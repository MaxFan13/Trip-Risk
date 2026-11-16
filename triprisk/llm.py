"""Where AI fits:

1. parse_query  -- turn "NYC to SF tomorrow morning" into airports + a date.
2. synthesize   -- turn a pile of heterogeneous evidence into a briefing a
                   traveler can act on: which risks matter, why, what to do.

Guardrails:
- The model receives the computed risk level and must not change it.
- Every risk and action must cite evidence ids; ids are validated after the
  call and anything uncited is dropped and reported.
- If the API is unavailable, a deterministic fallback keeps the app working.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv

from . import airports

load_dotenv()
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LAST_PARSE_ERROR: str | None = None


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def available() -> bool:
    return _api_key() is not None


def _json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Gemini returned no JSON object")
    return json.loads(text[start:end + 1])


def _call(system: str, user: str, max_tokens: int = 1500) -> dict | None:
    key = _api_key()
    if key is None:
        return None
    resp = requests.post(
        ENDPOINT.format(model=MODEL),
        headers={"x-goog-api-key": key},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": max_tokens,
                "temperature": 0.2,
                # thinking tokens would otherwise eat the output budget on 2.5 models
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=60,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as ex:
        try:
            message = resp.json().get("error", {}).get("message", "")
        except Exception:
            message = ""
        if message:
            raise RuntimeError(f"Gemini API {resp.status_code}: {message}") from ex
        raise RuntimeError(f"Gemini API returned HTTP {resp.status_code}") from ex
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no response candidate")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response")
    return _json(text)


# parsing
PARSE_SYSTEM = """You convert a traveler's free-text trip description into JSON.
Use ONLY airport codes from the provided catalog. If the user names a city, include
every catalog airport for that city. If they name a specific airport, include only it.
Resolve relative dates against today's date. Respond with JSON only:
{"origin": ["CODE", ...], "destination": ["CODE", ...], "date": "YYYY-MM-DD",
 "time_of_day": "morning|afternoon|evening|unspecified", "assumptions": "short note on anything you inferred"}
If you cannot determine origin, destination or date, set it to null."""


def _fallback_parse(text: str, today: date) -> dict | None:
    """Parse common trip forms locally when Gemini is unavailable."""
    normalized = text.strip()
    lower = normalized.lower()

    parts = re.split(r"\s+(?:to|→|->)\s+", normalized, flags=re.IGNORECASE, maxsplit=1)
    if len(parts) == 1 and re.search(r"\bfrom\b.+\b(?:to|→|->)\b", normalized, re.IGNORECASE):
        parts = re.split(r"\b(?:to|→|->)\b", re.sub(r"^.*\bfrom\b\s*", "", normalized, flags=re.IGNORECASE), maxsplit=1)
    elif len(parts) == 1:
        return None

    origin_text = parts[0]
    destination_text = parts[1]
    origin_text = re.sub(r"^\s*from\s+", "", origin_text, flags=re.IGNORECASE)

    def resolve_location(location: str) -> list[str]:
        location = location.strip()
        location_code = location.upper().strip()
        if location_code in airports.AIRPORTS:
            return [location_code]

        location_lower = location.lower()
        name_codes = [code for code, info in airports.AIRPORTS.items()
                      if info[0].lower() in location_lower or info[1].lower() in location_lower]
        if name_codes:
            return name_codes

        resolved = airports.resolve(location)
        return resolved

    origin = resolve_location(origin_text)

    destination_part = re.split(
        r"\b(?:tomorrow|today|this|next|on|at|morning|afternoon|evening)\b|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        destination_text,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]
    destination = resolve_location(destination_part)

    trip_date = None
    if "tomorrow" in lower:
        trip_date = today + timedelta(days=1)
    elif "today" in lower:
        trip_date = today
    else:
        iso_match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", normalized)
        if iso_match:
            try:
                trip_date = date(*(int(value) for value in iso_match.groups()))
            except ValueError:
                trip_date = None

        month_match = re.search(
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?\b",
            normalized,
            re.IGNORECASE,
        )
        if not trip_date and month_match:
            month_text, day_text, year_text = month_match.groups()
            year = int(year_text) if year_text else today.year
            try:
                trip_date = datetime.strptime(f"{month_text} {day_text} {year}", "%b %d %Y").date()
            except ValueError:
                try:
                    trip_date = datetime.strptime(f"{month_text} {day_text} {year}", "%B %d %Y").date()
                except ValueError:
                    pass

        if not trip_date:
            weekdays = {name: index for index, name in enumerate(
                ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
            )}
            weekday_match = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
            if weekday_match:
                target = weekdays[weekday_match.group(1)]
                days_ahead = (target - today.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 0
                elif re.search(r"\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower):
                    days_ahead += 7
                trip_date = today + timedelta(days=days_ahead)

    if not origin or not destination or trip_date is None:
        return None

    time_match = re.search(r"\b(morning|afternoon|evening)\b", lower)
    return {
        "origin": origin,
        "destination": destination,
        "date": trip_date.isoformat(),
        "time_of_day": time_match.group(1) if time_match else "unspecified",
        "assumptions": "Parsed locally from the trip text.",
    }


def parse_error() -> str | None:
    return LAST_PARSE_ERROR


def parse_query(text: str, today: date) -> dict | None:
    global LAST_PARSE_ERROR
    LAST_PARSE_ERROR = None
    user = f"Today is {today.isoformat()} ({today.strftime('%A')}).\nCatalog:\n{airports.catalog_for_prompt()}\n\nTrip: {text}"
    try:
        out = _call(PARSE_SYSTEM, user, 400)
    except Exception as ex:
        LAST_PARSE_ERROR = f"{type(ex).__name__}: {ex}"
        out = None
    else:
        if out is None and not available():
            LAST_PARSE_ERROR = "No Gemini API key is configured"
    if not out:
        return _fallback_parse(text, today)
    out["origin"] = [c for c in (out.get("origin") or []) if c in airports.AIRPORTS]
    out["destination"] = [c for c in (out.get("destination") or []) if c in airports.AIRPORTS]
    if out.get("origin") and out.get("destination") and out.get("date"):
        return out
    return _fallback_parse(text, today)


# synthesis
SYNTH_SYSTEM = """You are a travel-operations analyst writing a short pre-trip risk briefing.

Rules:
- The overall risk level has already been computed by rules. Do NOT change it; explain it.
- Use only the evidence provided. Every risk and every action must cite evidence ids
  from the input in "evidence_ids". Never invent ids, numbers, or events.
- Prioritize what would actually disrupt a flight (operations > official warnings >
  aviation forecast > general forecast). Merge evidence about the same hazard.
- Be calibrated: say "possible", "likely" etc. consistent with the confidence and
  days until travel. Name what is NOT known (e.g. live FAA status is unavailable until the day).
- If several airports serve a city and one is clearly worse, consider recommending an alternate.
- If the risk is Minimal or Low, say so plainly and recommend no action beyond normal checks.
- Actions must be concrete and proportionate (e.g. "Rebook to a morning departure",
  "Check airline travel waivers", "Leave extra time for the drive to EWR").

Respond with JSON only:
{"headline": "one sentence",
 "summary": "2-4 sentences",
 "risks": [{"title": "...", "airport": "CODE", "likelihood": "low|possible|likely|occurring",
            "impact": "what it would do to the trip", "evidence_ids": ["..."]}],
 "actions": [{"action": "...", "why": "...", "when": "now|day before|day of", "evidence_ids": ["..."]}],
 "uncertainty": "what could change this assessment and when to re-check"}"""


def synthesize(payload: dict, time_of_day: str = "unspecified") -> tuple[dict, list[str]]:
    """Returns (briefing, warnings). Falls back to a deterministic briefing."""
    warnings: list[str] = []
    try:
        out = _call(SYNTH_SYSTEM, json.dumps({**payload, "traveler_time_of_day": time_of_day}, default=str))
    except Exception as ex:
        out = None
        detail = str(ex).strip()
        if detail:
            warnings.append(f"AI briefing unavailable ({type(ex).__name__}: {detail}); showing rule-based summary.")
        else:
            warnings.append(f"AI briefing unavailable ({type(ex).__name__}); showing rule-based summary.")
    if out is None:
        if not warnings:
            warnings.append("No GEMINI_API_KEY set; showing rule-based summary.")
        return fallback(payload), warnings

    valid = {e["id"] for e in payload["evidence"]}
    for key in ("risks", "actions"):
        kept = []
        for item in out.get(key, []) or []:
            ids = [i for i in item.get("evidence_ids", []) if i in valid]
            dropped = set(item.get("evidence_ids", [])) - set(ids)
            if dropped:
                warnings.append(f"Removed unknown evidence id(s) {sorted(dropped)} cited by the AI.")
            if ids or (key == "actions" and payload["computed_risk_level"] in ("Minimal", "Low")):
                item["evidence_ids"] = ids
                kept.append(item)
            else:
                warnings.append(f"Dropped an AI {key[:-1]} with no supporting evidence: {item.get('title') or item.get('action')!r}")
        out[key] = kept
    return out, warnings


def fallback(payload: dict) -> dict:
    ev = payload["evidence"]
    top = [e for e in ev if e["severity"] >= 2] or ev[:3]
    level = payload["computed_risk_level"]
    return {
        "headline": f"{level} disruption risk for this trip.",
        "summary": ("No significant hazards found in the available sources." if not ev else
                    f"{len(ev)} signal(s) found; the most significant are listed below."),
        "risks": [{"title": e["summary"], "airport": e["airport"], "likelihood": "possible",
                   "impact": e["rule"], "evidence_ids": [e["id"]]} for e in top],
        "actions": ([] if level in ("Minimal", "Low") else
                    [{"action": "Check your airline's app for travel waivers and flight status",
                      "why": "Moderate or higher risk detected", "when": "day before", "evidence_ids": [top[0]["id"]]}]),
        "uncertainty": " ".join(payload["confidence_reasons"]),
    }

"""Gathers all sources in parallel and combines them deterministically. The risk level is computed by transparent rules, not by the
LLM. The LLM explains, prioritizes and recommends. It can't change the
level. That keeps the headline number reproducible and auditable.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import airports
from .models import Evidence, SourceStatus, SEVERITY_LABELS
from .sources import faa, nws, openmeteo, taf

LEVELS = {0: "Minimal", 1: "Low", 2: "Moderate", 3: "High"}
MAX_LEAD_DAYS = 15  # Open-Meteo's horizon is 16 days including today


@dataclass
class Assessment:
    origin: list[str]
    destination: list[str]
    trip_date: date
    lead_days: int
    level: int
    level_label: str
    confidence: str
    confidence_reasons: list[str]
    per_airport: dict[str, dict]
    evidence: list[Evidence]
    statuses: list[SourceStatus]
    corroborated: list[dict] = field(default_factory=list)

    def for_llm(self) -> dict:
        return {
            "route": {"origin_airports": self.origin, "destination_airports": self.destination},
            "travel_date": self.trip_date.isoformat(), "days_until_travel": self.lead_days,
            "computed_risk_level": self.level_label, "confidence": self.confidence,
            "confidence_reasons": self.confidence_reasons,
            "per_airport_level": {k: v["label"] for k, v in self.per_airport.items()},
            "corroborated_hazards": self.corroborated,
            "evidence": [
                {k: e.to_dict()[k] for k in ("id", "source", "airport", "hazard", "severity", "summary", "detail", "rule",
                                              "valid_from", "valid_to")}
                for e in self.evidence
            ],
            "source_coverage": [s.__dict__ for s in self.statuses],
        }


def _confidence(lead: int, statuses: list[SourceStatus]) -> tuple[str, list[str]]:
    reasons = []
    if lead <= 1:
        conf = 2
        reasons.append("Travel is within ~24 h: aviation forecasts apply" +
                       (" and live FAA status applies." if lead == 0 else "; live FAA status will only apply on the day."))
    elif lead <= 3:
        conf = 1
        reasons.append(f"Travel is {lead} days out: no live airport status or TAF yet; relying on forecasts and alerts.")
    elif lead <= 7:
        conf = 1
        reasons.append(f"Travel is {lead} days out: forecast skill for timing of storms is limited.")
    else:
        conf = 0
        reasons.append(f"Travel is {lead} days out: only a model forecast is available and it can change substantially.")
    errors = [s for s in statuses if s.status == "error"]
    if errors:
        conf = max(0, conf - 1)
        reasons.append("Some sources failed: " + ", ".join(sorted({f"{s.source} ({s.airport})" for s in errors})) + ".")
    return ["Low", "Medium", "High"][conf], reasons


def assess(origin: list[str], destination: list[str], trip_date: date) -> Assessment:
    codes = list(dict.fromkeys(origin + destination))
    aps = [airports.info(c) for c in codes]
    today = datetime.now(ZoneInfo(aps[0]["tz"])).date()
    lead = (trip_date - today).days
    if lead < 0 or lead > MAX_LEAD_DAYS:
        raise ValueError(f"Travel date must be between today and {MAX_LEAD_DAYS} days out "
                         f"(forecast horizon). Got {lead} days.")

    evidence: list[Evidence] = []
    statuses: list[SourceStatus] = []

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(mod.fetch, ap, trip_date) for ap in aps for mod in (nws, openmeteo, taf)]
        faa_future = pool.submit(faa.fetch_all)
        for f in futures:
            r = f.result()
            evidence += r.evidence
            statuses += r.statuses
        try:
            entries, update = faa_future.result()
            for ap in aps:
                r = faa.evaluate(entries, update, ap, trip_date)
                evidence += r.evidence
                statuses += r.statuses
        except Exception as ex:
            for ap in aps:
                statuses.append(SourceStatus(faa.SOURCE, ap["code"], "error", str(ex)[:200]))

    # Per-airport level = worst single signal. Track cross-source agreement.
    per_airport = {}
    corroborated = []
    for code in codes:
        ev = [e for e in evidence if e.airport == code]
        lvl = max((e.severity for e in ev), default=0)
        by_hazard = defaultdict(set)
        for e in ev:
            by_hazard[e.hazard].add(e.source)
        for hz, srcs in by_hazard.items():
            if len(srcs) >= 2:
                corroborated.append({"airport": code, "hazard": hz, "sources": sorted(srcs)})
        per_airport[code] = {"level": lvl, "label": LEVELS[lvl],
                             "role": "origin" if code in origin else "destination",
                             "name": airports.info(code)["name"]}

    level = max((v["level"] for v in per_airport.values()), default=0)
    confidence, reasons = _confidence(lead, statuses)
    if corroborated and level >= 2:
        reasons.append("Key hazards are corroborated by independent sources: " +
                       "; ".join(f"{c['hazard']} at {c['airport']}" for c in corroborated) + ".")

    evidence.sort(key=lambda e: (-e.severity, e.airport))
    return Assessment(origin, destination, trip_date, lead, level, LEVELS[level], confidence, reasons,
                      per_airport, evidence, statuses, corroborated)


__all__ = ["assess", "Assessment", "LEVELS", "SEVERITY_LABELS"]

"""FAA National Airspace System status (nasstatus.faa.gov). This shows ground stops, ground delay programs, closures. It's real-time
only, so it's applied when the trip is today and marked not-applicable otherwise.

The XML schema isn't formally documented, so the parser is deliberately
schema-tolerant: it walks every <Delay_type>, and treats any element that has
an <ARPT> child as one program entry.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..models import Evidence, SourceResult, SourceStatus
from .common import get, now_iso

SOURCE = "FAA NAS Status"
URL = "https://nasstatus.faa.gov/api/airport-status-information"
PUBLIC_URL = "https://nasstatus.faa.gov/"


def _flatten(el: ET.Element) -> dict:
    out = {}
    for child in el.iter():
        if child is el:
            continue
        txt = (child.text or "").strip()
        if txt:
            key = child.tag + (f"[{child.attrib.get('Type')}]" if child.attrib.get("Type") else "")
            out.setdefault(key, txt)
        for k, v in child.attrib.items():
            out.setdefault(f"{child.tag}.{k}", v)
    return out


def _minutes(text: str) -> int:
    """'1 hour and 15 minutes' / '45 minutes' -> minutes."""
    if not text:
        return 0
    h = re.search(r"(\d+)\s*hour", text)
    m = re.search(r"(\d+)\s*min", text)
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def fetch_all() -> tuple[list[dict], str | None]:
    """One national call; returns list of {type, airport, fields}."""
    xml = get(URL, accept="application/xml").text
    root = ET.fromstring(xml)
    update = root.findtext("Update_Time")
    entries = []
    for dt in root.iter("Delay_type"):
        name = dt.findtext("Name") or "Unknown"
        for el in dt.iter():
            arpt = el.find("ARPT")
            if arpt is not None and arpt.text:
                entries.append({"type": name, "airport": arpt.text.strip().upper(), "fields": _flatten(el)})
    return entries, update


def evaluate(entries: list[dict], update: str | None, ap: dict, trip_date: date) -> SourceResult:
    res = SourceResult()
    today_local = datetime.now(ZoneInfo(ap["tz"])).date()
    if trip_date != today_local:
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "not_applicable",
                                         "Real-time feed; only meaningful on the day of travel"))
        return res

    n = 0
    for e in entries:
        if e["airport"] != ap["code"]:
            continue
        t = e["type"].lower()
        f = e["fields"]
        reason = f.get("Reason", "not given")
        if "closure" in t:
            sev, hazard, rule = 3, "closure", "airport closure"
        elif "ground stop" in t:
            sev, hazard, rule = 3, "ground_stop", "active ground stop"
        elif "ground delay" in t:
            avg = _minutes(f.get("Avg", ""))
            sev, hazard = (3 if avg >= 60 else 2), "ground_delay"
            rule = f"ground delay program, avg {avg} min ({'>=60 → Severe' if avg >= 60 else '<60 → Moderate'})"
        else:
            mx = max(_minutes(v) for k, v in f.items() if k.startswith("Max")) if any(
                k.startswith("Max") for k in f) else 0
            sev, hazard = (2 if mx >= 45 else 1), "delay"
            rule = f"general delay, max {mx} min ({'>=45 → Moderate' if mx >= 45 else 'Minor'})"
        n += 1
        detail = "; ".join(f"{k}: {v}" for k, v in f.items() if k != "ARPT")
        res.evidence.append(Evidence(
            id=f"FAA-{ap['code']}-{n}", source=SOURCE, airport=ap["code"], category="airport_operations",
            hazard=hazard, severity=sev, summary=f"{e['type']} at {ap['code']} (reason: {reason})",
            detail=detail[:600], retrieved_at=now_iso(), valid_from=update, url=PUBLIC_URL, rule=rule,
        ))
    res.statuses.append(SourceStatus(SOURCE, ap["code"], "ok",
                                     f"{n} active program(s); feed updated {update or 'unknown'}"))
    return res

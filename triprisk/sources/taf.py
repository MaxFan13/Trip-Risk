"""Terminal Aerodrome Forecasts (aviationweather.gov). The forecast airlines and ATC actually plan against. Ceiling and
visibility drive arrival rates (and therefore ground delay programs) in a way
consumer forecasts don't capture. It only covers 24-30 hours, so it is
not-applicable for trips further out.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models import Evidence, SourceResult, SourceStatus
from .common import get, now_iso, overlaps, trip_window

SOURCE = "Aviation Weather TAF"
URL = "https://aviationweather.gov/api/data/taf"


def _vis_sm(v) -> float:
    if v is None:
        return 10.0
    s = str(v).replace("+", "").strip()
    try:
        if " " in s:  # "1 1/2"
            whole, frac = s.split()
            n, d = frac.split("/")
            return float(whole) + float(n) / float(d)
        if "/" in s:
            n, d = s.split("/")
            return float(n) / float(d)
        return float(s)
    except ValueError:
        return 10.0


def _ceiling_ft(clouds) -> int | None:
    bases = [c.get("base") for c in (clouds or []) if c.get("cover") in ("BKN", "OVC", "OVX") and c.get("base") is not None]
    return min(bases) if bases else None


def _category(ceiling, vis) -> str:
    if (ceiling is not None and ceiling < 500) or vis < 1:
        return "LIFR"
    if (ceiling is not None and ceiling < 1000) or vis < 3:
        return "IFR"
    if (ceiling is not None and ceiling <= 3000) or vis <= 5:
        return "MVFR"
    return "VFR"


def fetch(ap: dict, trip_date: date) -> SourceResult:
    res = SourceResult()
    win_start, win_end = trip_window(trip_date, ap["tz"])
    try:
        data = get(URL, {"ids": ap["icao"], "format": "json"}).json()
    except Exception as ex:
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "error", str(ex)[:200]))
        return res
    if not data:
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "error", "No TAF returned"))
        return res

    taf = data[0]
    periods = []
    for f in taf.get("fcsts", []):
        t0 = datetime.fromtimestamp(f["timeFrom"], tz=timezone.utc) if f.get("timeFrom") else None
        t1 = datetime.fromtimestamp(f["timeTo"], tz=timezone.utc) if f.get("timeTo") else None
        if t0 and t1 and overlaps(t0, t1, win_start, win_end):
            periods.append((t0, t1, f))
    if not periods:
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "not_applicable",
                                         "TAF does not reach the travel day (covers ~24-30 h)"))
        return res

    worst = {"LIFR": [], "IFR": [], "TS": [], "GUST": []}
    for t0, t1, f in periods:
        cat = _category(_ceiling_ft(f.get("clouds")), _vis_sm(f.get("visib")))
        label = f"{t0.strftime('%H%MZ')}-{t1.strftime('%H%MZ')}"
        if cat in ("LIFR", "IFR"):
            worst[cat].append(label)
        if "TS" in (f.get("wxString") or ""):
            worst["TS"].append(label)
        if (f.get("wgst") or 0) >= 35:
            worst["GUST"].append(f"{label} G{f.get('wgst')}kt")

    found = []
    if worst["LIFR"]:
        found.append(("low_visibility", 2, f"LIFR conditions forecast ({', '.join(worst['LIFR'][:3])})", "LIFR period → Moderate"))
    elif worst["IFR"]:
        found.append(("low_visibility", 1, f"IFR conditions forecast ({', '.join(worst['IFR'][:3])})", "IFR period → Minor"))
    if worst["TS"]:
        found.append(("thunderstorm", 2, f"Thunderstorms in TAF ({', '.join(worst['TS'][:3])})", "TS in TAF → Moderate"))
    if worst["GUST"]:
        found.append(("wind", 2, f"Gusts ≥35 kt ({', '.join(worst['GUST'][:3])})", "gust ≥35 kt → Moderate"))

    raw_text = taf.get("rawTAF", "")
    for n, (hazard, sev, summary, rule) in enumerate(found, 1):
        res.evidence.append(Evidence(
            id=f"TAF-{ap['code']}-{n}", source=SOURCE, airport=ap["code"], category="aviation_forecast",
            hazard=hazard, severity=sev, summary=summary, detail=raw_text, retrieved_at=now_iso(),
            url=f"https://aviationweather.gov/data/taf/?ids={ap['icao']}", rule=rule,
        ))
    res.statuses.append(SourceStatus(SOURCE, ap["code"], "ok", f"{len(periods)} TAF period(s) overlap the travel day"))
    res.raw[ap["code"]] = raw_text
    return res

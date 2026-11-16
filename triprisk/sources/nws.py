# National Weather Service active alerts (api.weather.gov). These are the official warnings/watches/advisories.
from __future__ import annotations

from datetime import date

from ..models import Evidence, SourceResult, SourceStatus
from .common import get, now_iso, overlaps, parse_dt, trip_window

SOURCE = "NWS Alerts"

# Alert events that matter for air travel; anything else is shown at severity 1 at most.
TRAVEL_RELEVANT = {
    "thunderstorm": "thunderstorm", "tornado": "thunderstorm", "hurricane": "tropical",
    "tropical storm": "tropical", "winter storm": "snow", "blizzard": "snow", "snow": "snow",
    "ice storm": "ice", "freezing": "ice", "wind": "wind", "fog": "low_visibility",
    "dust": "low_visibility", "smoke": "low_visibility", "flood": "flood",
}


def _hazard(event: str) -> tuple[str, bool]:
    e = event.lower()
    for k, v in TRAVEL_RELEVANT.items():
        if k in e:
            return v, True
    return "other", False


def _severity(event: str, nws_severity: str, relevant: bool) -> tuple[int, str]:
    e = event.lower()
    if not relevant:
        return 1, "non-travel alert type, capped at Minor"
    if "warning" in e and nws_severity in ("Severe", "Extreme"):
        return 3, f"travel-relevant Warning with NWS severity {nws_severity}"
    if "warning" in e:
        return 2, "travel-relevant Warning"
    if "watch" in e:
        return 2, "travel-relevant Watch"
    return 1, "travel-relevant Advisory/Statement"


def fetch(ap: dict, trip_date: date) -> SourceResult:
    res = SourceResult()
    url = "https://api.weather.gov/alerts/active"
    try:
        data = get(url, {"point": f"{ap['lat']},{ap['lon']}"}, accept="application/geo+json").json()
    except Exception as ex:  # surfaced in the UI, never hidden
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "error", str(ex)[:200]))
        return res

    win_start, win_end = trip_window(trip_date, ap["tz"])
    n = 0
    for f in data.get("features", []):
        p = f.get("properties", {})
        start = parse_dt(p.get("onset") or p.get("effective"))
        end = parse_dt(p.get("ends") or p.get("expires"))
        if not overlaps(start, end, win_start, win_end):
            continue
        event = p.get("event", "Alert")
        hazard, relevant = _hazard(event)
        sev, rule = _severity(event, p.get("severity", ""), relevant)
        n += 1
        res.evidence.append(Evidence(
            id=f"NWS-{ap['code']}-{n}", source=SOURCE, airport=ap["code"], category="official_alert",
            hazard=hazard, severity=sev, summary=p.get("headline") or event,
            detail=(p.get("description") or "")[:600],
            valid_from=p.get("onset") or p.get("effective"), valid_to=p.get("ends") or p.get("expires"),
            retrieved_at=now_iso(), url=p.get("@id") or f.get("id"), rule=rule,
        ))
    res.statuses.append(SourceStatus(SOURCE, ap["code"], "ok", f"{n} alert(s) overlap the travel day"))
    res.raw[ap["code"]] = data
    return res

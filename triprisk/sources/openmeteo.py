"""Open-Meteo hourly forecast (api.open-meteo.com). This shows quantitative, hourly, and reaches 16 days out. It's a model forecast, so it can be wrong, but it is the only source that reaches beyond ~24–30 h.
"""
from __future__ import annotations

from datetime import date

from ..models import Evidence, SourceResult, SourceStatus
from .common import get, now_iso

SOURCE = "Open-Meteo"
URL = "https://api.open-meteo.com/v1/forecast"

THUNDER = {95, 96, 99}
FREEZING = {56, 57, 66, 67}
SNOW = {71, 73, 75, 77, 85, 86}


def fetch(ap: dict, trip_date: date) -> SourceResult:
    res = SourceResult()
    params = {
        "latitude": ap["lat"], "longitude": ap["lon"], "timezone": ap["tz"],
        "start_date": trip_date.isoformat(), "end_date": trip_date.isoformat(),
        "hourly": "weather_code,precipitation_probability,precipitation,snowfall,"
                  "wind_speed_10m,wind_gusts_10m,visibility",
        "wind_speed_unit": "mph",
    }
    try:
        data = get(URL, params).json()
        h = data["hourly"]
    except Exception as ex:
        res.statuses.append(SourceStatus(SOURCE, ap["code"], "error", str(ex)[:200]))
        return res

    times = h.get("time", [])

    def col(name):
        return [v if v is not None else 0 for v in h.get(name, [0] * len(times))]

    codes, gusts, snow = col("weather_code"), col("wind_gusts_10m"), col("snowfall")
    vis = [v for v in h.get("visibility", []) if v is not None]
    pop, precip = col("precipitation_probability"), col("precipitation")

    def hours_where(pred):
        return [times[i][11:16] for i in range(len(times)) if pred(i)]

    found = []
    ts = hours_where(lambda i: codes[i] in THUNDER)
    if ts:
        found.append(("thunderstorm", 2, f"Thunderstorms forecast ({len(ts)} h: {', '.join(ts[:6])})",
                      "any thunderstorm hour → Moderate"))
    fz = hours_where(lambda i: codes[i] in FREEZING)
    if fz:
        found.append(("ice", 3, f"Freezing rain/drizzle forecast ({len(fz)} h)", "any freezing precip → Severe"))
    snow_cm = round(sum(snow), 1)
    if snow_cm >= 15:
        found.append(("snow", 3, f"Heavy snow: {snow_cm} cm over the day", "snow ≥15 cm → Severe"))
    elif snow_cm >= 5:
        found.append(("snow", 2, f"Snow accumulation: {snow_cm} cm", "snow ≥5 cm → Moderate"))
    elif any(c in SNOW for c in codes):
        found.append(("snow", 1, f"Light snow possible ({snow_cm} cm)", "snow codes present → Minor"))
    max_gust = round(max(gusts) if gusts else 0)
    if max_gust >= 45:
        found.append(("wind", 2, f"Strong gusts up to {max_gust} mph", "gust ≥45 mph → Moderate"))
    elif max_gust >= 35:
        found.append(("wind", 1, f"Gusty winds up to {max_gust} mph", "gust ≥35 mph → Minor"))
    min_vis = min(vis) if vis else None
    if min_vis is not None and min_vis < 800:
        found.append(("low_visibility", 2, f"Very low visibility ({int(min_vis)} m minimum)", "visibility <800 m → Moderate"))
    elif min_vis is not None and min_vis < 1600:
        found.append(("low_visibility", 1, f"Reduced visibility ({int(min_vis)} m minimum)", "visibility <1600 m → Minor"))
    heavy = hours_where(lambda i: precip[i] >= 5 and pop[i] >= 60)
    if heavy:
        found.append(("heavy_rain", 1, f"Heavy rain likely ({len(heavy)} h ≥5 mm/h)", "≥5 mm/h with PoP ≥60% → Minor"))

    detail = (f"Max gust {max_gust} mph; max precip probability {max(pop) if pop else 0}%; "
              f"total snowfall {snow_cm} cm; min visibility {int(min_vis) if min_vis is not None else 'n/a'} m")
    for n, (hazard, sev, summary, rule) in enumerate(found, 1):
        res.evidence.append(Evidence(
            id=f"OM-{ap['code']}-{n}", source=SOURCE, airport=ap["code"], category="weather_forecast",
            hazard=hazard, severity=sev, summary=summary, detail=detail,
            valid_from=trip_date.isoformat(), retrieved_at=now_iso(), url="https://open-meteo.com/", rule=rule,
        ))
    res.statuses.append(SourceStatus(SOURCE, ap["code"], "ok", detail))
    res.raw[ap["code"]] = {"max_gust_mph": max_gust, "max_pop": max(pop) if pop else 0,
                           "snow_cm": snow_cm, "min_visibility_m": min_vis}
    return res

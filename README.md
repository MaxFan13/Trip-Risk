# Trip disruption check

Enter a U.S. flight ("New York to San Francisco tomorrow") and get a risk level,
the specific risks, the evidence behind each one, and what to do about it.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY (free: aistudio.google.com/apikey) and a contact email
streamlit run app.py
```

Without an API key the app still runs (manual trip entry, rule-based summary).

## Sources (all free, live, no key)

| Source | What it adds | Horizon |
|---|---|---|
| NWS active alerts (`api.weather.gov`) | Official warnings, watches, advisories | Active/issued alerts |
| FAA NAS status (`nasstatus.faa.gov`) | Ground stops, delay programs, closures — what's actually happening | Day of travel only |
| Aviation Weather TAF (`aviationweather.gov`) | Ceiling/visibility/gusts that drive arrival rates | ~24–30 h |
| Open-Meteo (`api.open-meteo.com`) | Hourly storms, snow, ice, wind, visibility | 16 days |
| Gemini (Google AI Studio free tier) | Trip parsing; evidence-grounded briefing | — |

The sources were picked to cover different *time horizons* and different
*kinds* of truth: observed operations, official judgement, aviation-specific
forecast, and a quantitative model. Confidence falls as fewer of them apply.

## How signals combine

1. Each source normalizes findings into `Evidence` with a 0–3 severity set by
   a visible rule (e.g. "gust ≥45 mph → Moderate").
2. Airport level = worst finding. Trip level = worst airport.
3. Hazards flagged by two independent sources at one airport are marked corroborated.
4. Confidence = lead time + source coverage − source failures.

## Where AI is (and isn't) used

- **Is**: parsing free text into airports + date; writing the briefing —
  prioritizing, merging overlapping evidence, recommending proportionate actions,
  and stating uncertainty.
- **Isn't**: setting the risk level. The level is deterministic so it's
  reproducible and explainable. The model must cite evidence ids; uncited
  claims are removed and the removal is shown to the user.

## Known limitations / before real users

- Thresholds are uncalibrated judgment calls. Backtest them against BTS on-time
  and cancellation data and convert severity to an estimated delay/cancel probability.
- No flight-specific data (connections, aircraft inbound delays, airline ops).
  A flight-status API would be the highest-value addition.
- Only ~40 airports; swap to the full OurAirports dataset.
- No en-route or hub weather for connections.
- FAA XML schema is undocumented; parser is tolerant but needs monitoring.
- Add caching per source/TTL, retries, rate limiting, logging of LLM inputs/outputs,
  an eval set of past disruption days, and proactive alerts for booked trips
  (re-check automatically at 72 h / 24 h / day of).

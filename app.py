"""Streamlit front end.  Run:  streamlit run app.py"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from streamlit.runtime.scriptrunner import get_script_run_ctx

from triprisk import airports, llm  # noqa: E402
from triprisk.engine import MAX_LEAD_DAYS, assess  # noqa: E402
from triprisk.models import SEVERITY_LABELS  # noqa: E402

if get_script_run_ctx() is None:
    raise SystemExit("This is a Streamlit app. Run it with: streamlit run app.py")

st.set_page_config(page_title="Trip disruption check", page_icon="✈️", layout="wide")

LEVEL_COLORS = {"Minimal": "#2E7D5B", "Low": "#5B8C2E", "Moderate": "#C27C0E", "High": "#B3261E"}
SEV_COLORS = {0: "#6B7785", 1: "#5B8C2E", 2: "#C27C0E", 3: "#B3261E"}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stTextInput input { font-family: 'Public Sans', system-ui, sans-serif; }
.verdict { border-left: 10px solid var(--c); padding: 1rem 1.25rem; background: #fff; border-radius: 4px; }
.verdict h2 { margin: 0; font-weight: 800; color: var(--c); font-size: 2rem; }
.verdict p { margin: .35rem 0 0; font-size: 1.05rem; max-width: 70ch; }
.chip { display:inline-block; padding: .05rem .45rem; margin: 0 .2rem .2rem 0; border-radius: 3px;
        background:#E8EEF4; font-size:.78rem; font-weight:600; color:#1F4E79; }
.ap { border-top: 4px solid var(--c); background:#fff; padding:.6rem .8rem; border-radius: 3px; }
.ap b { font-size: 1.2rem; } .ap span { color: var(--c); font-weight: 700; }
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=300, show_spinner=False)
def run_assessment(origin: tuple, dest: tuple, d: date):
    return assess(list(origin), list(dest), d)


def chips(ids):
    return "".join(f"<span class='chip'>{i}</span>" for i in ids)


today = datetime.now(ZoneInfo("America/New_York")).date()

# input
st.title("Will my trip be disrupted?")
st.caption("Checks official weather alerts, live FAA airport status, aviation and hourly forecasts for "
           "both ends of a U.S. flight, then explains what matters.")

with st.sidebar:
    st.subheader("Enter trip manually")
    st.caption("Use this if the free-text box misreads your trip.")
    codes = list(airports.AIRPORTS)
    fmt = lambda c: f"{c} · {airports.AIRPORTS[c][0]}"  # noqa: E731
    m_origin = st.multiselect("From", codes, format_func=fmt, key="m_origin")
    m_dest = st.multiselect("To", codes, format_func=fmt, key="m_dest")
    m_date = st.date_input("Date", today + timedelta(days=1), min_value=today,
                           max_value=today + timedelta(days=MAX_LEAD_DAYS))
    manual = st.button("Check this trip", width="stretch")

query = st.text_input("Where and when are you flying?", placeholder="New York to San Francisco tomorrow morning")
go = st.button("Check trip", type="primary")

trip = None
if manual and m_origin and m_dest:
    trip = {"origin": m_origin, "destination": m_dest, "date": m_date.isoformat(),
            "time_of_day": "unspecified", "assumptions": "Entered manually."}
elif go and query:
    with st.spinner("Reading your trip..."):
        try:
            trip = llm.parse_query(query, today)
        except Exception as ex:
            st.error(f"Couldn't interpret the trip with AI ({type(ex).__name__}). Use the manual form in the sidebar.")
        if trip and trip.get("assumptions", "").startswith("Parsed locally"):
            if hasattr(llm, "parse_error"):
                error = llm.parse_error()
                if error:
                    st.warning(f"AI trip parsing was unavailable; used local parsing instead. {error}")
        if trip is None and not llm.available():
            st.warning("Free-text input needs GEMINI_API_KEY. Use the manual form in the sidebar.")
    if trip and (not isinstance(trip, dict)
                 or not trip.get("origin")
                 or not trip.get("destination")
                 or not trip.get("date")):
        st.error("I couldn't identify both airports and a date from that. Try naming the cities, "
                 "or use the manual form in the sidebar.")
        trip = None

if not isinstance(trip, dict):
    st.info("Try “Chicago to Denver this Friday” or “JFK → LAX on " +
            (today + timedelta(days=3)).strftime("%b ") + str((today + timedelta(days=3)).day) + "”. Forecasts reach "
            f"{MAX_LEAD_DAYS} days out.")
    st.stop()

try:
    trip_date = date.fromisoformat(trip["date"])
except (KeyError, TypeError, ValueError):
    st.error("The trip date was not valid. Try naming a complete date or use the manual form in the sidebar.")
    st.stop()

origin_codes = trip.get("origin") or []
destination_codes = trip.get("destination") or []
time_of_day = trip.get("time_of_day") or "unspecified"
assumptions = trip.get("assumptions")

if not isinstance(origin_codes, list) or not isinstance(destination_codes, list):
    st.error("The airport details were not valid. Try the manual form in the sidebar.")
    st.stop()

st.markdown(f"**Checking** {', '.join(origin_codes)} → {', '.join(destination_codes)} on "
            f"{trip_date.strftime('%A, %B ') + str(trip_date.day)}"
            + (f" ({time_of_day})" if time_of_day != "unspecified" else "")
            + (f"  \n<small>Assumed: {assumptions}</small>" if assumptions else ""),
            unsafe_allow_html=True)

# assessment
try:
    with st.spinner("Pulling alerts, airport status and forecasts..."):
        a = run_assessment(tuple(trip["origin"]), tuple(trip["destination"]), trip_date)
except ValueError as ex:
    st.error(str(ex))
    st.stop()

with st.spinner("Writing your briefing..."):
    brief, warnings = llm.synthesize(a.for_llm(), trip.get("time_of_day", "unspecified"))

color = LEVEL_COLORS[a.level_label]
st.markdown(f"""<div class='verdict' style='--c:{color}'>
<h2>{a.level_label} risk</h2>
<p><b>{brief.get('headline', '')}</b></p>
<p>{brief.get('summary', '')}</p>
<p style='color:#4A5866;font-size:.9rem'>Confidence: <b>{a.confidence}</b> · {' '.join(a.confidence_reasons)}</p>
</div>""", unsafe_allow_html=True)
for w in warnings:
    st.caption(f"{w}")

st.write("")
cols = st.columns(len(a.per_airport))
for col, (code, v) in zip(cols, a.per_airport.items()):
    c = LEVEL_COLORS[v["label"]]
    col.markdown(f"<div class='ap' style='--c:{c}'><b>{code}</b> <small>{v['role']}</small><br>"
                 f"<span>{v['label']}</span><br><small>{v['name']}</small></div>", unsafe_allow_html=True)

st.write("")
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("What could go wrong")
    if not brief.get("risks"):
        st.write("Nothing in the available data points to a meaningful disruption.")
    for r in brief.get("risks", []):
        st.markdown(f"**{r.get('title')}** · {r.get('airport', '')} · _{r.get('likelihood', '')}_  \n"
                    f"{r.get('impact', '')}  \n{chips(r.get('evidence_ids', []))}", unsafe_allow_html=True)
with right:
    st.subheader("What to do")
    if not brief.get("actions"):
        st.write("No action needed beyond checking your flight status before leaving.")
    for x in brief.get("actions", []):
        st.markdown(f"**{x.get('action')}** <small>({x.get('when', '')})</small>  \n{x.get('why', '')}  \n"
                    f"{chips(x.get('evidence_ids', []))}", unsafe_allow_html=True)
    st.markdown(f"**What could change this:** {brief.get('uncertainty', '')}")

# evidence
st.subheader("Evidence")
st.caption("Every risk above cites these ids. Severity comes from the fixed rule shown, not from the AI.")
if a.evidence:
    df = pd.DataFrame([{
        "id": e.id, "airport": e.airport, "source": e.source, "severity": SEVERITY_LABELS[e.severity],
        "finding": e.summary, "rule applied": e.rule, "valid": f"{e.valid_from or ''} → {e.valid_to or ''}",
        "link": e.url,
    } for e in a.evidence])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"link": st.column_config.LinkColumn("link", display_text="source")})
    with st.expander("Full text of each finding"):
        for e in a.evidence:
            st.markdown(f"**{e.id}** · {e.source} · retrieved {e.retrieved_at}")
            st.text(e.detail or "(no detail)")
else:
    st.write("No hazards found in any source for this day.")

with st.expander("Which sources were checked"):
    st.dataframe(pd.DataFrame([s.__dict__ for s in a.statuses]), hide_index=True, width="stretch")

with st.expander("How this assessment works"):
    st.markdown("""
- **Sources**: NWS active alerts, FAA NAS airport status (day of travel only), Aviation Weather Center TAFs
  (~24–30 h), Open-Meteo hourly model forecast (up to 16 days). All queried live, per airport.
- **Scoring**: each finding gets a 0–3 severity from a fixed threshold (shown in *rule applied*).
  An airport's level is its worst finding; the trip's level is its worst airport.
- **Confidence**: driven by how far out the trip is, which sources apply at that range, and whether any failed.
  Hazards flagged by two independent sources are called out as corroborated.
- **AI**: Gemini reads the free-text trip, and writes the briefing from the evidence. It can't change the level,
  and any risk or action without a valid evidence id is removed.
""")
    st.json(a.for_llm(), expanded=False)

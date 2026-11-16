"""Unit tests for parsing/threshold logic. Fixtures here test rules only --
the app itself always calls the live APIs."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from triprisk import airports
from triprisk.sources import faa, taf
from triprisk.models import SourceStatus
from triprisk.engine import _confidence

FAA_XML = """<AIRPORT_STATUS_INFORMATION><Update_Time>Thu Oct 29 14:02:00 2026 GMT</Update_Time>
<Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List><Ground_Delay>
<ARPT>SFO</ARPT><Reason>low ceilings</Reason><Avg>1 hour and 12 minutes</Avg><Max>2 hours and 5 minutes</Max>
</Ground_Delay></Ground_Delay_List></Delay_type>
<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List><Program><ARPT>EWR</ARPT>
<Reason>thunderstorms</Reason><End_Time>3:00 pm EDT</End_Time></Program></Ground_Stop_List></Delay_type>
</AIRPORT_STATUS_INFORMATION>"""

def test_resolve():
    assert set(airports.resolve("nyc")) == {"JFK", "LGA", "EWR"}
    assert airports.resolve("sfo") == ["SFO"]

def test_faa(monkeypatch):
    class R: text = FAA_XML
    monkeypatch.setattr(faa, "get", lambda *a, **k: R())
    entries, upd = faa.fetch_all()
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    sfo = faa.evaluate(entries, upd, airports.info("SFO"), today)
    assert sfo.evidence[0].severity == 3 and sfo.evidence[0].hazard == "ground_delay"
    ewr = faa.evaluate(entries, upd, airports.info("EWR"), datetime.now(ZoneInfo("America/New_York")).date())
    assert ewr.evidence[0].hazard == "ground_stop"
    later = faa.evaluate(entries, upd, airports.info("SFO"), date(2099, 1, 1))
    assert later.statuses[0].status == "not_applicable"

def test_taf_category():
    assert taf._category(400, 5) == "LIFR"
    assert taf._category(None, taf._vis_sm("1 1/2")) == "IFR"
    assert taf._category(5000, taf._vis_sm("6+")) == "VFR"
    assert taf._ceiling_ft([{"cover": "FEW", "base": 300}, {"cover": "BKN", "base": 800}]) == 800

def test_confidence():
    assert _confidence(0, [])[0] == "High"
    assert _confidence(10, [])[0] == "Low"
    assert _confidence(1, [SourceStatus("x", "JFK", "error")])[0] == "Medium"

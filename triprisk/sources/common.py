from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

UA = f"trip-disruption-prototype ({os.getenv('CONTACT_EMAIL', 'contact@example.com')})"
TIMEOUT = 15


def get(url: str, params: dict | None = None, accept: str = "application/json") -> requests.Response:
    r = requests.get(url, params=params, headers={"User-Agent": UA, "Accept": accept}, timeout=TIMEOUT)
    r.raise_for_status()
    return r


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def trip_window(trip_date: date, tz: str) -> tuple[datetime, datetime]:
    """The travel day in the airport's local time, as aware datetimes."""
    start = datetime(trip_date.year, trip_date.month, trip_date.day, tzinfo=ZoneInfo(tz))
    return start, start + timedelta(days=1)


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    a_start = a_start or b_start
    a_end = a_end or b_end
    return a_start < b_end and b_start < a_end

"""Shared data model. Every source normalizes into Evidence so scoring and the
LLM only ever see one shape, and every claim in the output can point at an id."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

SEVERITY_LABELS = {0: "None", 1: "Minor", 2: "Moderate", 3: "Severe"}


@dataclass
class Evidence:
    id: str                 # stable id the LLM must cite, e.g. "NWS-JFK-1"
    source: str             # "NWS Alerts", "FAA NAS Status", "Open-Meteo", "Aviation Weather TAF"
    airport: str            # IATA code
    category: str           # "official_alert" | "airport_operations" | "weather_forecast" | "aviation_forecast"
    hazard: str             # normalized hazard tag: thunderstorm, snow, ice, wind, low_visibility, ground_stop, delay, ...
    severity: int           # 0-3, assigned by deterministic rules in the source module
    summary: str            # one line, human readable
    detail: str = ""        # supporting numbers / text
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    retrieved_at: Optional[str] = None
    url: Optional[str] = None
    rule: str = ""          # which threshold fired -- shown to the user, keeps scoring auditable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceStatus:
    source: str
    airport: str
    status: str             # "ok" | "error" | "not_applicable"
    note: str = ""


@dataclass
class SourceResult:
    evidence: list[Evidence] = field(default_factory=list)
    statuses: list[SourceStatus] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

"""Plain data types shared by the domain layer. No Django, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

LatLon = tuple[float, float]  # (latitude, longitude)


class RiskLevel(IntEnum):
    """Known risk levels, ordered by severity. *Unknown* is deliberately not a level:
    it is represented by ``None`` so it can never be compared as, or mistaken for, Low."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }[self]


UNKNOWN_KEY = "unknown"


def level_key(level: RiskLevel | None) -> str:
    return UNKNOWN_KEY if level is None else level.key


@dataclass(frozen=True)
class Driver:
    """One reason behind a checkpoint's risk level (shown to the user as "why")."""

    factor: str  # "wind" | "rain" | "snow" | "load_rule"
    level: RiskLevel
    text: str


@dataclass(frozen=True)
class RiskAssessment:
    """Risk at one checkpoint. ``level is None`` means Unknown: some input was missing and the
    known inputs did not already prove No Travel. ``at_least`` is the lower bound the known inputs
    give (informational only)."""

    level: RiskLevel | None
    drivers: tuple[Driver, ...] = ()
    missing: tuple[str, ...] = ()
    at_least: RiskLevel | None = None

    @property
    def is_known(self) -> bool:
        return self.level is not None


@dataclass(frozen=True)
class RawRoute:
    """A route as returned by a routing provider, normalised to metric units.

    ``time_offsets`` are (metres from start, seconds from start) pairs taken from the provider's
    guidance data; empty when the provider gave none (the ETA fallback is then used and flagged).
    """

    points: tuple[LatLon, ...]
    distance_m: float
    duration_s: float
    time_offsets: tuple[tuple[float, float], ...] = ()
    via: str | None = None

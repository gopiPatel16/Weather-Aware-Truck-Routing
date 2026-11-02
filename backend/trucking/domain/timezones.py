"""Time zones: origin-local departure -> UTC, DST edge cases, and zone labels (plan 5.5).

The departure the user types is a *naive local time at the origin*. The browser/device zone is
never involved. ``zoneinfo`` needs the ``tzdata`` package on Windows and slim Docker images.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from tzfpy import get_tz


class TimeZoneLookupError(Exception):
    """No time zone could be determined for a coordinate."""


class NonexistentLocalTime(ValueError):
    """The local time falls in a spring-forward gap and never happens."""

    def __init__(self, local: datetime, tz_name: str, next_valid: datetime) -> None:
        self.local, self.tz_name, self.next_valid = local, tz_name, next_valid
        super().__init__(
            f"{local:%Y-%m-%d %H:%M} does not exist in {tz_name} (clocks jump forward). "
            f"The next valid time is {next_valid:%Y-%m-%d %H:%M}."
        )


@dataclass(frozen=True)
class LocalDeparture:
    utc: datetime
    tz_name: str
    local_iso: str  # e.g. 2026-11-02T06:00:00-06:00
    ambiguous: bool  # the local time occurs twice (clocks fall back)
    other_utc: datetime | None  # the second occurrence when ambiguous


def tz_name_at(lat: float, lon: float) -> str:
    """IANA zone for a coordinate (offline lookup)."""
    name = get_tz(lon, lat)
    if not name:
        raise TimeZoneLookupError(f"no time zone for {lat:.4f}, {lon:.4f}")
    return str(name)


def _exists(naive: datetime, zone: ZoneInfo) -> bool:
    aware = naive.replace(tzinfo=zone, fold=0)
    back = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    return back == naive


def resolve_local(naive: datetime, tz_name: str) -> LocalDeparture:
    """Convert a naive local time in ``tz_name`` to UTC.

    * nonexistent (spring forward) -> ``NonexistentLocalTime``
    * ambiguous (fall back)        -> the FIRST occurrence (daylight time) is used and flagged
    """
    if naive.tzinfo is not None:
        raise ValueError("expected a naive local datetime")
    zone = ZoneInfo(tz_name)
    if not _exists(naive, zone):
        step = naive
        for _ in range(12):  # search forward in 15-minute steps (gaps are at most a few hours)
            step += timedelta(minutes=15)
            if _exists(step, zone):
                raise NonexistentLocalTime(naive, tz_name, step)
        raise NonexistentLocalTime(naive, tz_name, step)

    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    ambiguous = first.utcoffset() != second.utcoffset()
    return LocalDeparture(
        utc=first.astimezone(UTC),
        tz_name=tz_name,
        local_iso=first.isoformat(),
        ambiguous=ambiguous,
        other_utc=second.astimezone(UTC) if ambiguous else None,
    )


def zone_label(utc: datetime, tz_name: str) -> tuple[str, str]:
    """(ISO local time with offset, abbreviation such as CST) for an instant in a zone."""
    local = utc.astimezone(ZoneInfo(tz_name))
    return local.isoformat(), local.tzname() or tz_name

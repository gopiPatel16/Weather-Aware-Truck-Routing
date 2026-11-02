"""Origin-local departure -> UTC, DST edge cases, zone lookup and labels (plan 5.5)."""

from datetime import UTC, datetime

import pytest

from trucking.domain.timezones import NonexistentLocalTime, resolve_local, tz_name_at, zone_label


def test_zone_lookup_for_known_cities():
    assert tz_name_at(41.8781, -87.6298) == "America/Chicago"
    assert tz_name_at(39.7392, -104.9903) == "America/Denver"
    assert tz_name_at(33.4484, -112.0740) == "America/Phoenix"
    assert tz_name_at(47.6062, -122.3321) == "America/Los_Angeles"


def test_departure_is_read_in_origin_zone_standard_time():
    dep = resolve_local(datetime(2026, 11, 2, 6, 0), "America/Chicago")  # CST, UTC-6
    assert dep.utc == datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    assert not dep.ambiguous and dep.local_iso == "2026-11-02T06:00:00-06:00"


def test_departure_in_daylight_time():
    dep = resolve_local(datetime(2026, 7, 1, 6, 0), "America/Chicago")  # CDT, UTC-5
    assert dep.utc == datetime(2026, 7, 1, 11, 0, tzinfo=UTC)


def test_same_wall_clock_different_origin_zone_gives_different_utc():
    chicago = resolve_local(datetime(2026, 11, 2, 6, 0), "America/Chicago")
    denver = resolve_local(datetime(2026, 11, 2, 6, 0), "America/Denver")
    assert (denver.utc - chicago.utc).total_seconds() == 3600


def test_zone_without_dst():
    dep = resolve_local(datetime(2026, 7, 1, 12, 0), "America/Phoenix")  # UTC-7 all year
    assert dep.utc == datetime(2026, 7, 1, 19, 0, tzinfo=UTC)


def test_ambiguous_time_uses_first_occurrence_and_is_flagged():
    # 2026-11-01 01:30 happens twice in Chicago (CDT then CST).
    dep = resolve_local(datetime(2026, 11, 1, 1, 30), "America/Chicago")
    assert dep.ambiguous
    assert dep.utc == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)  # first: CDT, UTC-5
    assert dep.other_utc == datetime(2026, 11, 1, 7, 30, tzinfo=UTC)  # second: CST, UTC-6


def test_nonexistent_time_is_rejected_with_next_valid_time():
    # 2026-03-08 02:30 never happens in Chicago (02:00 jumps to 03:00).
    with pytest.raises(NonexistentLocalTime) as info:
        resolve_local(datetime(2026, 3, 8, 2, 30), "America/Chicago")
    assert info.value.next_valid == datetime(2026, 3, 8, 3, 0)
    assert "does not exist" in str(info.value)


def test_times_adjacent_to_the_gap_are_valid():
    assert resolve_local(datetime(2026, 3, 8, 1, 59), "America/Chicago").utc == datetime(
        2026, 3, 8, 7, 59, tzinfo=UTC
    )
    assert resolve_local(datetime(2026, 3, 8, 3, 0), "America/Chicago").utc == datetime(
        2026, 3, 8, 8, 0, tzinfo=UTC
    )


def test_aware_input_is_rejected():
    with pytest.raises(ValueError):
        resolve_local(datetime(2026, 11, 2, 6, 0, tzinfo=UTC), "America/Chicago")


def test_route_crossing_zones_labels_each_checkpoint_in_its_own_zone():
    instant = datetime(2026, 11, 2, 20, 0, tzinfo=UTC)
    chicago_iso, chicago_abbr = zone_label(instant, "America/Chicago")
    denver_iso, denver_abbr = zone_label(instant, "America/Denver")
    assert (chicago_abbr, denver_abbr) == ("CST", "MST")
    assert chicago_iso.startswith("2026-11-02T14:00") and denver_iso.startswith("2026-11-02T13:00")


def test_label_follows_dst_of_the_instant():
    assert zone_label(datetime(2026, 7, 1, 18, 0, tzinfo=UTC), "America/Chicago")[1] == "CDT"
    assert zone_label(datetime(2026, 12, 1, 18, 0, tzinfo=UTC), "America/Chicago")[1] == "CST"

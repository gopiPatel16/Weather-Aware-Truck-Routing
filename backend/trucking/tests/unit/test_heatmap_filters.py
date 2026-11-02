"""Real-distance heatmap grid, per-hour levels, and honest route de-duplication."""

from datetime import UTC, datetime

import pytest

from trucking.domain.forecast import HourlySeries
from trucking.domain.geo import cumulative_miles, haversine_miles, sample_along
from trucking.domain.heatmap import (
    corridor_cells,
    hourly_levels,
    lat_step_deg,
    levels_string,
    lon_step_deg,
)
from trucking.domain.route_filters import dedupe, is_duplicate, share_ratio
from trucking.domain.types import RawRoute, RiskLevel

START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def line(lat0, lon0, lat1, lon1, n=60):
    return [
        (lat0 + (lat1 - lat0) * i / (n - 1), lon0 + (lon1 - lon0) * i / (n - 1)) for i in range(n)
    ]


def samples(points, step=5.0):
    return sample_along(points, cumulative_miles(points), step)


# ---- grid in real distance ----------------------------------------------------------------
@pytest.mark.parametrize("lat", [30.0, 45.0, 60.0])
def test_east_west_spacing_is_fifteen_miles_at_every_latitude(lat):
    cells = corridor_cells([samples(line(lat, -100, lat, -98))], 15.0, 20.0)
    row_lat = min(cells, key=lambda c: abs(c.lat - lat)).lat
    row = sorted((c for c in cells if c.lat == row_lat), key=lambda c: c.col)
    assert len(row) >= 3
    gaps = [
        haversine_miles((a.lat, a.lon), (b.lat, b.lon)) for a, b in zip(row, row[1:], strict=False)
    ]
    assert all(g == pytest.approx(15.0, abs=0.1) for g in gaps)


def test_a_fixed_degree_grid_would_not_have_been_uniform():
    # documents why 0.25 deg is not used: its east-west width shrinks with latitude
    assert 0.25 * 69.09 * 0.766 > 0.25 * 69.09 * 0.5  # 40 N vs 60 N


def test_north_south_spacing_is_fifteen_miles():
    cells = corridor_cells([samples(line(40, -100, 41, -100))], 15.0, 20.0)
    col_cells = [c for c in cells if abs(c.lon + 100) < lon_step_deg(c.lat, 15.0)]
    lats = sorted({c.lat for c in col_cells})
    assert all(
        b - a == pytest.approx(lat_step_deg(15.0)) for a, b in zip(lats, lats[1:], strict=False)
    )


def test_cells_are_within_the_corridor_half_width():
    route = line(40, -100, 41, -97)
    cells = corridor_cells([samples(route)], 15.0, 20.0)
    assert cells
    pts = samples(route, 1.0)
    for c in cells:
        assert min(haversine_miles((c.lat, c.lon), p) for p in pts) <= 20.0 + 1e-6


def test_shared_stretches_are_not_double_counted():
    route = line(40, -100, 41, -97)
    one = corridor_cells([samples(route)], 15.0, 20.0)
    two = corridor_cells([samples(route), samples(route)], 15.0, 20.0)
    assert len(one) == len(two) and one == two


def test_lattice_is_global_and_deterministic():
    a = corridor_cells([samples(line(40, -100, 41, -97))], 15.0, 20.0)
    b = corridor_cells([samples(line(40.3, -99.0, 41.2, -96.5))], 15.0, 20.0)
    shared = {(c.row, c.col): (c.lat, c.lon) for c in a} | {}
    for c in b:
        if (c.row, c.col) in shared:
            assert shared[(c.row, c.col)] == (c.lat, c.lon)


def test_more_routes_extend_the_corridor():
    r1 = samples(line(40, -100, 41, -97))
    r2 = samples(line(40, -100, 39, -97))
    assert len(corridor_cells([r1, r2], 15.0, 20.0)) > len(corridor_cells([r1], 15.0, 20.0))


# ---- hourly levels ------------------------------------------------------------------------
def series_with(n=60, wind=None, rain=None):
    def build(default, overrides):
        v = [default] * n
        for k, x in (overrides or {}).items():
            v[k] = x
        return tuple(v)

    return HourlySeries(
        START,
        build(10.0, wind),
        build(12.0, None),
        build(0.0, rain),
        build(0.0, None),
        build(40.0, None),
    )


def test_hourly_levels_has_49_positions_and_hits_both_endpoints():
    levels = hourly_levels(series_with(), START, 1000)
    assert len(levels) == 49 and all(lv == RiskLevel.LOW for lv in levels)


def test_hour_zero_and_hour_48_reflect_their_own_forecast():
    series = series_with(wind={0: 60.0, 1: 60.0, 48: 60.0, 49: 60.0})
    levels = hourly_levels(series, START, 1000)
    assert levels[0] == RiskLevel.NO_TRAVEL and levels[48] == RiskLevel.NO_TRAVEL
    assert levels[24] == RiskLevel.LOW


def test_hourly_levels_are_load_aware():
    series = series_with(wind=dict.fromkeys(range(60), 40.0))  # 35-44 mph all the time
    assert set(hourly_levels(series, START, 30_000)) == {RiskLevel.HIGH}
    assert set(hourly_levels(series, START, 45_000)) == {RiskLevel.SEVERE}


def test_cell_without_data_is_unknown_every_hour():
    assert hourly_levels(None, START, 1000) == [None] * 49


def test_series_too_short_gives_unknown_not_low():
    levels = hourly_levels(series_with(n=10), START, 1000)
    assert levels[0] == RiskLevel.LOW and levels[48] is None


def test_levels_string_encoding():
    assert levels_string([RiskLevel.LOW, RiskLevel.NO_TRAVEL, None, RiskLevel.SEVERE]) == "0493"
    assert len(levels_string(hourly_levels(series_with(), START, 1000))) == 49


# ---- route de-duplication -----------------------------------------------------------------
def route(points, dist_m=1_000_000, dur_s=36_000):
    return RawRoute(tuple(points), dist_m, dur_s)


def test_identical_routes_are_duplicates():
    pts = line(40, -100, 41, -90)
    assert is_duplicate(route(pts), route(pts))
    assert len(dedupe([route(pts), route(pts, dur_s=36_500)])) == 1


def test_geometrically_distinct_routes_are_both_kept():
    a = line(40, -100, 41, -90)
    b = line(41.5, -100, 42.5, -90)  # ~100 miles north
    assert share_ratio(a, b) == 0.0
    assert len(dedupe([route(a), route(b)])) == 2


def test_same_corridor_but_very_different_time_is_kept():
    pts = line(40, -100, 41, -90)
    assert len(dedupe([route(pts, dur_s=36_000), route(pts, dur_s=50_000)])) == 2


def test_partially_shared_routes_are_kept():
    a = line(40, -100, 41, -90, n=100)
    b = a[:50] + line(a[49][0], a[49][1], 39, -90, n=50)[1:]
    assert 0.3 < share_ratio(b, a) < 0.8
    assert len(dedupe([route(a), route(b)])) == 2


def test_dedupe_keeps_the_faster_route_first():
    pts = line(40, -100, 41, -90)
    kept = dedupe([route(pts, dur_s=37_000), route(pts, dur_s=36_000)])
    assert [r.duration_s for r in kept] == [36_000]


def test_dedupe_never_invents_routes():
    pts = line(40, -100, 41, -90)
    assert dedupe([route(pts)]) == [route(pts)]
    assert dedupe([]) == []

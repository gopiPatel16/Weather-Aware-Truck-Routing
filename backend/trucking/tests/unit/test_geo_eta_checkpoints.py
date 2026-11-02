"""Geometry, polyline codec, ETA profile and checkpoint spacing."""

from datetime import UTC, datetime, timedelta

import pytest

from trucking.domain import polyline
from trucking.domain.checkpoints import build_checkpoints, checkpoint_miles, choose_interval
from trucking.domain.eta import ESTIMATED, GUIDANCE, build_time_profile
from trucking.domain.geo import (
    METERS_PER_MILE,
    MILES_PER_DEGREE,
    cumulative_miles,
    decimate,
    haversine_miles,
    point_at,
    sample_along,
    scale_to_length,
    simplify,
    slice_polyline,
)

DEP = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def line(lat0, lon0, lat1, lon1, n=11):
    return [
        (lat0 + (lat1 - lat0) * i / (n - 1), lon0 + (lon1 - lon0) * i / (n - 1)) for i in range(n)
    ]


# ---- geo ----------------------------------------------------------------------------------
def test_haversine_degree_of_latitude():
    assert haversine_miles((0, 0), (1, 0)) == pytest.approx(MILES_PER_DEGREE, rel=1e-6)
    assert haversine_miles((41.8781, -87.6298), (39.7392, -104.9903)) == pytest.approx(920, abs=10)


def test_decimate_keeps_ends_and_thins_dense_points():
    pts = line(40, -100, 40.01, -100, n=200)  # ~0.7 mi in 200 points
    out = decimate(pts, 50)
    assert out[0] == pts[0] and out[-1] == pts[-1] and len(out) < 40


def test_point_at_interpolates_and_clamps():
    pts = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = cumulative_miles(pts)
    assert point_at(pts, cum, -5) == pts[0] and point_at(pts, cum, 1e9) == pts[-1]
    assert point_at(pts, cum, cum[1] / 2)[1] == pytest.approx(0.5)
    assert point_at(pts, cum, cum[1] * 1.5)[1] == pytest.approx(1.5)


def test_scale_to_length_matches_provider_total():
    cum = cumulative_miles(line(40, -100, 41, -100))
    assert scale_to_length(cum, 100.0)[-1] == pytest.approx(100.0)
    with pytest.raises(ValueError):
        scale_to_length([0.0], 10)


def test_slice_polyline_has_interpolated_ends():
    pts = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
    cum = cumulative_miles(pts)
    piece = slice_polyline(pts, cum, cum[1] * 0.5, cum[1] * 1.5)
    assert (
        piece[0][1] == pytest.approx(0.5)
        and piece[-1][1] == pytest.approx(1.5)
        and (0.0, 1.0) in piece
    )


def test_sample_along_includes_end():
    pts = line(40, -100, 41, -100)
    cum = cumulative_miles(pts)
    samples = sample_along(pts, cum, 10)
    assert (
        samples[0] == pts[0] and samples[-1] == pts[-1] and len(samples) == 8
    )  # 0,10,...,60 plus the end (69.09 mi)


def test_simplify_keeps_corner_drops_collinear():
    pts = [(0.0, 0.0), (0.0, 0.5), (0.0, 1.0), (0.5, 1.0), (1.0, 1.0)]
    out = simplify(pts, 100)
    assert (0.0, 1.0) in out and (0.0, 0.5) not in out and (0.5, 1.0) not in out


# ---- polyline -----------------------------------------------------------------------------
def test_polyline_known_example():
    decoded = polyline.decode("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert decoded == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert polyline.encode(decoded) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


@pytest.mark.parametrize("precision", [5, 6, 7])
def test_polyline_roundtrip(precision):
    pts = [(41.8781, -87.6298), (41.8, -88.1), (39.7392, -104.9903)]
    back = polyline.decode(polyline.encode(pts, precision), precision)
    assert all(
        abs(a - c) < 10**-precision
        for p, q in zip(pts, back, strict=True)
        for a, c in zip(p, q, strict=True)
    )


# ---- ETA ----------------------------------------------------------------------------------
def test_guidance_profile_interpolates_between_offsets():
    # slow first half (3 h for 50 km), fast second half (1 h for 50 km)
    profile = build_time_profile([(0, 0), (50_000, 10_800), (100_000, 14_400)], 100_000, 14_400)
    assert profile.method == GUIDANCE
    assert profile.seconds_at(25_000) == pytest.approx(5_400)
    assert profile.seconds_at(75_000) == pytest.approx(12_600)
    assert profile.seconds_at(1e9) == 14_400


def test_missing_guidance_falls_back_and_is_flagged():
    profile = build_time_profile([], 100_000, 7_200)
    assert profile.method == ESTIMATED and profile.seconds_at(50_000) == pytest.approx(3_600)


@pytest.mark.parametrize(
    "offsets",
    [
        [(0, 0), (50_000, 5_000), (90_000, 4_000)],  # time goes backwards
        [(0, 0), (40_000, 3_000)],  # does not reach the end of the route
        [(0, 0), (100_000, 99_999)],  # more time than the route's total duration
        [(0, 0)],  # a single point
    ],
)
def test_unusable_guidance_falls_back(offsets):
    assert build_time_profile(offsets, 100_000, 7_200).method == ESTIMATED


def test_profile_is_monotonic():
    profile = build_time_profile(
        [(0, 0), (30_000, 2_000), (60_000, 2_000), (100_000, 7_000)], 100_000, 7_200
    )
    times = [profile.seconds_at(m) for m in range(0, 100_001, 5_000)]
    assert times == sorted(times)


# ---- checkpoints --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (100, 25, [0, 25, 50, 75, 100]),
        (101, 25, [0, 25, 50, 75, 101]),  # 100 is within N/4 of the end -> dropped
        (10, 25, [0, 10]),
        (1003.2, 25, [*range(0, 976, 25), 1003.2]),
        (100, 10, [*range(0, 91, 10), 100]),
        (96, 10, [*range(0, 91, 10), 96]),  # 90 <= 96 - 2.5, so it is kept
        (100, 50, [0, 50, 100]),
    ],
)
def test_checkpoint_miles(total, interval, expected):
    assert checkpoint_miles(total, interval) == pytest.approx(expected)


def test_checkpoint_miles_always_end_at_destination_and_never_clump():
    for total in (12.0, 49.9, 250.0, 333.3, 1003.2):
        for interval in (10, 25, 50):
            miles = checkpoint_miles(total, interval)
            assert miles[0] == 0 and miles[-1] == total
            gaps = [b - a for a, b in zip(miles, miles[1:], strict=False)]
            # start and destination always exist, so a very short route can be shorter than N/4
            assert all(g >= min(0.25 * interval, total) - 1e-9 for g in gaps)


def test_choose_interval_raises_only_when_over_the_cap():
    assert choose_interval(1000, 25) == (25, False)
    assert choose_interval(2900, 10) == (10, False)  # 291 checkpoints, under the cap of 300
    assert choose_interval(3500, 10) == (25, True)  # 351 checkpoints -> raised
    assert choose_interval(3500, 50) == (50, False)


def test_build_checkpoints_eta_and_ownership():
    pts = line(40, -100, 41.5, -100, n=50)
    cum = scale_to_length(cumulative_miles(pts), 100.0)
    profile = build_time_profile([], 100.0 * METERS_PER_MILE, 6000)  # 100 mi in 6000 s
    cps = build_checkpoints(pts, cum, profile, DEP, 25)
    assert [c.mile for c in cps] == pytest.approx([0, 25, 50, 75, 100])
    assert cps[0].eta_utc == DEP and cps[-1].eta_utc == DEP + timedelta(seconds=6000)
    assert [c.eta_utc for c in cps] == sorted(c.eta_utc for c in cps)
    assert cps[0].owns_from_mi == 0 and cps[-1].owns_to_mi == pytest.approx(100.0)
    assert sum(c.owned_miles for c in cps) == pytest.approx(100.0)
    assert (cps[1].owns_from_mi, cps[1].owns_to_mi) == pytest.approx((12.5, 37.5))
    assert cps[0].lat == pytest.approx(40.0) and cps[-1].lat == pytest.approx(41.5)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_ownership_always_sums_to_route_length(interval):
    pts = line(40, -100, 45, -90, n=80)
    cum = scale_to_length(cumulative_miles(pts), 777.7)
    profile = build_time_profile([], 777.7 * METERS_PER_MILE, 40_000)
    cps = build_checkpoints(pts, cum, profile, DEP, interval)
    assert sum(c.owned_miles for c in cps) == pytest.approx(777.7)

"""Request validation. Responses are plain dicts built by the planner (documented in the OpenAPI)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rest_framework import serializers

from trucking import config
from trucking.domain import polyline
from trucking.domain.geo import cumulative_miles
from trucking.planner import Place, PlanInput


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200, allow_blank=True, default="")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


def _place(data: dict[str, Any]) -> Place:
    return Place(data["label"], data["lat"], data["lon"])


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure_local = serializers.CharField(
        help_text="Local time at the ORIGIN, e.g. 2026-11-02T06:00 (no UTC offset)."
    )
    cargo_weight_lb = serializers.FloatField(min_value=1, max_value=config.MAX_CARGO_LB)
    interval_miles = serializers.IntegerField(default=config.DEFAULT_INTERVAL_MILES)

    def validate_departure_local(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise serializers.ValidationError("Use the format YYYY-MM-DDTHH:MM.") from exc
        if parsed.tzinfo is not None:
            raise serializers.ValidationError("Send the origin's local time without a UTC offset.")
        return parsed

    def validate_interval_miles(self, value: int) -> int:
        if value not in config.INTERVAL_OPTIONS:
            raise serializers.ValidationError(
                f"Choose one of {list(config.INTERVAL_OPTIONS)} miles."
            )
        return value

    def to_input(self) -> PlanInput:
        d = self.validated_data
        return PlanInput(
            _place(d["origin"]),
            _place(d["destination"]),
            d["departure_local"],
            d["cargo_weight_lb"],
            d["interval_miles"],
        )


class HeatmapRouteSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=8)
    polyline = serializers.CharField(max_length=400_000)


class HeatmapRequestSerializer(serializers.Serializer):
    routes = HeatmapRouteSerializer(many=True, allow_empty=False, max_length=3)
    departure_utc = serializers.CharField()
    cargo_weight_lb = serializers.FloatField(min_value=1, max_value=config.MAX_CARGO_LB)

    def validate_departure_utc(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise serializers.ValidationError(
                "Use an ISO 8601 UTC time such as 2026-11-02T12:00:00Z."
            ) from exc
        if parsed.tzinfo is None:
            raise serializers.ValidationError("departure_utc must include a UTC offset (Z).")
        return parsed.astimezone(UTC)

    def validate_routes(
        self, routes: list[dict[str, Any]]
    ) -> list[tuple[str, list[tuple[float, float]]]]:
        decoded = []
        for route in routes:
            try:
                points = polyline.decode(route["polyline"])
            except (IndexError, ValueError) as exc:
                raise serializers.ValidationError(
                    f"Route {route['id']}: invalid polyline."
                ) from exc
            if len(points) < 2 or len(points) > 60_000:
                raise serializers.ValidationError(
                    f"Route {route['id']}: polyline must have 2-60000 points."
                )
            if cumulative_miles(points)[-1] > config.MAX_ROUTE_MILES * 1.1:
                raise serializers.ValidationError(f"Route {route['id']}: route is too long.")
            decoded.append((route["id"], points))
        return decoded

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from trucking import container
from trucking.domain.timezones import TimeZoneLookupError, tz_name_at
from trucking.errors import ApiError
from trucking.services.routing.base import RoutingError

from .serializers import HeatmapRequestSerializer, PlanRequestSerializer


class HealthView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class PlanView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "plan"

    @extend_schema(
        request=PlanRequestSerializer,
        responses={200: OpenApiTypes.OBJECT},
        description="Routes, checkpoints, risk, eligibility and recommendation. See docs/PLAN.md section 7.",
    )
    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(container.get_planner().plan(serializer.to_input()))


class HeatmapView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "plan"

    @extend_schema(
        request=HeatmapRequestSerializer,
        responses={200: OpenApiTypes.OBJECT},
        description="Hourly risk level (hours 0-48 after departure) for corridor cells, one character per hour.",
    )
    def post(self, request: Request) -> Response:
        serializer = HeatmapRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            container.get_planner().heatmap(
                data["routes"], data["departure_utc"], data["cargo_weight_lb"]
            )
        )


class GeocodeView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "geocode"

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Place name or address (min 2 characters)")
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            raise ApiError(
                "validation_error", "Type at least 2 characters.", 400, fields={"q": ["Too short."]}
            )
        try:
            hits = container.get_geocoder().search(query[:120])
        except RoutingError as exc:
            raise ApiError(
                exc.code, exc.message, exc.status, retry_after_s=exc.retry_after_s
            ) from exc
        results: list[dict[str, Any]] = []
        for hit in hits:
            try:
                zone = tz_name_at(hit.lat, hit.lon)
            except TimeZoneLookupError:
                continue
            results.append(
                {
                    "label": hit.label,
                    "lat": round(hit.lat, 5),
                    "lon": round(hit.lon, 5),
                    "timezone": zone,
                }
            )
        return Response({"results": results})

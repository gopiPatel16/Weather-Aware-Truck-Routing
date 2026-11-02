"""Maps every failure to the documented JSON shape ``{"error": {"code", "message", ...}}``."""

from __future__ import annotations

import logging
import math
from typing import Any

from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from trucking.errors import ApiError

log = logging.getLogger(__name__)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, ApiError):
        return Response(exc.payload(), status=exc.status)
    if isinstance(exc, exceptions.ValidationError):
        error = ApiError(
            "validation_error", "Some fields are invalid.", 400, fields={"detail": exc.detail}
        )
        payload = error.payload()
        payload["error"]["fields"] = exc.detail
        return Response(payload, status=400)
    if isinstance(exc, exceptions.Throttled):
        wait = math.ceil(exc.wait) if exc.wait else 30
        return Response(
            ApiError(
                "rate_limited", "Too many requests. Please wait a moment.", 429, retry_after_s=wait
            ).payload(),
            status=429,
        )
    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = (
            response.data.get("detail", "Request failed.")
            if isinstance(response.data, dict)
            else "Request failed."
        )
        response.data = ApiError("http_error", str(detail), response.status_code).payload()
        return response
    log.exception("Unhandled error in %s", context.get("view"))
    return Response(
        ApiError("internal_error", "Something went wrong on the server.", 500).payload(), status=500
    )

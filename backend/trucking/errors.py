"""One error type for everything the API reports to the user."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Rendered as ``{"error": {"code", "message", "retry_after_s?", "fields?"}}``."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        *,
        retry_after_s: int | None = None,
        fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after_s = retry_after_s
        self.fields = fields

    def payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.retry_after_s is not None:
            body["retry_after_s"] = self.retry_after_s
        if self.fields:
            body["fields"] = self.fields
        return {"error": body}

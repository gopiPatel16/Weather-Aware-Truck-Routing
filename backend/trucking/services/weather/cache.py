"""Cache adapters for the service layer."""

from __future__ import annotations

import time
from typing import Any


class DictCache:
    """Simple in-memory cache with TTL (tests and fallback)."""

    def __init__(self, clock: Any = time.monotonic) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._clock = clock

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None or item[0] < self._clock():
            return None
        return item[1]

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        self._data[key] = (self._clock() + ttl_s, value)


class DjangoCache:
    """Adapter over ``django.core.cache`` (LocMem in this app)."""

    def __init__(self) -> None:
        from django.core.cache import cache

        self._cache = cache

    def get(self, key: str) -> Any | None:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        self._cache.set(key, value, ttl_s)

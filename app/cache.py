from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Hashable, Optional, Tuple


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl_seconds: float, maxsize: int = 1024) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.maxsize = max(1, int(maxsize))
        self._data: Dict[Hashable, CacheEntry] = {}
        self._locks: Dict[Hashable, asyncio.Lock] = {}

    def get(self, key: Hashable) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._data.pop(key, None)
            return None
        return entry.value

    def set(self, key: Hashable, value: Any, ttl_seconds: Optional[float] = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))
        if ttl <= 0:
            return
        expires_at = time.monotonic() + ttl
        self._data[key] = CacheEntry(value=value, expires_at=expires_at)
        self._prune()

    async def get_or_set(
        self,
        key: Hashable,
        factory: Callable[[], Awaitable[Any]],
    ) -> Tuple[Any, bool]:
        value = self.get(key)
        if value is not None:
            return value, True

        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                value = self.get(key)
                if value is not None:
                    return value, True
                value = await factory()
                self.set(key, value)
                return value, False
        finally:
            # Best-effort cleanup to avoid unbounded lock growth.
            if key in self._locks and not self._locks[key].locked():
                self._locks.pop(key, None)

    def _prune(self) -> None:
        if len(self._data) <= self.maxsize:
            return
        now = time.monotonic()
        expired = [k for k, v in self._data.items() if v.expires_at <= now]
        for k in expired:
            self._data.pop(k, None)
        if len(self._data) <= self.maxsize:
            return
        # Drop entries with earliest expiration first
        over = len(self._data) - self.maxsize
        for k, _ in sorted(self._data.items(), key=lambda kv: kv[1].expires_at)[:over]:
            self._data.pop(k, None)

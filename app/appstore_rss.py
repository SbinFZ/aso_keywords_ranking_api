from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

from .cache import TTLCache
from .utils import utc_now_iso


RSS_BASE = "https://rss.applemarketingtools.com"

_CACHE_ENABLED = os.getenv("APPSTORE_CACHE_ENABLED", "1").lower() not in {"0", "false", "no"}
_CACHE_MAXSIZE = int(os.getenv("APPSTORE_CACHE_MAXSIZE", "2048"))
_RSS_TTL = float(os.getenv("APPSTORE_CACHE_TTL_RSS", "300"))
_RSS_CACHE = TTLCache(_RSS_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _RSS_TTL > 0 else None

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_HTTP_RETRIES = int(os.getenv("APPSTORE_HTTP_RETRIES", "2"))
_HTTP_BACKOFF = float(os.getenv("APPSTORE_HTTP_BACKOFF", "0.3"))

_ALLOWED_MEDIA = {"apps"}
_ALLOWED_FEEDS = {"top-free", "top-paid", "top-grossing"}
_ALLOWED_TYPES = {"apps"}
_ALLOWED_LIMITS = {10, 25, 50}


async def _request_with_retries(
    client: httpx.AsyncClient,
    url: str,
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(_HTTP_RETRIES + 1):
        try:
            resp = await client.get(url)
            if resp.status_code in _RETRYABLE_STATUS:
                raise httpx.HTTPStatusError("Retryable status", request=resp.request, response=resp)
            resp.raise_for_status()
            return resp
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    raise
            if attempt >= _HTTP_RETRIES:
                raise
            await asyncio.sleep(_HTTP_BACKOFF * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError("request failed without exception")


def _normalize_country(country: str) -> str:
    return (country or "US").lower()


def _validate_limit(limit: int) -> int:
    limit = int(limit)
    if limit not in _ALLOWED_LIMITS:
        raise ValueError(f"limit must be one of {sorted(_ALLOWED_LIMITS)}")
    return limit


def _validate_enum(value: str, allowed: set, label: str) -> str:
    if value not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)}")
    return value


async def fetch_appstore_rss(
    client: httpx.AsyncClient,
    *,
    country: str = "us",
    media: str = "apps",
    feed: str = "top-free",
    limit: int = 10,
    type_: str = "apps",
    use_cache: bool = True,
) -> Dict[str, Any]:
    country = _normalize_country(country)
    media = _validate_enum(media, _ALLOWED_MEDIA, "media")
    feed = _validate_enum(feed, _ALLOWED_FEEDS, "feed")
    limit = _validate_limit(limit)
    type_ = _validate_enum(type_, _ALLOWED_TYPES, "type")

    url = f"{RSS_BASE}/api/v2/{country}/{media}/{feed}/{limit}/{type_}.json"
    cache_key = (country, media, feed, limit, type_)

    async def _fetch() -> Dict[str, Any]:
        resp = await _request_with_retries(client, url)
        payload = resp.json()
        return {
            "country": country.upper(),
            "media": media,
            "feed": feed,
            "limit": limit,
            "type": type_,
            "url": url,
            "feed_data": payload,
            "fetched_at": utc_now_iso(),
        }

    if use_cache and _RSS_CACHE is not None:
        data, _ = await _RSS_CACHE.get_or_set(cache_key, _fetch)
        return data
    return await _fetch()

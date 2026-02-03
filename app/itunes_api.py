from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

from .cache import TTLCache
from .utils import normalize_keyword, utc_now_iso


ITUNES_BASE = "https://itunes.apple.com"

_CACHE_ENABLED = os.getenv("APPSTORE_CACHE_ENABLED", "1").lower() not in {"0", "false", "no"}
_CACHE_MAXSIZE = int(os.getenv("APPSTORE_CACHE_MAXSIZE", "2048"))
_SEARCH_TTL = float(os.getenv("APPSTORE_CACHE_TTL_ITUNES_SEARCH", "300"))
_LOOKUP_TTL = float(os.getenv("APPSTORE_CACHE_TTL_ITUNES_LOOKUP", "300"))

_SEARCH_CACHE = TTLCache(_SEARCH_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _SEARCH_TTL > 0 else None
_LOOKUP_CACHE = TTLCache(_LOOKUP_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _LOOKUP_TTL > 0 else None

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_HTTP_RETRIES = int(os.getenv("APPSTORE_HTTP_RETRIES", "2"))
_HTTP_BACKOFF = float(os.getenv("APPSTORE_HTTP_BACKOFF", "0.3"))


async def _request_with_retries(
    client: httpx.AsyncClient,
    url: str,
    params: Dict[str, Any],
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(_HTTP_RETRIES + 1):
        try:
            resp = await client.get(url, params=params)
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
    return (country or "US").upper()


def _validate_limit(limit: int) -> int:
    limit = int(limit)
    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    return limit


def _validate_offset(offset: int) -> int:
    offset = int(offset)
    if offset < 0:
        raise ValueError("offset must be >= 0")
    return offset


def _validate_explicit(explicit: Optional[str]) -> Optional[str]:
    if explicit is None:
        return None
    if explicit not in {"Yes", "No"}:
        raise ValueError("explicit must be 'Yes' or 'No'")
    return explicit


async def itunes_search(
    client: httpx.AsyncClient,
    term: str,
    *,
    country: str = "US",
    media: Optional[str] = None,
    entity: Optional[str] = "software",
    attribute: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    lang: Optional[str] = None,
    explicit: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    term = (term or "").strip()
    if not term:
        raise ValueError("term is required")
    limit = _validate_limit(limit)
    offset = _validate_offset(offset)
    country = _normalize_country(country)

    cache_key = (
        "search",
        country,
        normalize_keyword(term),
        media or "",
        entity or "",
        attribute or "",
        limit,
        offset,
        lang or "",
        explicit or "",
    )

    async def _fetch() -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "term": term,
            "country": country,
            "limit": limit,
            "offset": offset,
        }
        if media:
            params["media"] = media
        if entity:
            params["entity"] = entity
        if attribute:
            params["attribute"] = attribute
        if lang:
            params["lang"] = lang
    explicit = _validate_explicit(explicit)
    if explicit:
        params["explicit"] = explicit

        resp = await _request_with_retries(client, f"{ITUNES_BASE}/search", params=params)
        payload = resp.json()
        return {
            "term": term,
            "country": country,
            "request": params,
            "result_count": payload.get("resultCount", 0),
            "results": payload.get("results", []),
            "fetched_at": utc_now_iso(),
        }

    if use_cache and _SEARCH_CACHE is not None:
        data, _ = await _SEARCH_CACHE.get_or_set(cache_key, _fetch)
        return data
    return await _fetch()


async def itunes_lookup(
    client: httpx.AsyncClient,
    *,
    country: str = "US",
    id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    entity: Optional[str] = None,
    limit: Optional[int] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    country = _normalize_country(country)
    if not id and not bundle_id:
        raise ValueError("id or bundle_id is required")
    params: Dict[str, Any] = {"country": country}
    if id:
        params["id"] = str(id)
    if bundle_id:
        params["bundleId"] = bundle_id
    if entity:
        params["entity"] = entity
    if limit is not None:
        params["limit"] = _validate_limit(limit)

    cache_key = (
        "lookup",
        country,
        str(id or ""),
        bundle_id or "",
        entity or "",
        str(limit or ""),
    )

    async def _fetch() -> Dict[str, Any]:
        resp = await _request_with_retries(client, f"{ITUNES_BASE}/lookup", params=params)
        payload = resp.json()
        return {
            "country": country,
            "request": params,
            "result_count": payload.get("resultCount", 0),
            "results": payload.get("results", []),
            "fetched_at": utc_now_iso(),
        }

    if use_cache and _LOOKUP_CACHE is not None:
        data, _ = await _LOOKUP_CACHE.get_or_set(cache_key, _fetch)
        return data
    return await _fetch()

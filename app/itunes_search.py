from __future__ import annotations

import asyncio
import os
from typing import Dict, Any, Optional

import httpx

from .cache import TTLCache
from .utils import normalize_keyword, utc_now_iso


_CACHE_ENABLED = os.getenv("APPSTORE_CACHE_ENABLED", "1").lower() not in {"0", "false", "no"}
_CACHE_MAXSIZE = int(os.getenv("APPSTORE_CACHE_MAXSIZE", "2048"))
_SEARCH_TTL = float(os.getenv("APPSTORE_CACHE_TTL_SEARCH", "300"))
_SEARCH_CACHE = TTLCache(_SEARCH_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _SEARCH_TTL > 0 else None

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

async def fetch_search_rank(
    client: httpx.AsyncClient,
    keyword: str,
    target_app_id: str,
    country: str = "US",
    *,
    max_rank: int = 200,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Search iTunes API for a keyword and find the rank of target_app_id.
    Returns: {
        "total_results": int,   # count from the first page (API does not expose true total)
        "scanned_results": int, # how many results we scanned
        "rank": int | None,     # None if not found in top N
        "top_app": str | None   # Name of the #1 app
    }
    """
    keyword = (keyword or "").strip()
    country = (country or "US").upper()
    max_rank = max(1, int(max_rank))
    cache_key = (country, normalize_keyword(keyword), str(target_app_id), max_rank)

    async def _fetch() -> Dict[str, Any]:
        url = "https://itunes.apple.com/search"
        limit = min(200, max_rank)
        offset = 0
        scanned = 0
        rank = None
        top_app = None
        first_page_count = 0

        while offset < max_rank:
            params = {
                "term": keyword,
                "country": country,
                "entity": "software",
                "limit": limit,
                "offset": offset,
            }
            resp = await _request_with_retries(client, url, params=params)
            data = resp.json()

            results = data.get("results", [])
            result_count = data.get("resultCount", 0)
            if offset == 0:
                first_page_count = result_count
                top_app = results[0].get("trackName") if results else None

            for i, item in enumerate(results):
                scanned += 1
                if str(item.get("trackId")) == str(target_app_id):
                    rank = offset + i + 1
                    break
            if rank is not None:
                break

            if result_count < limit:
                break
            offset += limit

        return {
            "total_results": first_page_count,
            "scanned_results": scanned,
            "rank": rank,
            "top_app": top_app,
            "fetched_at": utc_now_iso(),
        }

    try:
        if use_cache and _SEARCH_CACHE is not None:
            data, _ = await _SEARCH_CACHE.get_or_set(cache_key, _fetch)
            return data
        return await _fetch()
    except Exception as e:
        print(f"Search error for {keyword}: {e}")
        return {
            "total_results": -1,
            "scanned_results": 0,
            "rank": None,
            "top_app": None,
            "error": str(e),
            "fetched_at": utc_now_iso(),
        }

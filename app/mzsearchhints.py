# app/mzsearchhints.py
from __future__ import annotations

import asyncio
import json
import math
import os
import plistlib
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .cache import TTLCache
from .storefronts import STOREFRONT_BY_COUNTRY
from .utils import normalize_keyword, utc_now_iso


MZ_HINTS_BASE = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa"

_CACHE_ENABLED = os.getenv("APPSTORE_CACHE_ENABLED", "1").lower() not in {"0", "false", "no"}
_CACHE_MAXSIZE = int(os.getenv("APPSTORE_CACHE_MAXSIZE", "2048"))
_HINTS_TTL = float(os.getenv("APPSTORE_CACHE_TTL_HINTS", "300"))
_TRENDS_TTL = float(os.getenv("APPSTORE_CACHE_TTL_TRENDS", "300"))
_POP_TTL = float(os.getenv("APPSTORE_CACHE_TTL_POPULARITY", "300"))

_HINTS_CACHE = TTLCache(_HINTS_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _HINTS_TTL > 0 else None
_TRENDS_CACHE = TTLCache(_TRENDS_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _TRENDS_TTL > 0 else None
_POP_CACHE = TTLCache(_POP_TTL, _CACHE_MAXSIZE) if _CACHE_ENABLED and _POP_TTL > 0 else None

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_HTTP_RETRIES = int(os.getenv("APPSTORE_HTTP_RETRIES", "2"))
_HTTP_BACKOFF = float(os.getenv("APPSTORE_HTTP_BACKOFF", "0.3"))

_LANGUAGE_BY_COUNTRY = {
    "US": "en-US",
    "GB": "en-GB",
    "CA": "en-CA",
    "AU": "en-AU",
    "CN": "zh-CN",
    "TW": "zh-TW",
    "HK": "zh-HK",
    "JP": "ja-JP",
    "KR": "ko-KR",
    "FR": "fr-FR",
    "DE": "de-DE",
    "IT": "it-IT",
    "ES": "es-ES",
    "PT": "pt-PT",
    "BR": "pt-BR",
    "RU": "ru-RU",
    "TR": "tr-TR",
}

def _parse_overrides(env_value: str) -> Dict[str, str]:
    """
    APPSTORE_STOREFRONT_OVERRIDES="US=143441-1,29;CN=143465-19,29"
    """
    out: Dict[str, str] = {}
    if not env_value:
        return out
    parts = [p.strip() for p in env_value.split(";") if p.strip()]
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip().upper()] = v.strip()
    return out

def resolve_storefront(country: str) -> str:
    country = (country or "US").upper()
    overrides = _parse_overrides(os.getenv("APPSTORE_STOREFRONT_OVERRIDES", ""))
    if country in overrides:
        return overrides[country]
    return STOREFRONT_BY_COUNTRY.get(country, STOREFRONT_BY_COUNTRY["US"])

def priority_to_normalized_score(priority: int) -> float:
    """
    把 priority（可能是几千到几万/更高）压缩到 0~100，便于前端展示。
    这里用 log10 做一个温和压缩：priority ~ 10^5 时接近 100 分。
    """
    if priority <= 0:
        return 0.0
    score = 20.0 * math.log10(priority + 1)  # 10^5 -> 100
    return float(max(0.0, min(100.0, round(score, 2))))

def _headers(country: str) -> Dict[str, str]:
    storefront = resolve_storefront(country)
    ua = os.getenv("APPSTORE_USER_AGENT", "AppStore/3.0 iOS/14.4 model/iPhone13,2 hwp/t8101 build/18D52 (6; dt:202)")
    accept_language = os.getenv("APPSTORE_ACCEPT_LANGUAGE", "") or _LANGUAGE_BY_COUNTRY.get(country.upper(), "en-US")
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "Accept-Language": accept_language,
        "X-Apple-Store-Front": storefront,
    }

def _loads_plist(content: bytes) -> Any:
    # MZSearchHints 返回通常是 plist（XML / binary）
    try:
        return plistlib.loads(content)
    except Exception:
        # Fallback to JSON if plist fails (sometimes Apple returns JSON)
        try:
            return json.loads(content)
        except Exception:
            raise


def _extract_terms(obj: Any) -> List[Dict[str, Any]]:
    """
    兼容几种常见返回：
    - list[dict(term, priority, url, ...)]
    - dict 包含 array（少见）
    """
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        # 尝试找一个 list 值
        for v in obj.values():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []

async def _request_with_retries(
    client: httpx.AsyncClient,
    url: str,
    params: Dict[str, Any],
    headers: Dict[str, str],
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(_HTTP_RETRIES + 1):
        try:
            resp = await client.get(url, params=params, headers=headers)
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


def _apply_max_count(items: List[Dict[str, Any]], max_count: Optional[int]) -> List[Dict[str, Any]]:
    if max_count is not None and max_count > 0:
        return items[:max_count]
    return items


def _strip_raw(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in item.items() if k != "raw"} for item in items]


async def fetch_trends(
    client: httpx.AsyncClient,
    country: str = "US",
    max_count: int = 10,
    *,
    use_cache: bool = True,
    include_raw: bool = True,
) -> List[Dict[str, Any]]:
    # 社区常用：/trends?maxCount=10，需带 X-Apple-Store-Front :contentReference[oaicite:4]{index=4}
    country = (country or "US").upper()
    cache_key = (country, int(max_count))

    async def _fetch() -> List[Dict[str, Any]]:
        url = f"{MZ_HINTS_BASE}/trends"
        r = await _request_with_retries(
            client,
            url,
            params={"maxCount": str(max_count)},
            headers=_headers(country),
        )
        data = _loads_plist(r.content)
        items = _extract_terms(data)
        # 统一字段
        out: List[Dict[str, Any]] = []
        for idx, it in enumerate(items):
            term = it.get("term") or it.get("displayTerm") or it.get("text")
            priority = it.get("priority")
            if term is None:
                continue
            try:
                p = int(priority) if priority is not None else 0
            except Exception:
                p = 0
            out.append({
                "term": str(term),
                "priority": p,
                "normalized_score": priority_to_normalized_score(p),
                "hint_rank": idx + 1,
                "raw": it,
            })
        return out

    if use_cache and _TRENDS_CACHE is not None:
        items, _ = await _TRENDS_CACHE.get_or_set(cache_key, _fetch)
    else:
        items = await _fetch()

    items = _apply_max_count(items, max_count)
    if not include_raw:
        items = _strip_raw(items)
    return items

async def fetch_hints(
    client: httpx.AsyncClient,
    keyword: str,
    country: str = "US",
    max_count: Optional[int] = None,
    *,
    use_cache: bool = True,
    include_raw: bool = True,
) -> List[Dict[str, Any]]:
    # 社区常用：/hints?clientApplication=Software&term=NBA :contentReference[oaicite:5]{index=5}
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    country = (country or "US").upper()
    cache_key = (country, normalize_keyword(keyword))

    async def _fetch() -> List[Dict[str, Any]]:
        url = f"{MZ_HINTS_BASE}/hints"
        params = {
            "clientApplication": "Software",
            "term": keyword,
        }
        r = await _request_with_retries(
            client,
            url,
            params=params,
            headers=_headers(country),
        )
        data = _loads_plist(r.content)
        items = _extract_terms(data)

        out: List[Dict[str, Any]] = []
        for it in items:
            term = it.get("term") or it.get("displayTerm") or it.get("text")
            priority = it.get("priority")
            if term is None:
                continue
            try:
                p = int(priority) if priority is not None else 0
            except Exception:
                p = 0
            out.append({
                "term": str(term),
                "priority": p,
                "normalized_score": priority_to_normalized_score(p),
                "raw": it,
            })

        # 一般 priority 越大越“热”，这里按 priority 降序
        out.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return out

    if use_cache and _HINTS_CACHE is not None:
        items, _ = await _HINTS_CACHE.get_or_set(cache_key, _fetch)
    else:
        items = await _fetch()

    items = _apply_max_count(items, max_count)
    if not include_raw:
        items = _strip_raw(items)
    return items


def _best_approx_match(hints: List[Dict[str, Any]], kw_norm: str) -> Tuple[Optional[Dict[str, Any]], str]:
    if not hints:
        return None, "none"
    for item in hints:
        if normalize_keyword(item.get("term", "")) == kw_norm:
            return item, "exact"
    for item in hints:
        if normalize_keyword(item.get("term", "")).startswith(kw_norm):
            return item, "prefix"
    for item in hints:
        if kw_norm in normalize_keyword(item.get("term", "")):
            return item, "contains"
    return hints[0], "top"

async def fetch_keyword_popularity(
    client: httpx.AsyncClient,
    keyword: str,
    country: str = "US",
    *,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    取“keyword 本身”的 popularity：
    - 优先找 hints 返回里 term == keyword（忽略大小写）
    - 如果找不到，就用 hints 中最接近的词（前缀/包含/Top）作为近似
    - 当上游未提供 priority 时，使用排名估算，并标记为 estimated
    """
    keyword = (keyword or "").strip()
    country = (country or "US").upper()
    cache_key = (country, normalize_keyword(keyword))

    async def _fetch() -> Dict[str, Any]:
        hints = await fetch_hints(client, keyword=keyword, country=country, max_count=None, use_cache=use_cache)
        kw_norm = normalize_keyword(keyword)
        exact = next((x for x in hints if normalize_keyword(x.get("term", "")) == kw_norm), None)

        if exact:
            priority_raw = int(exact.get("priority") or 0)
            priority = priority_raw
            normalized_score = float(exact.get("normalized_score") or 0.0)
            priority_is_estimated = False
            score_method = "priority"

            if priority_raw == 0:
                hint_rank = exact.get("hint_rank") or 0
                if hint_rank > 0:
                    priority = max(10, 100 - ((hint_rank - 1) * 10))
                    normalized_score = float(priority)
                    priority_is_estimated = True
                    score_method = "rank_estimated"

            return {
                "keyword": keyword,
                "country": country,
                "priority": priority,
                "priority_raw": priority_raw,
                "priority_is_estimated": priority_is_estimated,
                "normalized_score": normalized_score,
                "score_method": score_method,
                "exact_match": True,
                "match_type": "exact",
                "source": "MZSearchHints.hints(priority)" if score_method == "priority" else "MZSearchHints.hints(rank_estimated)",
                "hints_top": hints[:10],
                "fetched_at": utc_now_iso(),
            }

        best, match_type = _best_approx_match(hints, kw_norm)
        if best is None:
            return {
                "keyword": keyword,
                "country": country,
                "priority": 0,
                "priority_raw": 0,
                "priority_is_estimated": False,
                "normalized_score": 0.0,
                "score_method": "none",
                "exact_match": False,
                "match_type": "none",
                "source": "MZSearchHints.hints(empty)",
                "hints_top": [],
                "fetched_at": utc_now_iso(),
            }

        priority_raw = int(best.get("priority") or 0)
        priority = priority_raw
        normalized_score = float(best.get("normalized_score") or 0.0)
        priority_is_estimated = True
        score_method = "approximate_priority"

        if priority_raw == 0:
            hint_rank = best.get("hint_rank") or 1
            priority = max(10, 100 - ((hint_rank - 1) * 10))
            normalized_score = float(priority)
            score_method = "approximate_rank_estimated"

        return {
            "keyword": keyword,
            "country": country,
            "priority": priority,
            "priority_raw": priority_raw,
            "priority_is_estimated": priority_is_estimated,
            "normalized_score": normalized_score,
            "score_method": score_method,
            "exact_match": False,
            "match_type": match_type,
            "source": "MZSearchHints.hints(approximate)",
            "hints_top": hints[:10],
            "fetched_at": utc_now_iso(),
        }

    if use_cache and _POP_CACHE is not None:
        data, _ = await _POP_CACHE.get_or_set(cache_key, _fetch)
        return data
    return await _fetch()

# app/mzsearchhints.py
from __future__ import annotations

import os
import math
import plistlib
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .storefronts import STOREFRONT_BY_COUNTRY


MZ_HINTS_BASE = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa"

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
    return {
        "User-Agent": ua,
        "Accept": "*/*",
        "X-Apple-Store-Front": storefront,
    }

import json

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

async def fetch_trends(client: httpx.AsyncClient, country: str = "US", max_count: int = 10) -> List[Dict[str, Any]]:
    # 社区常用：/trends?maxCount=10，需带 X-Apple-Store-Front :contentReference[oaicite:4]{index=4}
    url = f"{MZ_HINTS_BASE}/trends"
    r = await client.get(url, params={"maxCount": str(max_count)}, headers=_headers(country))
    r.raise_for_status()
    data = _loads_plist(r.content)
    items = _extract_terms(data)
    # 统一字段
    out = []
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
    return out

async def fetch_hints(
    client: httpx.AsyncClient,
    keyword: str,
    country: str = "US",
    max_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    # 社区常用：/hints?clientApplication=Software&term=NBA :contentReference[oaicite:5]{index=5}
    url = f"{MZ_HINTS_BASE}/hints"
    params = {
        "clientApplication": "Software",
        "term": keyword,
    }
    r = await client.get(url, params=params, headers=_headers(country))
    r.raise_for_status()
    data = _loads_plist(r.content)
    items = _extract_terms(data)

    out = []
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

    if max_count is not None and max_count > 0:
        out = out[:max_count]
    return out

async def fetch_keyword_popularity(
    client: httpx.AsyncClient,
    keyword: str,
    country: str = "US",
) -> Dict[str, Any]:
    """
    取“keyword 本身”的 popularity：
    - 优先找 hints 返回里 term == keyword（忽略大小写）
    - 如果找不到，就用 hints 的最高 priority 作为近似，并标记 exact_match=false
    """
    hints = await fetch_hints(client, keyword=keyword, country=country, max_count=None)
    kw_norm = keyword.strip().lower()

    exact = next((x for x in hints if x["term"].strip().lower() == kw_norm), None)
    if exact:
        # Fallback: if priority is 0, use rank-based score
        priority = exact["priority"]
        if priority == 0:
            # Find index
            try:
                idx = next(i for i, x in enumerate(hints) if x["term"].strip().lower() == kw_norm)
                # Synthetic score: 100 for #1, 90 for #2, ... min 10
                priority = max(10, 100 - (idx * 10))
                exact["normalized_score"] = float(priority)
                exact["priority"] = priority
            except StopIteration:
                pass

        return {
            "keyword": keyword,
            "country": country.upper(),
            "priority": exact["priority"],
            "normalized_score": exact["normalized_score"],
            "exact_match": True,
            "source": "MZSearchHints.hints(priority)" if exact["priority"] > 100 else "MZSearchHints.hints(rank_based)",
            "hints_top": hints[:10],
        }

    best = hints[0] if hints else None
    return {
        "keyword": keyword,
        "country": country.upper(),
        "priority": (best["priority"] if best else 0),
        "normalized_score": (best["normalized_score"] if best else 0.0),
        "exact_match": False,
        "source": "MZSearchHints.hints(priority,approx)",
        "hints_top": hints[:10],
    }


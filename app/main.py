# app/main.py
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query

from .mzsearchhints import fetch_hints, fetch_trends, fetch_keyword_popularity


TIMEOUT = float(os.getenv("APPSTORE_HTTP_TIMEOUT", "10"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        app.state.http = client
        yield

app = FastAPI(title="App Store Keyword Service", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/v1/keywords/trends")
async def api_trends(
    country: str = Query("US", min_length=2, max_length=2),
    max_count: int = Query(10, ge=1, le=100),
):
    try:
        return {
            "country": country.upper(),
            "items": await fetch_trends(app.state.http, country=country, max_count=max_count),
            "source": "MZSearchHints.trends",
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/keywords/hints")
async def api_hints(
    keyword: str = Query(..., min_length=1, max_length=100),
    country: str = Query("US", min_length=2, max_length=2),
    max_count: Optional[int] = Query(10, ge=1, le=100),
):
    try:
        items = await fetch_hints(app.state.http, keyword=keyword, country=country, max_count=max_count)
        return {
            "keyword": keyword,
            "country": country.upper(),
            "items": items,
            "source": "MZSearchHints.hints",
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/keywords/popularity")
async def api_popularity(
    keyword: str = Query(..., min_length=1, max_length=100),
    country: str = Query("US", min_length=2, max_length=2),
):
    try:
        return await fetch_keyword_popularity(app.state.http, keyword=keyword, country=country)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


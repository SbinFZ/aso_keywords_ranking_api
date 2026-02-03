# app/main.py
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query, Header
from pydantic import BaseModel

from .mzsearchhints import fetch_hints, fetch_trends, fetch_keyword_popularity
from .itunes_api import itunes_search, itunes_lookup
from .appstore_rss import fetch_appstore_rss
from .asa_api import asa_request


TIMEOUT = float(os.getenv("APPSTORE_HTTP_TIMEOUT", "10"))
CONNECT_TIMEOUT = float(os.getenv("APPSTORE_CONNECT_TIMEOUT", "5"))
POOL_TIMEOUT = float(os.getenv("APPSTORE_POOL_TIMEOUT", "5"))
MAX_CONNECTIONS = int(os.getenv("APPSTORE_MAX_CONNECTIONS", "100"))
MAX_KEEPALIVE = int(os.getenv("APPSTORE_MAX_KEEPALIVE", "20"))
HTTP2_ENABLED = os.getenv("APPSTORE_HTTP2", "0").lower() in {"1", "true", "yes"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    timeout = httpx.Timeout(
        timeout=TIMEOUT,
        connect=CONNECT_TIMEOUT,
        read=TIMEOUT,
        write=TIMEOUT,
        pool=POOL_TIMEOUT,
    )
    limits = httpx.Limits(max_connections=MAX_CONNECTIONS, max_keepalive_connections=MAX_KEEPALIVE)
    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        http2=HTTP2_ENABLED,
        follow_redirects=True,
    ) as client:
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
    include_raw: bool = Query(True),
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        return {
            "country": country.upper(),
            "items": await fetch_trends(
                app.state.http,
                country=country,
                max_count=max_count,
                include_raw=include_raw,
                use_cache=not fresh,
            ),
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
    include_raw: bool = Query(True),
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        keyword = keyword.strip()
        items = await fetch_hints(
            app.state.http,
            keyword=keyword,
            country=country,
            max_count=max_count,
            include_raw=include_raw,
            use_cache=not fresh,
        )
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
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        keyword = keyword.strip()
        return await fetch_keyword_popularity(
            app.state.http,
            keyword=keyword,
            country=country,
            use_cache=not fresh,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/itunes/search")
async def api_itunes_search(
    term: str = Query(..., min_length=1, max_length=200),
    country: str = Query("US", min_length=2, max_length=2),
    media: Optional[str] = Query(None),
    entity: Optional[str] = Query("software"),
    attribute: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=2000),
    lang: Optional[str] = Query(None),
    explicit: Optional[str] = Query(None),
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        return await itunes_search(
            app.state.http,
            term=term,
            country=country,
            media=media,
            entity=entity,
            attribute=attribute,
            limit=limit,
            offset=offset,
            lang=lang,
            explicit=explicit,
            use_cache=not fresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/itunes/lookup")
async def api_itunes_lookup(
    country: str = Query("US", min_length=2, max_length=2),
    id: Optional[str] = Query(None, max_length=32),
    bundle_id: Optional[str] = Query(None, max_length=200),
    entity: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=200),
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        return await itunes_lookup(
            app.state.http,
            country=country,
            id=id,
            bundle_id=bundle_id,
            entity=entity,
            limit=limit,
            use_cache=not fresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/appstore/rss")
async def api_appstore_rss(
    country: str = Query("us", min_length=2, max_length=2),
    feed: str = Query("top-free"),
    limit: int = Query(10),
    media: str = Query("apps"),
    type_: str = Query("apps", alias="type"),
    fresh: bool = Query(False, description="Bypass cache"),
):
    try:
        return await fetch_appstore_rss(
            app.state.http,
            country=country,
            media=media,
            feed=feed,
            limit=limit,
            type_=type_,
            use_cache=not fresh,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AsaRequestBody(BaseModel):
    path: str
    method: str = "GET"
    params: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None
    org_id: Optional[str] = None


@app.post("/v1/asa/request")
async def api_asa_request(
    body: AsaRequestBody,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    try:
        return await asa_request(
            app.state.http,
            path=body.path,
            method=body.method,
            authorization=authorization,
            params=body.params,
            json_body=body.payload,
            org_id=body.org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

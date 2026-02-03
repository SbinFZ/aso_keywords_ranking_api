from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

import httpx

from .utils import utc_now_iso


ASA_BASE_URL = os.getenv("ASA_BASE_URL", "https://api.searchads.apple.com")
ASA_ACCESS_TOKEN = os.getenv("ASA_ACCESS_TOKEN")
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_HTTP_RETRIES = int(os.getenv("APPSTORE_HTTP_RETRIES", "2"))
_HTTP_BACKOFF = float(os.getenv("APPSTORE_HTTP_BACKOFF", "0.3"))


async def _request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(_HTTP_RETRIES + 1):
        try:
            resp = await client.request(method, url, headers=headers, params=params, json=json)
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


def _require_bearer(auth_header: Optional[str]) -> str:
    if not auth_header:
        raise ValueError("Authorization header is required")
    if not auth_header.startswith("Bearer "):
        raise ValueError("Authorization must use Bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise ValueError("Bearer token is empty")
    return token


def _validate_path(path: str) -> str:
    if not path or not path.startswith("/"):
        raise ValueError("path must start with '/'")
    if ".." in path:
        raise ValueError("path contains invalid segments")
    if not path.startswith("/api/"):
        raise ValueError("path must start with '/api/'")
    return path


async def asa_request(
    client: httpx.AsyncClient,
    *,
    path: str,
    method: str = "GET",
    authorization: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    method = method.upper()
    if method not in {"GET", "POST"}:
        raise ValueError("method must be GET or POST")
    path = _validate_path(path)
    auth_value = authorization
    if not auth_value and ASA_ACCESS_TOKEN:
        auth_value = f"Bearer {ASA_ACCESS_TOKEN}"
    _require_bearer(auth_value)

    base = (base_url or ASA_BASE_URL).rstrip("/")
    url = f"{base}{path}"

    headers = {
        "Authorization": auth_value,
        "Accept": "application/json",
    }
    if org_id:
        headers["X-AP-Context"] = f"orgId={org_id}"

    resp = await _request_with_retries(
        client,
        method,
        url,
        headers=headers,
        params=params,
        json=json_body,
    )
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        body: Any = resp.json()
    else:
        body = resp.text

    return {
        "url": url,
        "status_code": resp.status_code,
        "response": body,
        "fetched_at": utc_now_iso(),
    }

"""Generic HTTP client for the DB's plain-REST APIs (financial, OT, ambulance, appointments).

These upstreams share one contract: list endpoints return `{ "data": [...], "total": N }`
and single reads return the object. All use the same bearer key as the financial API
(`settings.financial_key`). Fabric passes the JSON straight through — it's already the
dict shape the agents want, so no FHIR transform is involved.

Callers pass the upstream `base_url` per call (see service/financial.py, service/ot.py, …).
The initial-sync API uses a different (keyset-pagination) envelope and lives in
sync_client.py, which reuses `auth_headers` from here.
"""

import logging

import httpx

from config import settings

logger = logging.getLogger("rest_client")


def auth_headers() -> dict:
    """Bearer auth shared by all the DB's plain-REST APIs (incl. initial-sync)."""
    h = {"Accept": "application/json"}
    if settings.financial_key:
        h["Authorization"] = f"Bearer {settings.financial_key}"
    return h


async def _get(base_url: str, path: str, params: dict | None = None):
    url = f"{base_url.rstrip('/')}/{path}"
    async with httpx.AsyncClient(timeout=settings.upstream_timeout) as client:
        resp = await client.get(url, params=params, headers=auth_headers())
        resp.raise_for_status()
        return resp.json() if resp.content else None


async def _post(base_url: str, path: str, body: dict | None = None):
    url = f"{base_url.rstrip('/')}/{path}"
    async with httpx.AsyncClient(timeout=settings.upstream_timeout) as client:
        resp = await client.post(url, json=body, headers=auth_headers())
        resp.raise_for_status()
        return resp.json() if resp.content else None


async def _patch(base_url: str, path: str, body: dict | None = None):
    url = f"{base_url.rstrip('/')}/{path}"
    async with httpx.AsyncClient(timeout=settings.upstream_timeout) as client:
        resp = await client.patch(url, json=body, headers=auth_headers())
        resp.raise_for_status()
        return resp.json() if resp.content else None


def _unwrap(payload) -> list[dict]:
    """Unwrap {data:[...], total:N} or bare list."""
    if isinstance(payload, dict):
        return payload.get("data", [])
    return payload or []


async def list_(base_url: str, path: str, **params) -> list[dict]:
    clean = {k: v for k, v in params.items() if v is not None}
    return _unwrap(await _get(base_url, path, clean or None))


async def safe_list(base_url: str, path: str, **params) -> list[dict]:
    """Like list_ but degrades to [] if the upstream endpoint is unavailable."""
    try:
        return await list_(base_url, path, **params)
    except Exception as exc:
        logger.warning("REST %s/%s unavailable: %s", base_url, path, str(exc)[:120])
        return []


async def get_one(base_url: str, path: str):
    """Single-object read (endpoints that return the object, not a {data,total} list)."""
    return await _get(base_url, path)


async def create(base_url: str, path: str, body: dict) -> dict:
    result = await _post(base_url, path, body)
    return result or {}


async def update(base_url: str, path: str, body: dict | None = None) -> dict:
    result = await _patch(base_url, path, body)
    return result or {}

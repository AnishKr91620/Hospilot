"""HTTP client for the DB's initial-sync API (GET /api/sync/<table>).

Unlike the other plain-REST endpoints (financial/OT/ambulance), the sync API
returns a full keyset-pagination envelope — sync_id, table, schema, pagination,
rows — rather than {data:[...], total:N}. Fabric passes that envelope straight
through to the main backend, so this client returns the raw JSON unchanged.

Shares the same bearer key/auth as the plain-REST client (reuses its
`auth_headers`, which reads settings.financial_key).
"""

import logging

import httpx

from clients.rest_client import auth_headers
from config import settings

logger = logging.getLogger("sync_client")


async def fetch_page(
    table: str,
    *,
    limit: int | None = None,
    cursor: str | None = None,
    sync_id: str | None = None,
) -> dict:
    """GET one keyset page from the DB's /api/sync/<table>.

    Returns the full upstream envelope unchanged. Raises httpx.HTTPStatusError
    on a non-2xx response so the caller can map the DB's status code through.
    """
    params = {
        k: v
        for k, v in {"limit": limit, "cursor": cursor, "sync_id": sync_id}.items()
        if v is not None
    }
    url = f"{settings.sync_api_base_url.rstrip('/')}/{table}"
    async with httpx.AsyncClient(timeout=settings.upstream_timeout) as client:
        resp = await client.get(url, params=params or None, headers=auth_headers())
        resp.raise_for_status()
        return resp.json()

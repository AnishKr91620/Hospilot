"""Ventilator inventory reads (ICU).

No FHIR resource and no plain-REST list endpoint upstream, so Fabric sources this
from the DB's keyset sync API (like lab_result). Rows pass through in the DB's
shape. Inert until the DB registers /api/sync/ventilator.
"""

from service import initial_sync


async def units() -> list[dict]:
    return await initial_sync.drain("ventilator")

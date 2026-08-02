"""Initial-sync API — one-time bulk table dumps. NOT runtime.

Used once per deployment (or after a cache wipe) so hospilot-backend can populate
Redis from scratch, before the Kafka change feed takes over for incremental
updates. Keyset-paginated, because these are whole-table reads.

Distinct from api/runtime/ in both caller and cadence: the backend drains these at
startup, whereas runtime routes serve agents continuously.

See tables.py for the pagination contract.
"""

from api.sync.tables import router

__all__ = ["router"]

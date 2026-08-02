"""Runtime API — live queries the agents make while they work.

One of Fabric's three API surfaces, split by request lifecycle:

  api/runtime/   this package — live agent reads and writes, called continuously
  api/changes/   the write handshake with the DB, driven by the DB, not by agents
  api/sync/      one-time bulk table dumps to seed the backend's cache

Everything here answers "what is true right now, for this filter" — the questions
the backend's Redis cache can't serve because they need lists, joins or aggregates
rather than a single record. One module per domain; every route keeps the URL it has
always had, so callers are unaffected by this grouping.

Aggregated below into a single `router`, which main.py mounts once. Domain prefixes
don't overlap, so include order is not significant across modules — but WITHIN each
module static sub-paths must stay declared before their `/{id}` sibling or FastAPI
will shadow them.

⚠ patients.py is the only PHI-bearing module; the rest is pseudonymous.
"""

from fastapi import APIRouter

from api.runtime import (
    admissions,
    appointments,
    beds,
    departments,
    financial,
    labs,
    ot,
    patients,
    pharmacy,
    tasks,
    visits,
    vitals,
)

router = APIRouter()

for _module in (
    beds,
    admissions,
    vitals,
    visits,
    tasks,
    labs,
    pharmacy,
    financial,
    patients,
    departments,
    ot,
    appointments,
):
    router.include_router(_module.router)

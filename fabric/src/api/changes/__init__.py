"""Change-exchange API — the write handshake with the upstream HIS. NOT runtime.

The odd one out among Fabric's three API surfaces: these routes are called by the
**DB/HIS**, not by hospilot's agents, and not on any agent's critical path. The DB
polls them on its own schedule to collect changes Hospilot wants applied, then
reports back what it accepted.

Active in change_api and polling mode. Under INTEGRATION_MODE=kafka the DB stops
polling — proposals are pushed to hospilot.sync.write by writeback/ — and these
routes return 409 so the two can't race the same queue.

See pending_changes.py for the three-step protocol.
"""

from api.changes.pending_changes import router

__all__ = ["router"]

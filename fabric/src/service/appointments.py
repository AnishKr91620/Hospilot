"""Appointment + doctor-slot reads and writes over the DB's plain-REST API.

Reads pass through untransformed. Writes do NOT go upstream directly: create() and
book_slot() enqueue a PendingChange, which leaves via whichever write leg the mode
selects (HTTP $pending-changes pull, or the Kafka push in writeback/).

Delivery paths (see fabric/README.md for the full table):
  • streamed → Kafka → backend Redis:  list_all, slots
      Registered in sync_map.REST_ENTITIES as `appointment` / `doctor_slot`. Agents get
      the steady state from Redis — but unlike OT these keep their HTTP routes, because
      agents also need filtered lookups (by patient, provider, date, specialization)
      that Redis keys can't answer.
  • write path:  create, book_slot
"""

from clients import rest_client as rc
from config import settings
from service.change_store import PendingChange, get_change_store, new_change_id, now_iso
from service.writes import CHANGE_TYPE_APPROVAL, CHANGE_TYPE_ENTITY


def _base() -> str:
    return settings.db_rest_base_url


async def list_all(**filters) -> list[dict]:
    return await rc.list_(_base(), "appointments", **filters)


async def create(body: dict) -> dict:
    # The DB assigns the appointment id, so record_id is unknown until $confirm returns
    # it as `assigned_id`; the ack event fills `id` from there.
    await get_change_store().add(PendingChange(
        change_type="appointment_create",
        resource_type="Appointment",
        resource_id=None,
        http_method="POST",
        payload={"body": body},
        timestamp=now_iso(),
        change_id=new_change_id(),
        entity=CHANGE_TYPE_ENTITY["appointment_create"],
        record_id="",
        approval_needed=CHANGE_TYPE_APPROVAL["appointment_create"],
    ))
    return {"ok": True, "queued": True}


async def slots(**filters) -> list[dict]:
    return await rc.list_(_base(), "appointments/slots", **filters)


async def book_slot(slot_id: str) -> dict:
    await get_change_store().add(PendingChange(
        change_type="slot_book",
        resource_type="Slot",
        resource_id=slot_id,
        http_method="PATCH",
        payload={},
        timestamp=now_iso(),
        change_id=new_change_id(),
        entity=CHANGE_TYPE_ENTITY["slot_book"],
        record_id=str(slot_id),
        approval_needed=CHANGE_TYPE_APPROVAL["slot_book"],
    ))
    return {"ok": True, "queued": True}

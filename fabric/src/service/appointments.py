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

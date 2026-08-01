from clients import rest_client as rc
from config import settings


def _base() -> str:
    return f"{settings.db_rest_base_url}/ot"


async def rooms() -> list[dict]:
    return await rc.list_(_base(), "rooms")


async def room_status() -> list[dict]:
    return await rc.list_(_base(), "room-status")


async def surgery_schedule() -> list[dict]:
    return await rc.list_(_base(), "surgery-schedule")


async def equipment_usage() -> list[dict]:
    return await rc.safe_list(_base(), "equipment-usage")


async def surgeries() -> list[dict]:
    return await rc.list_(_base(), "surgeries")

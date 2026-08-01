from clients import rest_client as rc
from config import settings


def _base() -> str:
    return settings.db_rest_base_url


async def fleet() -> list[dict]:
    return await rc.list_(_base(), "ambulance")

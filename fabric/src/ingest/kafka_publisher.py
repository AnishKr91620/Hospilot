"""Kafka producer for publishing data-change events to hospilot-backend.

Each event is `{entity, id, data}` published to topic `{prefix}.{entity}` and keyed
by the record id (so per-record ordering is preserved). The `data` field is the full
current row in Fabric's normalized shape — hospilot-backend consumes it and upserts
Redis directly (see docs KAFKA_EVENT_CONTRACT).

Disabled (no-op) when KAFKA_BOOTSTRAP_SERVERS is unset, so Fabric runs without Kafka
in dev. `publish()` raises on delivery failure; the poller uses that to decide whether
to acknowledge the DB change feed (at-least-once).
"""

import json
import logging

from config import settings

logger = logging.getLogger("kafka")

_producer = None


def enabled() -> bool:
    return settings.kafka_enabled


async def start() -> None:
    global _producer
    if not enabled():
        logger.info("✓ Kafka publishing OFF (no KAFKA_BOOTSTRAP_SERVERS)")
        return
    from aiokafka import AIOKafkaProducer

    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        client_id=settings.kafka_client_id,
        acks="all",
        enable_idempotence=True,
    )
    await _producer.start()
    logger.info("✓ Kafka producer connected  servers=%s prefix=%s",
                settings.kafka_bootstrap_servers, settings.kafka_topic_prefix)


async def stop() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish(
    entity: str,
    record_id: str,
    data: dict | None,
    operation: str = "upsert",
    changed: list[str] | None = None,
) -> None:
    """Publish one change event. Raises on delivery failure (caller decides on ack).

    `operation` is "upsert" for full creates/updates, "delete" for removals, and
    "patch" for polling-mode field-level diffs. For "delete", `data` is None —
    consumers evict the record. For "patch", `data` carries ONLY the changed columns
    and `changed` lists their names — consumers MERGE it onto existing state rather
    than replacing the record. `changed` is omitted from the payload unless given, so
    "upsert"/"delete" events keep their exact original shape.
    """
    if _producer is None:
        return  # disabled — no-op
    topic = f"{settings.kafka_topic_prefix}.{entity}"
    payload = {"entity": entity, "id": record_id, "operation": operation, "data": data}
    if changed is not None:
        payload["changed"] = changed
    await _producer.send_and_wait(
        topic,
        value=json.dumps(payload, default=str).encode("utf-8"),
        key=str(record_id).encode("utf-8"),
    )


async def publish_ack(
    *,
    snapshot_id: str,
    change_id: str,
    entity: str,
    record_id: str,
    change_type: str,
    status: str,
    reason: str | None,
    ts: str,
) -> None:
    """Publish one write-proposal acknowledgement to the dedicated ack topic.

    `status` is "accepted" or "rejected". The backend consumes these to release the
    optimistic lock it took when it issued the write (revert on "rejected"). Keyed by
    `record_id` so a record's acks stay ordered. Raises on delivery failure so the
    $confirm caller can keep the snapshot locked and let the DB retry. No-op when the
    producer is disabled."""
    if _producer is None:
        return
    payload = {
        "snapshot_id": snapshot_id,
        "change_id": change_id,
        "entity": entity,
        "id": record_id,
        "change_type": change_type,
        "status": status,
        "reason": reason,
        "ts": ts,
    }
    await _producer.send_and_wait(
        settings.kafka_ack_topic,
        value=json.dumps(payload, default=str).encode("utf-8"),
        key=str(record_id).encode("utf-8"),
    )


async def publish_write_proposal(
    *,
    change_id: str,
    entity: str,
    record_id: str,
    change_type: str,
    http_method: str,
    approval_needed: bool,
    bundle: dict,
    ts: str,
) -> None:
    """Publish one approved change to the DB over Kafka (integration_mode=kafka write leg).

    The value is a thin envelope carrying a single-entry, spec-clean FHIR R5 transaction
    `bundle` (built with include_approval=False, so approval lives here in the envelope,
    not on the FHIR resource). Keyed by `record_id` (falls back to `change_id` when the
    record id isn't known yet, e.g. appointment_create) so all changes to one record land
    on one partition and stay ordered. Raises on delivery failure so the publisher loop
    keeps the change queued (at-least-once); the DB dedups by change_id. No-op when the
    producer is disabled (dev)."""
    if _producer is None:
        return
    payload = {
        "change_id": change_id,
        "entity": entity,
        "id": record_id,
        "change_type": change_type,
        "http_method": http_method,
        "approval_needed": approval_needed,
        "ts": ts,
        "bundle": bundle,
    }
    key = record_id or change_id
    await _producer.send_and_wait(
        settings.kafka_write_topic,
        value=json.dumps(payload, default=str).encode("utf-8"),
        key=str(key).encode("utf-8"),
    )

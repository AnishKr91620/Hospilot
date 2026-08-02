"""Service layer — every read here goes UPSTREAM to the hospital's HIS.

Fabric owns no data and has no database. It is a client of three upstream APIs, and
which one a module uses is the only structural distinction in this package:

  clients.fhir_client   canonical FHIR R5 (clinical)   → clinical, sync_map, lab
  clients.rest_client   plain REST (financial, OT,     → financial, ot, ambulance,
                        ambulance, appointments)          appointments, pharmacy, lab
  clients.sync_client   keyset bulk sync               → initial_sync, staff, ventilator

Pure transform / in-memory state, no upstream: transform, change_store, writes.

**Fabric never connects to Redis.** Modules here mention Redis often, but always to
describe what hospilot-backend does after consuming Fabric's Kafka events — the
backend caches them, the agents read that cache. Fabric has no Redis client, no Redis
dependency, and no cache of its own; "Redis-backed" means "the backend keeps it in
Redis", never "Fabric writes it there".

Two delivery paths lead to the agents, and most entities use both. See the table in
fabric/README.md, and each module's own docstring for its entities:
  • streamed     — published to Kafka, cached by the backend, read from Redis
  • pass-through — served live over Fabric's REST API, for the list / filter /
                   computed queries Redis keys cannot answer

PHI: only transform.patient() returns demographics (name, mobile, UHID), backing
/patients*. Everything else Fabric serves carries an opaque patient token only.
"""

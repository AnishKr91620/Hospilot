# Hospilot Fabric

Fabric is the data layer between a hospital's existing information system and Hospilot's
agents. It reads the hospital's APIs, maps everything to **FHIR R5**, and gives the Hospilot
backend one stable shape to consume — so integrating a different HIS means changing Fabric,
not the agents.

Fabric **owns no data**. It has no database and no cache. Every read goes upstream to the
hospital; everything it emits is derived.

---

## The three parties

The thing to understand first: Fabric sits between two systems and speaks a different
protocol to each. HTTP/FHIR faces the hospital, Kafka faces Hospilot.

```
     HOSPITAL HIS                  FABRIC                 HOSPILOT BACKEND
    (owns the data)            (this service)            (agents, Redis cache)
          │                          │                          │
  READ    │  ── Fabric polls ──►     │  ── Kafka ──►            │
          │  GET $changed-resources  │  hospilot.data.{entity}  │
          │                          │                          │
  WRITE   │  ◄── the HIS polls ──    │  ◄── Kafka ──            │
          │  GET  $pending-changes   │  hospilot.sync.ack       │
          │  POST $acknowledge       │                          │
          │  POST $confirm           │                          │
          │                          │  ◄── HTTP ──             │
          │                          │  agents query live       │
          └───── HTTP / FHIR ────────┴──── Kafka + HTTP ────────┘
```

The hospital never touches Kafka. Kafka is internal to Hospilot: it's how Fabric pushes
changes to the backend, which caches them in Redis for the agents. Fabric itself never
connects to Redis — when this codebase says an entity is "cached", it means the *backend*
caches it.

---

## How data gets in: `INTEGRATION_MODE`

Hospitals differ in what they can offer, so ingest has three implementations. Exactly one
runs, chosen by `INTEGRATION_MODE`, and all three end by publishing to Kafka.

| Mode | How Fabric learns of changes | Module |
|---|---|---|
| `change_api` *(default)* | Polls the HIS's `$changed-resources` FHIR feed | `ingest/change_poller.py` |
| `polling` | No change feed upstream — Fabric polls each resource API and diffs field by field | `ingest/diff_poller.py` |
| `kafka` | The HIS pushes to `hospilot.changes.*`; Fabric consumes | `ingest/kafka_consumer.py` |

Ingest only starts when `KAFKA_BOOTSTRAP_SERVERS` is set. Without a broker Fabric still
serves its REST API normally — you just get no change stream, which is the usual local-dev
setup.

## How data gets out: the write handshake

Agents don't write to the hospital directly. A write becomes a queued `PendingChange`, and
the HIS collects it in three steps:

1. `GET /fhir/Bundle/$pending-changes` — mints a `snapshot_id`, returns the queue as a FHIR
   R5 transaction Bundle. Re-pulling returns the **same** snapshot, not a new one.
2. `POST /fhir/Bundle/$pending-changes/$acknowledge` — the HIS confirms durable receipt;
   Fabric holds a soft lock. The queue is not cleared yet.
3. `POST /fhir/Bundle/$pending-changes/$confirm` — the HIS reports accepted/rejected per
   change. Fabric publishes one ack per change to `hospilot.sync.ack` and releases the lock.

Miss step 3 for `SNAPSHOT_LOCK_TIMEOUT_MS` (default 60s) and the lock expires and those
changes are re-offered — delivery is at-least-once, and the HIS should dedupe on
`change_id`. Under `INTEGRATION_MODE=kafka` these routes return **409** instead: proposals
are pushed to `hospilot.sync.write` by `writeback/`, and the two must not race the queue.

---

## Two ways data reaches an agent

Most entities travel both paths, which looks redundant until you notice they answer
different questions. **Redis holds one record; Fabric answers questions about many.**
`bed:{id}` is a cache hit, but "which ICU beds are dirty" is not something Redis keys can
answer, so that goes to Fabric.

| | Entities | Where agents read it |
|---|---|---|
| **Streamed only** | `ot_room`, `ot_room_status`, `ot_schedule`, `ot_surgery`, `ambulance`, `ventilator`, `staff`, `staff_roster` | Redis. Fabric exposes **no** HTTP route for these — the ones that existed had no callers and were removed. |
| **Both** | `bed`, `admission`, `discharge_ready`, `visit`, `task`, `lab_order`, `lab_result`, `lab_sample`, `lab_analyzer`, `pharmacy_order`, `pharmacy_inventory`, `appointment`, `doctor_slot` | Redis for single records; Fabric for lists, filters and aggregates. |
| **Live only** | All `financial/*`; computed views (`/beds/summary`, `/er/pressure`, `/admissions/discharge-horizon`); `/patients*`; `/departments`; `/ot/equipment-usage`; the lab and pharmacy rules tables | Fabric, every time. Never cached. |

`ventilator`, `staff` and `staff_roster` are wired but **inert**: they stay empty until the
hospital exposes `/api/sync/{ventilator,staff,staff_roster}`.

---

## PHI

Fabric is pseudonymous nearly everywhere. Records carry an opaque `patient_token`; there is
no patient table here and no PHI at rest.

The exception is `api/runtime/patients.py`, backed by `service/transform.py::patient()`,
which resolves a token to real demographics (name, mobile, UHID) for `/patients`,
`/patients/{token}` and `/patients/by-mobile`. Treat that module as the PHI boundary:

- **never** run with `FABRIC_API_KEY` unset where those routes are reachable
- don't log their responses
- `/patients/by-mobile` is a reverse lookup — unauthenticated, it would let a caller
  enumerate patients by phone number

---

## Layout

```
src/
├── api/                    three surfaces, split by who calls them and when
│   ├── runtime/            live agent queries — one module per domain
│   ├── changes/            the HIS-driven write handshake (not runtime)
│   └── sync/               one-time bulk dumps to seed the backend's cache
├── ingest/                 HIS → Fabric; one module per INTEGRATION_MODE
├── messaging/              the single shared Kafka producer
├── writeback/              Fabric → HIS write leg (kafka mode only)
├── service/                upstream reads + transforms; owns no data
├── clients/                HTTP clients for the three upstream APIs
├── fhirgw/                 FHIR R5 gateway — terminology, extensions, mappers, bundles
├── config.py               all settings (see .env.example)
└── main.py                 app + lifespan wiring
```

`fhirgw` is named that, not `fhir`, on purpose: `src/` is the import root, so a package
called `fhir` would shadow the `fhir.resources` library.

Each package's `__init__.py` documents its own scope and dependencies — start with
`service/__init__.py` and `api/runtime/__init__.py`.

---

## Running it locally

Requires Python 3.11+ (CI runs 3.12).

```bash
cd fabric
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt      # requirements.txt + pytest
cp .env.example .env                     # defaults work against a local HIS on :3001

python -m pytest                         # 72 tests, no network or broker needed
uvicorn main:app --app-dir src --port 8001
```

Then open `http://localhost:8001/docs` — every route carries a summary, so the generated
page is the API reference. `GET /health` needs no auth.

With the whole stack, including a single-node Kafka:

```bash
docker compose -f deployments/docker-compose.fabric.yml up --build
```

### Configuration notes

Everything comes from the environment or `.env`; see `.env.example` for the full annotated
set and `src/config.py` for the defaults. Two that catch people out:

- **`FINANCIAL_API_BASE_URL` is load-bearing beyond finance.** The OT / ambulance /
  appointment REST base and the initial-sync base are both *derived* from it, so a wrong
  value silently breaks those too.
- **`FABRIC_API_KEY` blank disables Fabric's own auth.** Fine locally, not anywhere shared —
  see the PHI section.

---

## Tests

```bash
python -m pytest                  # all 72
python -m pytest tests/test_transform.py -v
```

Six suites covering FHIR mapping round-trips, the transform layer, endpoint wiring, the
polling-mode differ, the two-phase pending-changes protocol, and kafka-mode payload
handling. All hermetic: upstreams are mocked, and no Kafka broker or database is required.

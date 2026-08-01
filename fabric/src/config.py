"""Hospilot-Fabric settings.

Fabric is a TRANSFORMATION layer: it is a CLIENT of the DB's APIs. It calls the
DB's FHIR API (clinical) + the DB's plain-REST financial API, transforms the
responses into the normal dict shapes the main backend wants, and serves those.

It needs:
  • the DB's FHIR base URL + key   (clinical resources, FHIR R5)
  • the DB's financial REST base URL + key   (invoices/claims/… plain JSON)
  • its own API key                (guards Fabric's endpoints for the main app)
  • its own public FHIR base URL   (mints identifier systems for write payloads)

All values come from the environment / a local `.env` (see .env.example).
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings

_INTEGRATION_MODES = {"change_api", "polling", "kafka"}


class Settings(BaseSettings):
    # ── upstream: the DB's FHIR API (what Fabric calls and transforms) ──────────
    ehr_fhir_base_url: str = "http://localhost:3001/fhir"
    ehr_fhir_api_key: str = ""

    # ── upstream: the DB's plain-REST financial API ─────────────────────────────
    financial_api_base_url: str = "http://localhost:3001/api/financial"
    financial_api_key: str = ""        # empty => falls back to ehr_fhir_api_key

    # ── downstream: Fabric's own auth (main app → Fabric) ───────────────────────
    fabric_api_key: str = ""           # empty => Fabric auth disabled (dev)

    # ── identity (used only when building FHIR write payloads) ──────────────────
    fhir_base_url: str = "http://localhost:8002/fhir"
    ehr_source: str = "hospilot"

    # ── Kafka: Fabric publishes data-change events (read direction → main app) ──
    # Empty bootstrap servers => publishing AND the change poller are disabled (dev).
    kafka_bootstrap_servers: str = ""
    kafka_topic_prefix: str = "hospilot.data"
    kafka_client_id: str = "hospilot-fabric"
    poll_interval_ms: int = 10000
    # dedicated topic for write-proposal acknowledgements (DB accepted/rejected a change)
    kafka_ack_topic: str = "hospilot.sync.ack"
    # kafka-mode write leg: Fabric PUSHES approved changes here as single-entry FHIR
    # Bundles; the DB consumes, applies, and acks on kafka_ack_topic. Only used when
    # integration_mode=kafka (change_api/polling still use the HTTP $pending-changes pull).
    kafka_write_topic: str = "hospilot.sync.write"
    # drain cadence (ms) for the kafka-mode write publisher loop
    write_drain_interval_ms: int = 1000
    # soft-lock timeout: if the DB doesn't $confirm an in-flight snapshot within this
    # window, the lock expires and its changes are re-offered on the next pull.
    snapshot_lock_timeout_ms: int = 60000

    # ── ingest mode: how Fabric learns about DB changes (read direction) ─────────
    #   "change_api" (default) — poll the DB's FHIR $changed-resources change feed.
    #   "polling"              — the DB has no change feed, so Fabric polls each
    #                            per-resource API itself and publishes a field-level
    #                            diff (only the changed columns). See diff_poller.py.
    integration_mode: str = "change_api"
    # polling-mode per-entity poll cadence (ms). Only used when integration_mode=polling.
    # Defaults reflect clinical volatility: beds flip fast; labs/tasks are slower; the
    # keyset-paginated lab_result table gets the slowest cadence.
    poll_interval_bed_ms: int = 5000
    poll_interval_admission_ms: int = 10000
    poll_interval_visit_ms: int = 10000
    poll_interval_lab_order_ms: int = 15000
    poll_interval_task_ms: int = 15000
    poll_interval_lab_result_ms: int = 30000
    poll_interval_rest_ms: int = 10000        # ot_*, ambulance, appointment, doctor_slot

    # ── app ─────────────────────────────────────────────────────────────────────
    app_env: str = "development"
    cors_origins: str = "*"
    upstream_timeout: float = 20.0

    @field_validator("integration_mode", mode="before")
    @classmethod
    def _normalize_integration_mode(cls, v: str) -> str:
        mode = str(v).strip().lower()
        if mode not in _INTEGRATION_MODES:
            raise ValueError(
                f"integration_mode must be one of {sorted(_INTEGRATION_MODES)}, got {v!r}"
            )
        return mode

    @property
    def kafka_enabled(self) -> bool:
        return bool(self.kafka_bootstrap_servers)

    @property
    def polling_mode(self) -> bool:
        return self.integration_mode == "polling"

    @property
    def kafka_mode(self) -> bool:
        return self.integration_mode == "kafka"

    @property
    def poll_intervals_ms(self) -> dict[str, int]:
        """Per-entity poll cadence (ms) for polling mode, keyed by topic entity."""
        return {
            "bed": self.poll_interval_bed_ms,
            "admission": self.poll_interval_admission_ms,
            "visit": self.poll_interval_visit_ms,
            "lab_order": self.poll_interval_lab_order_ms,
            "task": self.poll_interval_task_ms,
            "lab_result": self.poll_interval_lab_result_ms,
        }

    @property
    def snapshot_lock_timeout_s(self) -> float:
        return self.snapshot_lock_timeout_ms / 1000

    @property
    def financial_key(self) -> str:
        return self.financial_api_key or self.ehr_fhir_api_key

    @property
    def db_rest_base_url(self) -> str:
        """Base URL for all DB plain-REST APIs (OT, ambulance, appointments).
        Derived from financial_api_base_url by stripping /financial."""
        url = self.financial_api_base_url.rstrip("/")
        return url[: -len("/financial")] if url.endswith("/financial") else url

    @property
    def sync_api_base_url(self) -> str:
        """Base URL for the DB's initial-sync API (GET /api/sync/<table>).
        Derived from db_rest_base_url -> http://<host>/api/sync."""
        return f"{self.db_rest_base_url}/sync"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

"""Kafka transport — the shared producer Fabric publishes everything through.

Not a direction and not a mode: this is infrastructure both legs depend on. The
single producer here carries all three publishes — data-change events and write
acknowledgements inward to hospilot-backend, and write proposals outward to the
DB — so ingest.*, writeback.* and the api.* request handlers all import it.

Named to match agentic-framework/messaging/, which consumes these same topics.
"""

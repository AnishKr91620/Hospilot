"""
Test bootstrap. Fabric runs with `src/` as the import root, so put it on sys.path
here -- this is the only thing that makes the flat imports work under pytest.
Settings all have safe defaults, so no real upstreams needed.
"""

import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("EHR_FHIR_BASE_URL", "http://localhost:3001/fhir")
os.environ.setdefault("FINANCIAL_API_BASE_URL", "http://localhost:3001/api/financial")
os.environ.setdefault("FABRIC_API_KEY", "")     # Fabric auth disabled in tests

# Pin the ingest mode and disable Kafka. Without these, a developer's local
# `fabric/.env` (which may set INTEGRATION_MODE=kafka) leaks into the suite: the
# $pending-changes pull returns 409 in kafka mode, and the mode-default assertion
# flips. Tests that exercise kafka mode set it explicitly via monkeypatch.
os.environ.setdefault("INTEGRATION_MODE", "change_api")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "")

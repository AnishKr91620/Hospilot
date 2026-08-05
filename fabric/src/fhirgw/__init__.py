"""
fhirgw — Hospilot's in-app FHIR gateway (canonical FHIR R5 / 5.0.0).

Named `fhirgw` (not `fhir`) on purpose: `src/` is the import root (uvicorn runs with
--app-dir src; tests/conftest.py puts it on sys.path), so a package literally named
`fhir` would shadow the `fhir.resources` library and break
`from fhir.resources... import ...`.

Vocabulary and mapping only — no I/O, no transport, no queue:
  terminology.py   — code systems + LOINC/status/class/interpretation maps
  identifiers.py   — internal id / patient_token -> FHIR identifier system+value
  extensions.py    — Hospilot extension URLs + build/read helpers
  narrative.py     — human-readable <div> text for generated resources
  mappers/         — bidirectional internal-dict <-> canonical FHIR

Consumers: input_transform/transform.py (terminology, extensions + the location, encounter and
observation mappers) and writeback/bundle.py, which assembles transaction Bundles from
these pieces. Bundle assembly used to live here but is write-leg-specific, so it moved
to writeback/ with the rest of that pipeline.

The patient and organization mappers have no Fabric caller — they're shared mapping
logic kept for their tests. See their module docstrings.
"""

FHIR_VERSION = "5.0.0"  # fhir.resources top-level == R5

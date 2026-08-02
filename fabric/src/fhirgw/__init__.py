"""
fhirgw — Hospilot's in-app FHIR gateway (canonical FHIR R5 / 5.0.0).

Named `fhirgw` (not `fhir`) on purpose: the app runs with `src/` on the import
root (see server.sh), so a package literally named `fhir` would shadow the
`fhir.resources` library and break `from fhir.resources... import ...`.

Layout:
  terminology.py   — code systems + LOINC/status/class/interpretation maps
  identifiers.py   — internal id / patient_token -> FHIR identifier system+value
  extensions.py    — Hospilot extension URLs + build/read helpers
  narrative.py     — human-readable <div> text for generated resources
  bundle.py        — transaction Bundle assembly for the write queue (FHIRPath Patch
                     entries for updates, full resources for creates)
  mappers/         — bidirectional internal-dict <-> canonical FHIR

Fabric uses a subset of this package: bundle.py drives the write path, and
transform.py uses terminology/extensions plus the location, encounter and
observation mappers. The patient and organization mappers are shared mapping logic
kept for their tests — see their module docstrings.
"""

FHIR_VERSION = "5.0.0"  # fhir.resources top-level == R5

"""
Round-trip identity + FHIR validity for the pilot mappers.

The agent contract is preserved because `to_internal(to_fhir(x)) == x` for the
exact internal projection shapes the poller produces (see src/poller/carerOS_poller.py
_map_* and src/db/hasura.py read-backs). Validity is checked by re-parsing each
resource's serialized JSON through its fhir.resources model.
"""

import json

import pytest

from fhir.resources.location import Location
from fhir.resources.organization import Organization
from fhir.resources.encounter import Encounter
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient

from fhirgw.mappers import location, organization, encounter, observation, patient


# ─── fixtures mirroring the real projection shapes ────────────────────────────
BEDS = [
    {  # fully enriched, available
        "id": "bed-icu-01", "ward": "ICU", "bed_number": "ICU-01", "room_type": "ICU",
        "status": "Available", "is_active": True, "branch_id": "branch-main",
        "ventilation": "full_ventilator", "room_sharing": "private", "proximity": 2,
        "floor": 3, "wing": "North", "natural_light": True, "noise_level": "quiet",
        "features": ["isolation", "telemetry"],
    },
    {  # sparse, Hospilot-owned status, null enrichment, empty features
        "id": "bed-2", "ward": "General", "bed_number": "2", "room_type": "General",
        "status": "reserved", "is_active": True, "branch_id": None,
        "ventilation": None, "room_sharing": None, "proximity": None, "floor": None,
        "wing": None, "natural_light": None, "noise_level": None, "features": [],
    },
    {  # dirty bed (suspended)
        "id": "bed-3", "ward": "ICU", "bed_number": "ICU-03", "room_type": "ICU",
        "status": "Dirty", "is_active": True, "branch_id": "branch-main",
        "ventilation": "oxygen", "room_sharing": "shared_2", "proximity": 5,
        "floor": 1, "wing": "South", "natural_light": False, "noise_level": "loud",
        "features": ["telemetry"],
    },
]

DEPARTMENTS = [
    {"id": "dept-icu", "name": "Intensive Care Unit", "type": "icu"},
    {"id": "dept-x", "name": "", "type": None},
]

ADMISSIONS = [
    {"id": "adm-1", "patient_token": "pt-123", "bed_id": "bed-icu-01",
     "admitted_at": "2025-01-15T10:30:00+00:00", "expected_discharge_at": "2025-01-20T14:00:00+00:00",
     "status": "admitted"},
    {"id": "adm-2", "patient_token": "", "bed_id": None,
     "admitted_at": "2025-01-15T10:30:00", "expected_discharge_at": None,  # naive ts -> ext only
     "status": "discharging"},
]

VISITS = [
    {"id": "v-1", "patient_token": "pt-9", "department_id": "dept-er",
     "arrived_at": "2025-01-15T16:45:00+00:00", "status": "waiting", "chief_complaint": "Chest pain"},
    {"id": "v-2", "patient_token": "", "department_id": None,
     "arrived_at": None, "status": "in_treatment", "chief_complaint": None},
]

VITALS = [
    {"id": "vit-1", "patient_token": "pt-1", "admission_id": "adm-1",
     "recorded_at": "2025-01-15T14:22:00+00:00", "temperature": 37.2, "pulse": 85,
     "bp_systolic": 130, "bp_diastolic": 85, "spo2": 96, "respiratory_rate": 18,
     "gcs": 15, "is_critical": False},
    {"id": "vit-2", "patient_token": "pt-2", "admission_id": None,
     "recorded_at": "2025-01-15T14:22:00+00:00", "temperature": None, "pulse": 120,
     "bp_systolic": None, "bp_diastolic": None, "spo2": 88, "respiratory_rate": None,
     "gcs": None, "is_critical": True},
]


def _revalidate(resource, model_cls):
    """Serialize then re-parse to assert the resource is structurally valid FHIR."""
    js = resource.model_dump_json(exclude_none=True, by_alias=True)
    reparsed = model_cls.model_validate_json(js)
    assert json.loads(js)["resourceType"] == model_cls.__name__
    return reparsed


# ─── beds ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bed", BEDS, ids=lambda b: b["id"])
def test_bed_roundtrip(bed):
    loc = location.to_fhir(bed)
    _revalidate(loc, Location)
    assert location.to_internal(loc) == bed


def test_bed_upsert_row_is_operational_only():
    loc = location.to_fhir(BEDS[0])
    row = location.to_upsert_row(loc)
    assert set(row) == set(location.OPERATIONAL_KEYS)
    assert row["status"] == "Available" and row["is_active"] is True


# ─── departments ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("dept", DEPARTMENTS, ids=lambda d: d["id"])
def test_department_roundtrip(dept):
    org = organization.to_fhir(dept)
    _revalidate(org, Organization)
    assert organization.to_internal(org) == dept


# ─── admissions ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("adm", ADMISSIONS, ids=lambda a: a["id"])
def test_admission_roundtrip(adm):
    enc = encounter.admission_to_fhir(adm)
    _revalidate(enc, Encounter)
    assert encounter.admission_to_internal(enc) == adm
    assert encounter.to_internal(enc) == adm  # dispatcher picks IMP


# ─── visits ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("visit", VISITS, ids=lambda v: v["id"])
def test_visit_roundtrip(visit):
    enc = encounter.visit_to_fhir(visit)
    _revalidate(enc, Encounter)
    assert encounter.visit_to_internal(enc) == visit
    assert encounter.to_internal(enc) == visit  # dispatcher picks EMER


# ─── vitals (numeric-normalized; vitals projection uses raw read-back) ────────
def _norm_vital(d):
    out = dict(d)
    for k in ("temperature", "pulse", "bp_systolic", "bp_diastolic", "spo2", "respiratory_rate", "gcs"):
        if out.get(k) is not None:
            out[k] = float(out[k])
    return out


@pytest.mark.parametrize("vital", VITALS, ids=lambda v: v["id"])
def test_vitals_roundtrip(vital):
    obs_list = observation.vitals_to_fhir(vital)
    assert obs_list, "expected at least one Observation"
    for o in obs_list:
        _revalidate(o, Observation)
        assert o.id.split(".")[0] == vital["id"]
    recovered = observation.vitals_to_internal(obs_list)
    assert _norm_vital(recovered) == _norm_vital(vital)


def test_vitals_bp_panel_has_two_components():
    obs_list = observation.vitals_to_fhir(VITALS[0])
    bp = [o for o in obs_list if o.id.endswith(".85354-9")]
    assert len(bp) == 1 and len(bp[0].component) == 2


def test_vitals_critical_sets_interpretation():
    obs_list = observation.vitals_to_fhir(VITALS[1])  # is_critical=True
    assert all(o.interpretation for o in obs_list)


# ─── labs ─────────────────────────────────────────────────────────────────────
def test_lab_result_to_observation():
    row = {"id": "lab-1", "order_id": "o-1", "patient_token": "pt-1",
           "test_name": "Serum Potassium", "test_code": "K-001", "result_value": "6.8",
           "flag": "Critical", "reference_range": "3.5-5.0", "unit": "mEq/L",
           "reported_at": "2025-01-15T09:00:00+00:00"}
    obs = observation.lab_result_to_observation(row)
    reparsed = _revalidate(obs, Observation)
    assert obs.id == "lab-1"
    assert obs.valueQuantity.value == 6.8
    assert obs.interpretation  # Critical -> HH


# ─── patient (PSEUDONYMOUS — no PHI) ──────────────────────────────────────────
def test_patient_has_no_phi():
    p = patient.patient_token_to_patient("pt-123")
    _revalidate(p, Patient)
    assert p.name is None and p.birthDate is None and p.gender is None and p.telecom is None
    assert p.identifier[0].value == "pt-123"
    assert patient.to_internal(p) == {"patient_token": "pt-123"}

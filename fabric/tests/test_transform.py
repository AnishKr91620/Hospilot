"""
Transform tests — the core job: the DB's STANDARD (extension-free) FHIR R5 → the
normalized dict shapes the main backend wants.

We build realistic FHIR with the to_fhir mappers, then STRIP all extensions to
simulate the DB's standard output, and assert the transform recovers the data
from standard elements (not from Hospilot extensions).
"""

import json

from fhir.resources.location import Location
from fhir.resources.patient import Patient

from fhirgw.mappers import location as loc_map, encounter as enc_map, observation as obs_map
from service import transform as tx


class _Obs:
    """Minimal stand-in for grouping (only .id is read)."""
    def __init__(self, oid):
        self.id = oid


def test_vitals_grouping_db_measure_prefixed_ids():
    # the DB emits one Observation per measure, all sharing the reading uuid
    obs = [_Obs("hr-u1"), _Obs("temp-u1"), _Obs("bp-u1"), _Obs("gcs-u1"), _Obs("hr-u2")]
    groups = tx.group_vitals_by_reading(obs)
    assert set(groups.keys()) == {"u1", "u2"}
    assert len(groups["u1"]) == 4 and len(groups["u2"]) == 1


def test_patient_transform():
    p = Patient(
        id="tok-1",
        name=[{"family": "Doe", "given": ["Jane"]}],
        gender="female", birthDate="1990-01-01",
        identifier=[{"system": "https://hosp/uhid", "value": "UHID-1"}],
        telecom=[{"system": "phone", "value": "555-0100"}],
    )
    assert tx.patient_token(p) == "tok-1"          # token = Patient.id, not identifier
    d = tx.patient(p)
    assert d["patient_token"] == "tok-1"
    assert d["first_name"] == "Jane" and d["last_name"] == "Doe"
    assert d["uhid"] == "UHID-1" and d["gender"] == "female"


def strip_ext(model):
    """Return a copy of a fhir.resources model with all `extension` arrays removed."""
    d = json.loads(model.model_dump_json(exclude_none=True, by_alias=True))

    def _strip(x):
        if isinstance(x, dict):
            x.pop("extension", None)
            return {k: _strip(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_strip(i) for i in x]
        return x

    return type(model).model_validate(_strip(d))


def test_admission_from_standard_fhir():
    enc = strip_ext(enc_map.admission_to_fhir({
        "id": "adm-1", "patient_token": "pt-1", "bed_id": "B1",
        "admitted_at": "2025-01-15T10:30:00+00:00", "status": "admitted",
    }))
    assert not enc.extension                      # truly standard FHIR
    d = tx.admission(enc)
    assert d["id"] == "adm-1"
    assert d["patient_token"] == "pt-1"
    assert d["bed_id"] == "B1"
    assert d["admitted_at"].startswith("2025-01-15T10:30:00")
    assert d["status"] == "admitted"              # reverse-mapped from in-progress


def test_visit_from_standard_fhir():
    enc = strip_ext(enc_map.visit_to_fhir({
        "id": "v-1", "patient_token": "pt-2", "department_id": "dept-1",
        "arrived_at": "2025-01-15T16:00:00+00:00", "status": "waiting",
        "chief_complaint": "Chest pain", "triage_score": 2,
    }))
    d = tx.visit(enc)
    assert d["patient_token"] == "pt-2"
    assert d["department_id"] == "dept-1"
    assert d["chief_complaint"] == "Chest pain"
    # EMER keeps the FHIR status value (in-progress), not the IMP "admitted" reverse
    assert d["status"] == "in-progress"
    # triage_score came from an extension → not recoverable from pure standard FHIR
    assert d["triage_score"] is None


def test_vital_from_standard_fhir():
    obs = obs_map.vitals_to_fhir({
        "id": "vit-1", "patient_token": "pt-1", "recorded_at": "2025-01-15T14:00:00+00:00",
        "temperature": 37.2, "pulse": 85, "bp_systolic": 130, "bp_diastolic": 85,
        "spo2": 96, "respiratory_rate": 18, "gcs": 15, "is_critical": True,
    })
    stripped = [strip_ext(o) for o in obs]
    d = tx.vital(stripped)
    assert d["id"] == "vit-1"
    assert d["patient_token"] == "pt-1"
    assert d["pulse"] == 85
    assert d["bp_systolic"] == 130 and d["bp_diastolic"] == 85
    assert d["gcs"] == 15
    assert d["recorded_at"].startswith("2025-01-15T14:00:00")   # from effectiveDateTime
    assert d["is_critical"] is True                              # from interpretation=AA


def test_lab_from_standard_fhir():
    o = strip_ext(obs_map.lab_result_to_observation({
        "id": "L1", "patient_token": "pt-1", "test_code": "K-001", "test_name": "Serum Potassium",
        "result_value": "6.8", "unit": "mEq/L", "flag": "Critical", "reference_range": "3.5-5.0",
        "reported_at": "2025-01-15T13:00:00+00:00",
    }))
    d = tx.lab_result(o)
    assert d["id"] == "L1"
    assert d["patient_token"] == "pt-1"
    assert d["test_code"] == "K-001"
    assert d["result_value"] == 6.8
    assert d["unit"] == "mEq/L"
    assert d["flag"] == "Critical"                # reverse-mapped from interpretation HH
    assert d["reference_range"] == "3.5-5.0"


def test_bed_from_standard_partof_ward():
    # The DB spec exposes ward via partOf → ward Location (form=wa); build that shape.
    bed = Location(
        id="B1", status="active", name="ICU-01", mode="instance",
        form={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/location-physical-type",
                          "code": "bd", "display": "Bed"}]},
        operationalStatus={"system": "http://terminology.hl7.org/CodeSystem/v2-0116",
                           "code": "U", "display": "Unoccupied"},
        partOf={"reference": "Location/W1"},
    )
    d = tx.bed(bed, wards_by_id={"W1": "ICU"})
    assert d["id"] == "B1"
    assert d["bed_number"] == "ICU-01"
    assert d["status"] == "Available"             # from operationalStatus U
    assert d["ward"] == "ICU"                      # from partOf → ward name
    assert tx.is_icu_bed(d) is True

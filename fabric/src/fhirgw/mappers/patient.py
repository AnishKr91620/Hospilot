"""patient_token <-> FHIR Patient (PSEUDONYMOUS — identifier only, never any PHI).

Hospilot has no patient table; PHI lives in CarerOS. The FHIR Patient is a
referenceable anchor carrying only the opaque token, tagged PSEUDED (pseudonymized).

NOT LIVE in fabric/: no caller in src/ (only the also-dead views.py references
this module). Fabric's live inbound path, transform.py's patient(), reads full
demographics directly off the FHIR Patient CarerOS sends — it does not use this
mapper or its pseudonymization. The pseudonymized-Patient behavior described
here is real, but only in agentic-framework's separate copy of fhirgw, where
patient_token_to_patient() backs the live GET /fhir/Patient endpoint.
"""

from fhir.resources.patient import Patient

from fhirgw import identifiers as ID, terminology as T, narrative as N


def patient_token_to_patient(token: str) -> Patient:
    return Patient(
        id=str(token),
        identifier=[ID.patient_identifier(token)],
        meta={"security": [{"system": T.SYS_SECURITY,
                            "code": T.PSEUD_SECURITY_LABEL[0], "display": T.PSEUD_SECURITY_LABEL[1]}]},
        text=N.text(f"Pseudonymized patient {token}"),
    )


# alias matching the mapper naming convention
def to_fhir(token: str) -> Patient:
    return patient_token_to_patient(token)


def to_internal(patient: Patient) -> dict:
    token = None
    for i in (patient.identifier or []):
        sys = i.get("system") if isinstance(i, dict) else getattr(i, "system", None)
        if sys == ID.sys_patient_token():
            token = i.get("value") if isinstance(i, dict) else getattr(i, "value", None)
            break
    return {"patient_token": token or patient.id}

"""
Normalized REST API — the face Fabric exposes to the main backend.

Each route calls the service layer, which calls the DB's FHIR/financial APIs and
transforms the responses into the plain dict shapes the agents already use. Reads
are GET; writes are POST (translated to FHIR and sent to the DB). Errors are plain
JSON (404 via HTTPException).

Static sub-paths are declared before `/{id}` routes so they aren't shadowed.
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from clients import fhir_client as fc
from service import clinical, financial, writes, transform as tx, lab as lab_svc, pharmacy as pharmacy_svc

logger = logging.getLogger("normalized")
router = APIRouter()


async def _or_404(value, what: str):
    if value is None:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return value


# ─── beds ──────────────────────────────────────────────────────────────────────
@router.get("/beds")
async def beds():
    return await clinical.beds()


@router.get("/beds/available-icu")
async def beds_available_icu():
    return await clinical.available_icu_beds()


@router.get("/beds/dirty")
async def beds_dirty():
    return await clinical.dirty_beds()


@router.get("/beds/dirty-icu")
async def beds_dirty_icu():
    return await clinical.dirty_beds(icu_only=True)


@router.get("/beds/postop")
async def beds_postop():
    return [b for b in await clinical.beds()
            if not tx.is_icu_bed(b) and b.get("status") == "Available"]


@router.get("/beds/summary")
async def beds_summary():
    return await clinical.beds_summary()


@router.get("/beds/{bed_id}")
async def bed(bed_id: str):
    rid = bed_id if bed_id.startswith("bed-") else f"bed-{bed_id}"   # DB ids are bed-{uuid}
    loc = await fc.read_location(rid)
    return await _or_404(tx.bed(loc) if loc else None, f"Bed {bed_id}")


class BedStatus(BaseModel):
    status: str


@router.post("/beds/{bed_id}/status")
async def set_bed_status(bed_id: str, body: BedStatus):
    await writes.update_bed_status(bed_id, body.status)
    return {"ok": True, "id": bed_id, "status": body.status}


# ─── admissions ─────────────────────────────────────────────────────────────────
@router.get("/admissions")
async def admissions():
    return await clinical.all_admissions()


@router.get("/admissions/icu")
async def admissions_icu():
    return await clinical.icu_admissions()


@router.get("/admissions/non-icu")
async def admissions_non_icu():
    return await clinical.non_icu_admissions()


@router.get("/admissions/with-wards")
async def admissions_with_wards():
    return await clinical.admissions_with_wards()


@router.get("/admissions/discharge-eligible")
async def admissions_discharge_eligible():
    return [a for a in await clinical.all_admissions() if (a.get("status") in (None, "admitted"))]


@router.get("/admissions/discharge-ready")
async def admissions_discharge_ready():
    return [a for a in await clinical.all_admissions() if a.get("discharge_ready")]


@router.get("/admissions/discharge-ready-count")
async def admissions_discharge_ready_count():
    return {"count": await clinical.discharge_ready_count()}


@router.get("/admissions/discharge-horizon")
async def admissions_discharge_horizon(hours: int = Query(24)):
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    n = sum(1 for a in await clinical.all_admissions()
            if a.get("discharge_ready") or (a.get("expected_discharge_at") or "") and (a["expected_discharge_at"] <= cutoff))
    return {"hours": hours, "count": n}


class TransferPending(BaseModel):
    ids: list[str]


@router.post("/admissions/transfer-pending")
async def admissions_transfer_pending(body: TransferPending):
    await writes.set_admissions_transfer_pending(body.ids)
    return {"ok": True, "count": len(body.ids)}


@router.get("/admissions/{admission_id}")
async def admission(admission_id: str):
    rid = admission_id if admission_id.startswith("ipd-") else f"ipd-{admission_id}"   # DB ids are ipd-{uuid}
    enc = await fc.read_encounter(rid)
    return await _or_404(tx.admission(enc) if enc else None, f"Admission {admission_id}")


class DischargeReady(BaseModel):
    ready: bool
    blocked_reason: str | None = None


@router.post("/admissions/{admission_id}/discharge-ready")
async def set_discharge_ready(admission_id: str, body: DischargeReady):
    await writes.update_discharge_ready(admission_id, body.ready, body.blocked_reason)
    return {"ok": True, "id": admission_id, "ready": body.ready}


# ─── vitals ─────────────────────────────────────────────────────────────────────
@router.get("/vitals/latest")
async def vitals_latest(patient: str = Query(...)):
    return await clinical.latest_vitals(patient)


@router.get("/vitals/critical")
async def vitals_critical():
    return await clinical.critical_vitals()


@router.get("/vitals/observations/{observation_id}")
async def vital_observation(observation_id: str):
    obs = await fc.read_observation(observation_id)
    return await _or_404(obs, f"Observation {observation_id}")


@router.post("/vitals/{vital_id}/critical")
async def flag_vital_critical(vital_id: str):
    await writes.flag_critical_vital(vital_id)
    return {"ok": True, "id": vital_id, "is_critical": True}


# ─── visits / ER ────────────────────────────────────────────────────────────────
@router.get("/visits/er")
async def visits_er():
    return await clinical.er_visits()


@router.get("/visits/untriaged")
async def visits_untriaged():
    return [v for v in await clinical.er_visits() if v.get("triage_score") is None]


@router.get("/er/pressure")
async def er_pressure():
    return await clinical.er_pressure()


class BulkTriage(BaseModel):
    items: list[dict]


@router.post("/visits/triage/bulk")
async def visits_triage_bulk(body: BulkTriage):
    await writes.bulk_set_triage_scores(body.items)
    return {"ok": True, "count": len(body.items)}


class TriageScore(BaseModel):
    score: int


@router.post("/visits/{visit_id}/triage")
async def set_triage(visit_id: str, body: TriageScore):
    await writes.set_triage_score(visit_id, body.score)
    return {"ok": True, "id": visit_id, "score": body.score}


# ─── nursing tasks ──────────────────────────────────────────────────────────────
@router.get("/tasks/incomplete")
async def tasks_incomplete():
    return await clinical.incomplete_tasks()


@router.get("/tasks/overdue")
async def tasks_overdue():
    return await clinical.overdue_tasks()


@router.get("/tasks/completed-count")
async def tasks_completed_count(admission: str = Query(...)):
    return {"admission_id": admission, "count": await clinical.completed_task_count(admission)}


@router.get("/tasks")
async def tasks(admission: str | None = Query(None)):
    if admission:
        return await clinical.nursing_tasks_for(admission)
    return await clinical.incomplete_tasks()


# ─── labs ───────────────────────────────────────────────────────────────────────
@router.get("/labs/orders")
async def lab_orders_all():
    return await clinical.lab_orders()


@router.get("/labs/orders/pending")
async def lab_orders_pending():
    return await clinical.lab_orders()


@router.get("/labs/results")
async def lab_results(patient: str | None = Query(None), test_code: str | None = Query(None)):
    return await clinical.lab_results(patient_token=patient, test_code=test_code)


# ─── departments / patients ──────────────────────────────────────────────────────
@router.get("/departments")
async def departments():
    return await clinical.departments()


@router.get("/patients/tokens")
async def patient_tokens():
    return await clinical.patient_tokens()


@router.get("/patients")
async def patients(ids: str = Query(..., description="comma-separated patient tokens")):
    """{token: {first_name, last_name, uhid, ...}} — replaces db.hasura.get_patient_names."""
    toks = [t.strip() for t in ids.split(",") if t.strip()]
    return await clinical.patient_names(toks)


@router.get("/patients/by-mobile")
async def patient_by_mobile(mobile: str = Query(..., description="Phone number — any format; normalised to last 10 digits")):
    return await clinical.patient_by_mobile(mobile)


@router.get("/patients/{token}")
async def patient(token: str):
    return await _or_404(await clinical.patient(token), f"Patient {token}")


# ─── discharge summaries ────────────────────────────────────────────────────────
class AINote(BaseModel):
    note: str


@router.post("/discharge-summaries/{admission_id}/ai-note")
async def set_ai_note(admission_id: str, body: AINote):
    await writes.set_ai_discharge_note(admission_id, body.note)
    return {"ok": True, "admission_id": admission_id}


# ─── financial (DB's plain-REST financial API, passed through) ───────────────────
@router.get("/financial/invoices")
async def fin_invoices(
    payment_status: str | None = None,
    patient: str | None = None,
    invoice_type: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return await financial.invoices(
        payment_status=payment_status, patient=patient, invoice_type=invoice_type,
        limit=limit, offset=offset,
    )


@router.get("/financial/invoices/{invoice_id}/line-items")
async def fin_invoice_line_items(invoice_id: str):
    return await financial.invoice_line_items(invoice_id)


@router.get("/financial/claims")
async def fin_claims(
    status: str | None = None,
    patient: str | None = None,
    visit_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
):
    return await financial.claims(
        status=status, patient=patient, visit_id=visit_id, limit=limit, offset=offset,
    )


@router.get("/financial/claims/{claim_id}/line-items")
async def fin_claim_line_items(claim_id: str):
    return await financial.claim_line_items(claim_id)


@router.get("/financial/claims/{claim_id}/history")
async def fin_claim_history(claim_id: str):
    return await financial.claim_history(claim_id)


@router.get("/financial/claims/{claim_id}/queries")
async def fin_claim_queries(claim_id: str):
    return await financial.claim_queries(claim_id)


@router.get("/financial/payments")
async def fin_payments():
    return await financial.payments()


@router.get("/financial/payments/{payment_id}/entries")
async def fin_payment_entries(payment_id: str):
    return await financial.payment_entries(payment_id)


# ─── patient registration ─────────────────────────────────────────────────────
# In-memory store for pending registration requests (TTL handled by backend's
# 24h reaper; process restart is safe — backend re-sends on timeout).
import re as _re
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz

_pending_registrations: dict[str, dict] = {}


class _RegisterRequest(BaseModel):
    mobile: str
    name_hint: str | None = None
    session_id: str
    source: str = "patient_verification_agent"


@router.post("/patients/register", status_code=202)
async def register_patient(body: _RegisterRequest):
    """Receive a registration request from the backend, store it as pending, and
    return immediately. The actual patient creation is manual (DB side worklist).
    The diff poller detects the new patient and publishes hospilot.data.patient."""
    digits = _re.sub(r"\D", "", body.mobile)[-10:]
    request_id = f"reg_{_uuid.uuid4().hex[:8]}"
    _pending_registrations[request_id] = {
        "request_id": request_id,
        "mobile": digits,
        "mobile_display": body.mobile,
        "name_hint": body.name_hint,
        "session_id": body.session_id,
        "source": body.source,
        "status": "pending",
        "created_at": _dt.now(_tz.utc).isoformat(),
    }
    logger.info("patient registration pending  mobile=%s  session=%s  req=%s",
                digits, body.session_id, request_id)
    return {"request_id": request_id, "status": "pending"}


@router.get("/patients/register/pending")
async def pending_registrations():
    """Pending patient registration requests — polled by the DB-side staff worklist."""
    return list(_pending_registrations.values())


@router.delete("/patients/register/{request_id}")
async def complete_registration(request_id: str):
    """Mark a registration request complete (called when staff confirm patient created)."""
    entry = _pending_registrations.pop(request_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Registration request not found")
    logger.info("patient registration completed  req=%s", request_id)
    return {"request_id": request_id, "status": "completed"}


@router.get("/financial/refunds")
async def fin_refunds(invoice_id: str | None = None):
    return await financial.refunds(invoice_id=invoice_id)


@router.get("/financial/contracts")
async def fin_contracts():
    return await financial.contracts()


@router.get("/financial/contracts/{contract_id}/rates")
async def fin_contract_rates(contract_id: str):
    return await financial.contract_rates(contract_id)


@router.get("/financial/collections/{date}")
async def fin_collections(date: str):
    return await financial.collections(date)


@router.get("/financial/reconciliation/{date}")
async def fin_reconciliation(date: str):
    return await financial.reconciliation(date)


# ─── labs (extended) ─────────────────────────────────────────────────────────
# /labs/orders/pending and /labs/results are already above (FHIR-backed via clinical.py).
# The routes below are the additional lab agent endpoints.

@router.get("/labs/samples")
async def lab_samples():
    return await lab_svc.samples()


@router.get("/labs/analyzers")
async def lab_analyzers():
    return await lab_svc.analyzers()


@router.get("/labs/qc-logs")
async def lab_qc_logs(hours: int = Query(24)):
    return await lab_svc.qc_logs(hours=hours)


@router.get("/labs/reflex-rules")
async def lab_reflex_rules():
    return await lab_svc.reflex_rules()


@router.get("/labs/validation-rules")
async def lab_validation_rules():
    return await lab_svc.validation_rules()


@router.get("/labs/capacity")
async def lab_capacity(days: int = Query(30)):
    return await lab_svc.capacity_history(days=days)


@router.get("/labs/critical-escalations")
async def lab_critical_escalations():
    return await lab_svc.critical_escalations()


# ─── pharmacy ────────────────────────────────────────────────────────────────

@router.get("/pharmacy/orders")
async def pharmacy_orders():
    return await pharmacy_svc.orders()


@router.get("/pharmacy/orders/pending")
async def pharmacy_orders_pending():
    return await pharmacy_svc.pending_orders()


@router.get("/pharmacy/orders/stat")
async def pharmacy_orders_stat():
    return await pharmacy_svc.stat_orders()


@router.get("/pharmacy/inventory")
async def pharmacy_inventory():
    return await pharmacy_svc.inventory()


@router.get("/pharmacy/dispensing-log")
async def pharmacy_dispensing_log(hours: int = Query(8)):
    return await pharmacy_svc.dispensing_log(hours=hours)


@router.get("/pharmacy/interactions")
async def pharmacy_interactions():
    return await pharmacy_svc.interaction_rules()


@router.get("/pharmacy/substitutions")
async def pharmacy_substitutions():
    return await pharmacy_svc.substitution_rules()


@router.get("/pharmacy/controlled-log")
async def pharmacy_controlled_log(hours: int = Query(24)):
    return await pharmacy_svc.controlled_log(hours=hours)


@router.get("/pharmacy/capacity")
async def pharmacy_capacity(days: int = Query(30)):
    return await pharmacy_svc.capacity_history(days=days)

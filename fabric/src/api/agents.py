"""Agent-facing endpoints: OT, Ambulance, Appointments.

These endpoints are designed for careros-hospilot-backend agents that need
to query operating-theatre status, ambulance fleet, and appointment data.
"""

from fastapi import APIRouter, Query
from typing import Optional

from service import ambulance as amb_svc
from service import appointments as appt_svc
from service import ot as ot_svc
from service import writes as writes_svc

router = APIRouter()


# ── OT ───────────────────────────────────────────────────────────────────────

@router.get("/ot/rooms", summary="List all OT rooms with capacity and equipment")
async def get_ot_rooms():
    return await ot_svc.rooms()


@router.get("/ot/room-status", summary="Live surgery status for each OT room")
async def get_ot_room_status():
    return await ot_svc.room_status()


@router.get("/ot/surgery-schedule", summary="Scheduled surgeries with staff and patient details")
async def get_surgery_schedule():
    return await ot_svc.surgery_schedule()


@router.get("/ot/equipment-usage", summary="OT equipment usage records (empty if none)")
async def get_equipment_usage():
    return await ot_svc.equipment_usage()


@router.get("/ot/surgeries", summary="All surgeries with pre/post-op notes and outcomes")
async def get_surgeries():
    return await ot_svc.surgeries()


@router.post(
    "/ot/surgery-schedule/{surgery_id}/reschedule",
    summary="Reschedule a surgery to a new theatre slot (queued as a pending change)",
    status_code=202,
)
async def reschedule_surgery(surgery_id: str, body: dict):
    fields = {k: body.get(k) for k in
              ("scheduled_date", "scheduled_start_time", "scheduled_end_time", "ot_room_id", "status")}
    return await writes_svc.reschedule_surgery(surgery_id, fields)


# ── Ambulance ────────────────────────────────────────────────────────────────

@router.get("/ambulances", summary="Ambulance fleet with live status, location, and ETA")
async def get_ambulance_fleet():
    return await amb_svc.fleet()


# ── Appointments ─────────────────────────────────────────────────────────────

@router.get("/appointments", summary="List appointments with optional filters")
async def get_appointments(
    patient_id: Optional[str] = Query(None, description="Filter by patient ID"),
    provider_id: Optional[str] = Query(None, description="Filter by provider/doctor ID"),
    department_id: Optional[str] = Query(None, description="Filter by department ID"),
    status: Optional[str] = Query(None, description="Filter by appointment status"),
    date: Optional[str] = Query(None, description="Filter by appointment date (YYYY-MM-DD)"),
):
    return await appt_svc.list_all(
        patient_id=patient_id,
        provider_id=provider_id,
        department_id=department_id,
        status=status,
        date=date,
    )


@router.post("/appointments", summary="Create a new appointment", status_code=201)
async def create_appointment(body: dict):
    return await appt_svc.create(body)


@router.get("/appointments/slots", summary="List available appointment slots")
async def get_appointment_slots(
    provider_id: Optional[str] = Query(None, description="Filter by provider ID"),
    date: Optional[str] = Query(None, description="Filter by slot date (YYYY-MM-DD)"),
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
):
    return await appt_svc.slots(
        provider_id=provider_id,
        date=date,
        specialization=specialization,
    )


@router.patch(
    "/appointments/slots/{slot_id}/book",
    summary="Book an appointment slot (mark as booked)",
)
async def book_slot(slot_id: str):
    return await appt_svc.book_slot(slot_id)

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

import pytest
from django.db import connections

from appointments import services
from appointments.exceptions import (
    AlreadyCancelled,
    AppointmentCancelled,
    AppointmentNotFound,
    AppointmentStarted,
    DoctorInactive,
    OffGrid,
    OutsideWorkingHours,
    ReasonRequired,
    SameSlot,
    SlotInPast,
    SlotTaken,
    TooSoon,
)
from appointments.models import Appointment

pytestmark = pytest.mark.django_db

NAIROBI = ZoneInfo("Africa/Nairobi")


def at(day, h, m=0):
    """Clinic-local aware datetime in January 2030 (the 7th is a Monday)."""
    return datetime(2030, 1, day, h, m, tzinfo=NAIROBI)


NOW = at(7, 9)  # Monday 09:00 clinic time; the booking lead time is 60 minutes


def book(doctor, patient, start, **kw):
    return services.book_appointment(doctor=doctor, patient=patient, start=start, now=NOW, **kw)


# --- Booking: happy path ------------------------------------------------------------------


def test_books_a_valid_slot(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    assert appt.status == Appointment.Status.BOOKED
    assert appt.start_time == at(7, 14) and appt.end_time == at(7, 14, 30)
    assert appt.start_time.utcoffset() == timedelta(0)  # stored as UTC


def test_naive_datetime_is_interpreted_as_clinic_local(doctor, patient):
    appt = book(doctor, patient, datetime(2030, 1, 7, 14, 0))
    assert appt.start_time == at(7, 14)


def test_last_slot_of_the_day_and_exact_lead_time_boundary_are_allowed(doctor, patient):
    book(doctor, patient, at(7, 16, 30))  # ends exactly at closing
    book(doctor, patient, at(7, 10))      # exactly now + 60 minutes


# --- Booking: validation --------------------------------------------------------------------


@pytest.mark.parametrize(
    "start, error",
    [
        (at(7, 14, 15), OffGrid),
        (at(7, 7, 30), OutsideWorkingHours),   # before opening
        (at(7, 12), OutsideWorkingHours),      # lunch break
        # at closing: slot would end after hours
        (at(7, 17), OutsideWorkingHours),
        (at(12, 10), OutsideWorkingHours),     # Saturday: doctor doesn't work
        (at(13, 10), OutsideWorkingHours),     # Sunday
        # earlier today, inside working hours
        (at(7, 8), SlotInPast),
        (at(7, 9), SlotInPast),                # exactly now
        # in the future but inside the lead time
        (at(7, 9, 30), TooSoon),
    ],
)
def test_invalid_slots_are_rejected_with_the_right_error(doctor, patient, start, error):
    with pytest.raises(error):
        book(doctor, patient, start)
    assert Appointment.objects.count() == 0


def test_inactive_doctor_cannot_be_booked(doctor, patient):
    doctor.is_active = False
    doctor.save()
    with pytest.raises(DoctorInactive):
        book(doctor, patient, at(7, 14))


def test_error_codes_and_statuses():
    assert (OffGrid.status_code, OffGrid.code) == (400, "off_grid")
    assert (SlotTaken.status_code, SlotTaken.code) == (409, "slot_taken")
    assert (AlreadyCancelled.status_code, AlreadyCancelled.code) == (
        409, "already_cancelled")
    assert (AppointmentNotFound.status_code, AppointmentNotFound.code) == (
        404, "appointment_not_found")


# --- Booking: conflicts ---------------------------------------------------------------------


def test_booked_slot_cannot_be_taken_by_someone_else(doctor, patient, other_patient):
    book(doctor, patient, at(7, 14))
    with pytest.raises(SlotTaken):
        book(doctor, other_patient, at(7, 14))
    assert Appointment.objects.count() == 1


def test_same_time_with_a_different_doctor_is_fine(doctor, other_doctor, patient, other_patient, make_doctor):
    second = make_doctor(email="second@example.com", name="Dr. Second")
    book(doctor, patient, at(7, 14))
    book(second, other_patient, at(7, 14))


def test_cancelled_slot_can_be_booked_again(doctor, patient, other_patient):
    first = book(doctor, patient, at(7, 14))
    services.cancel_appointment(
        appointment_id=first.id, reason="Unwell", cancelled_by="patient", now=NOW)
    second = book(doctor, other_patient, at(7, 14))
    assert second.status == Appointment.Status.BOOKED


@pytest.mark.django_db(transaction=True)
def test_concurrent_bookings_of_one_slot_exactly_one_wins(doctor, patient, other_patient):
    """Both requests pass validation; only the database constraint can break the tie."""
    barrier = threading.Barrier(2)

    def attempt(who):
        try:
            barrier.wait(timeout=10)
            book(doctor, who, at(7, 14))
            return "booked"
        except SlotTaken:
            return "taken"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(attempt, [patient, other_patient]))

    assert outcomes == ["booked", "taken"]
    assert Appointment.objects.filter(status="booked").count() == 1


# --- Cancel -------------------------------------------------------------------------------------


def test_cancel_records_who_why_and_when_and_frees_the_slot(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    result = services.cancel_appointment(
        appointment_id=appt.id, reason="  Doctor unwell ", cancelled_by="doctor", now=NOW)
    appt.refresh_from_db()
    assert result.id == appt.id
    assert appt.status == Appointment.Status.CANCELLED
    assert appt.cancellation_reason == "Doctor unwell"  # trimmed
    assert appt.cancelled_by == "doctor" and appt.cancelled_at == NOW
    assert at(7, 14) in services.get_availability(
        doctor, at(7, 14).date(), now=NOW)


def test_cancelling_twice_is_a_conflict(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    services.cancel_appointment(
        appointment_id=appt.id, reason="x", cancelled_by="patient", now=NOW)
    with pytest.raises(AlreadyCancelled):
        services.cancel_appointment(
            appointment_id=appt.id, reason="again", cancelled_by="patient", now=NOW)


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_cancel_requires_a_reason(doctor, patient, reason):
    appt = book(doctor, patient, at(7, 14))
    with pytest.raises(ReasonRequired):
        services.cancel_appointment(
            appointment_id=appt.id, reason=reason, cancelled_by="patient", now=NOW)
    appt.refresh_from_db()
    assert appt.status == Appointment.Status.BOOKED


def test_cannot_cancel_an_appointment_that_has_started(doctor, patient, make_appointment):
    appt = make_appointment(doctor, patient, at(
        7, 8).astimezone(dt_timezone.utc))  # 08:00, NOW is 09:00
    with pytest.raises(AppointmentStarted):
        services.cancel_appointment(
            appointment_id=appt.id, reason="late", cancelled_by="patient", now=NOW)


def test_cancel_unknown_appointment_is_not_found():
    with pytest.raises(AppointmentNotFound):
        services.cancel_appointment(
            appointment_id=999999, reason="x", cancelled_by="patient", now=NOW)


# --- Reschedule -----------------------------------------------------------------------------------


def test_reschedule_moves_in_place_and_frees_the_old_slot(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    moved = services.reschedule_appointment(
        appointment_id=appt.id, new_start=at(8, 10), now=NOW)

    assert moved.id == appt.id and Appointment.objects.count() == 1
    assert moved.start_time == at(8, 10) and moved.end_time == at(8, 10, 30)
    assert moved.status == Appointment.Status.BOOKED
    assert at(7, 14) in services.get_availability(
        doctor, at(7, 14).date(), now=NOW)
    assert at(8, 10) not in services.get_availability(
        doctor, at(8, 10).date(), now=NOW)


@pytest.mark.parametrize(
    "new_start, error",
    [
        (at(8, 10, 15), OffGrid),
        (at(8, 12), OutsideWorkingHours),
        (at(12, 10), OutsideWorkingHours),
        (at(7, 8), SlotInPast),
        (at(7, 9, 30), TooSoon),
    ],
)
def test_reschedule_target_is_validated_like_a_fresh_booking(doctor, patient, new_start, error):
    appt = book(doctor, patient, at(7, 14))
    with pytest.raises(error):
        services.reschedule_appointment(
            appointment_id=appt.id, new_start=new_start, now=NOW)
    appt.refresh_from_db()
    assert appt.start_time == at(7, 14)  # unchanged


def test_reschedule_onto_a_taken_slot_is_a_conflict_and_keeps_the_original(doctor, patient, other_patient):
    mine = book(doctor, patient, at(7, 14))
    book(doctor, other_patient, at(8, 10))
    with pytest.raises(SlotTaken):
        services.reschedule_appointment(
            appointment_id=mine.id, new_start=at(8, 10), now=NOW)
    mine.refresh_from_db()
    assert mine.start_time == at(
        7, 14) and mine.status == Appointment.Status.BOOKED


def test_reschedule_to_the_same_slot_is_rejected(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    with pytest.raises(SameSlot):
        services.reschedule_appointment(
            appointment_id=appt.id, new_start=at(7, 14), now=NOW)


def test_cancelled_appointment_cannot_be_rescheduled(doctor, patient):
    appt = book(doctor, patient, at(7, 14))
    services.cancel_appointment(
        appointment_id=appt.id, reason="x", cancelled_by="patient", now=NOW)
    with pytest.raises(AppointmentCancelled):
        services.reschedule_appointment(
            appointment_id=appt.id, new_start=at(8, 10), now=NOW)


def test_started_appointment_cannot_be_rescheduled(doctor, patient, make_appointment):
    appt = make_appointment(doctor, patient, at(
        7, 8).astimezone(dt_timezone.utc))
    with pytest.raises(AppointmentStarted):
        services.reschedule_appointment(
            appointment_id=appt.id, new_start=at(8, 10), now=NOW)


def test_reschedule_unknown_appointment_is_not_found():
    with pytest.raises(AppointmentNotFound):
        services.reschedule_appointment(
            appointment_id=999999, new_start=at(8, 10), now=NOW)


# --- Availability ---------------------------------------------------------------------------------


def test_full_day_has_14_slots_and_a_lunch_gap(doctor):
    result = services.get_availability(
        doctor, at(8, 0).date(), now=NOW)  # Tuesday
    assert len(result) == 14
    assert result == sorted(result)
    assert at(8, 12) not in result and at(8, 13) not in result


def test_availability_excludes_booked_slots_but_not_cancelled_ones(doctor, patient, other_patient):
    kept = book(doctor, patient, at(8, 9))
    gone = book(doctor, other_patient, at(8, 9, 30))
    services.cancel_appointment(
        appointment_id=gone.id, reason="x", cancelled_by="patient", now=NOW)
    result = services.get_availability(doctor, at(8, 0).date(), now=NOW)
    assert at(8, 9) not in result and at(
        8, 9, 30) in result and len(result) == 13


def test_availability_ignores_other_doctors_bookings(doctor, other_doctor, patient):
    book(doctor, patient, at(8, 9))
    assert len(services.get_availability(other_doctor, at(
        8, 0).date(), now=NOW)) == 0  # no hours set
    assert at(8, 9) not in services.get_availability(
        doctor, at(8, 0).date(), now=NOW)


def test_availability_today_hides_slots_inside_the_lead_time(doctor):
    result = services.get_availability(doctor, at(
        7, 0).date(), now=NOW)  # NOW = Mon 09:00, lead 60 min
    assert result[0] == at(7, 10) and len(result) == 10


def test_availability_for_a_past_day_is_empty(doctor):
    assert services.get_availability(doctor, at(4, 0).date(), now=NOW) == []


def test_availability_for_a_day_off_is_empty(doctor):
    assert services.get_availability(
        doctor, at(13, 0).date(), now=NOW) == []  # Sunday

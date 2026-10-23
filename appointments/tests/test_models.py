from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from appointments.models import Appointment

pytestmark = pytest.mark.django_db


def cancel(appt, reason="Unwell", by="patient"):
    appt.status = Appointment.Status.CANCELLED
    appt.cancellation_reason = reason
    appt.cancelled_by = by
    appt.cancelled_at = timezone.now()
    appt.save()


# --- The double-booking guard -------------------------------------------------
def test_same_doctor_same_start_cannot_be_booked_twice(doctor, patient, other_patient, make_appointment, slot_start):
    make_appointment(doctor, patient, slot_start)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_appointment(doctor, other_patient, slot_start)


def test_same_patient_cannot_rebook_the_same_slot(doctor, patient, make_appointment, slot_start):
    make_appointment(doctor, patient, slot_start)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_appointment(doctor, patient, slot_start)


def test_cancelling_frees_the_slot(doctor, patient, other_patient, make_appointment, slot_start):
    first = make_appointment(doctor, patient, slot_start)
    cancel(first)
    second = make_appointment(doctor, other_patient,
                              slot_start)  # no IntegrityError
    assert second.status == Appointment.Status.BOOKED
    assert Appointment.objects.filter(
        doctor=doctor, start_time=slot_start).count() == 2  # history kept


def test_many_cancelled_rows_can_share_a_slot(doctor, patient, make_appointment, slot_start):
    for _ in range(3):
        cancel(make_appointment(doctor, patient, slot_start))
    assert Appointment.objects.filter(status="cancelled").count() == 3


def test_different_doctors_can_be_booked_at_the_same_time(doctor, other_doctor, patient, other_patient, make_appointment, slot_start):
    make_appointment(doctor, patient, slot_start)
    make_appointment(other_doctor, other_patient, slot_start)


def test_adjacent_slots_do_not_conflict(doctor, patient, make_appointment, slot_start):
    make_appointment(doctor, patient, slot_start)
    make_appointment(doctor, patient, slot_start + timedelta(minutes=30))


# --- Row-level integrity ------------------------------------------------------
def test_end_must_be_after_start(doctor, patient, slot_start):
    with pytest.raises(IntegrityError), transaction.atomic():
        Appointment.objects.create(
            doctor=doctor, patient=patient, start_time=slot_start, end_time=slot_start)


def test_cancelled_row_requires_reason_actor_and_timestamp(doctor, patient, make_appointment, slot_start):
    appt = make_appointment(doctor, patient, slot_start)
    appt.status = Appointment.Status.CANCELLED  # nothing else filled in
    with pytest.raises(IntegrityError), transaction.atomic():
        appt.save()


def test_cancelled_row_rejects_blank_reason(doctor, patient, make_appointment, slot_start):
    appt = make_appointment(doctor, patient, slot_start)
    with pytest.raises(IntegrityError), transaction.atomic():
        cancel(appt, reason="")


def test_booked_row_cannot_carry_cancellation_data(doctor, patient, make_appointment, slot_start):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_appointment(doctor, patient, slot_start, cancelled_by="patient")


def test_doctor_with_appointments_cannot_be_deleted(doctor, patient, make_appointment, slot_start):
    from django.db.models import ProtectedError

    make_appointment(doctor, patient, slot_start)
    with pytest.raises(ProtectedError):
        doctor.delete()

from datetime import datetime, time, timedelta, timezone as dt_timezone

import pytest

from accounts.models import Patient, Role, User
from appointments.models import Appointment
from doctors.models import Doctor, WorkingHours

PASSWORD = "S3cure-pass-phrase"


@pytest.fixture
def patient(db):
    user = User.objects.create_user(
        email="patient@example.com", password=PASSWORD)
    return Patient.objects.create(user=user, full_name="Pat Ient")


@pytest.fixture
def other_patient(db):
    user = User.objects.create_user(
        email="other@example.com", password=PASSWORD)
    return Patient.objects.create(user=user, full_name="Other Patient")


@pytest.fixture
def make_doctor(db):
    """A doctor is a user (role=doctor) plus a profile, optionally with Mon-Fri hours."""

    def _make(email="doctor@example.com", name="Dr. Test", working=True, **extra):
        user = User.objects.create_user(
            email=email, password=PASSWORD, role=Role.DOCTOR)
        doc = Doctor.objects.create(
            user=user, full_name=name, specialty="GP", **extra)
        if working:
            for weekday in range(5):
                WorkingHours.objects.create(
                    doctor=doc, weekday=weekday, start_time=time(8), end_time=time(12))
                WorkingHours.objects.create(
                    doctor=doc, weekday=weekday, start_time=time(14), end_time=time(17))
        return doc

    return _make


@pytest.fixture
def doctor(make_doctor):
    return make_doctor()


@pytest.fixture
def other_doctor(make_doctor):
    return make_doctor(email="other-doctor@example.com", name="Dr. Other", working=False)


@pytest.fixture
def slot_start():
    """A fixed future-ish UTC instant on the slot grid, for model-level tests."""
    return datetime(2030, 1, 7, 7, 0, tzinfo=dt_timezone.utc)  # Monday 10:00 Nairobi


@pytest.fixture
def make_appointment(db):
    def _make(doctor, patient, start, **extra):
        return Appointment.objects.create(
            doctor=doctor, patient=patient, start_time=start, end_time=start + timedelta(minutes=30), **extra
        )

    return _make

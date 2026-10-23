from datetime import time

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import Role, User
from doctors.models import Doctor, WorkingHours

pytestmark = pytest.mark.django_db


def hours(doctor, start, end, weekday=0):
    return WorkingHours(doctor=doctor, weekday=weekday, start_time=start, end_time=end)


def test_lunch_break_is_two_non_overlapping_intervals(doctor):
    # The fixture already has 08-12 and 14-17 on Monday; both pass validation.
    for wh in doctor.working_hours.filter(weekday=0):
        wh.full_clean()
    assert doctor.working_hours.filter(weekday=0).count() == 2


@pytest.mark.parametrize("start", [time(9, 15), time(9, 45), time(9, 0, 30)])
def test_working_hours_must_sit_on_30_minute_grid(doctor, start):
    with pytest.raises(ValidationError):
        hours(doctor, start, time(11, 0), weekday=6).full_clean()


def test_end_must_be_after_start(doctor):
    with pytest.raises(ValidationError):
        hours(doctor, time(11, 0), time(10, 0), weekday=6).full_clean()


def test_end_after_start_is_also_enforced_by_the_database(doctor):
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkingHours.objects.create(
            doctor=doctor, weekday=6, start_time=time(11), end_time=time(10))


def test_overlapping_intervals_are_rejected(doctor):
    with pytest.raises(ValidationError, match="overlap"):
        hours(doctor, time(11, 0), time(13, 0)).full_clean()


def test_adjacent_intervals_are_allowed(doctor):
    hours(doctor, time(12, 0), time(14, 0)).full_clean()


def test_same_hours_on_other_weekday_or_doctor_do_not_overlap(doctor, other_doctor):
    hours(doctor, time(8), time(12), weekday=5).full_clean()
    hours(other_doctor, time(8), time(12), weekday=0).full_clean()


def test_doctor_requires_a_login():
    with pytest.raises(IntegrityError), transaction.atomic():
        Doctor.objects.create(full_name="No Login")


def test_doctor_with_user_cannot_have_user_deleted():
    from django.db.models import ProtectedError

    user = User.objects.create_user(
        email="gone@example.com", password="x", role=Role.DOCTOR)
    Doctor.objects.create(user=user, full_name="Dr. Gone")
    with pytest.raises(ProtectedError):
        user.delete()


def test_linked_user_must_have_doctor_role():
    patient_user = User.objects.create_user(
        email="p@example.com", password="x")
    with pytest.raises(ValidationError) as exc:
        Doctor(full_name="Bad Link", user=patient_user).full_clean()
    assert "user" in exc.value.message_dict


def test_doctor_user_link_is_one_to_one():
    user = User.objects.create_user(
        email="d@example.com", password="x", role=Role.DOCTOR)
    Doctor.objects.create(full_name="First", user=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        Doctor.objects.create(full_name="Second", user=user)

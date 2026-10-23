import pytest

from accounts.models import Role, User
from accounts.permissions import STAFF_GROUP

pytestmark = pytest.mark.django_db


def make(email, **extra):
    return User.objects.create_user(email=email, password="S3cure-pass-phrase", **extra)


def fresh(user):
    return User.objects.get(pk=user.pk)


def test_staff_user_joins_the_clinic_staff_group():
    staff = make("s@example.com", role=Role.STAFF)
    assert staff.groups.filter(name=STAFF_GROUP).exists()


def test_staff_permissions_are_exactly_what_the_workflow_needs():
    staff = fresh(make("s@example.com", role=Role.STAFF))
    for perm in ("doctors.add_doctor", "doctors.change_doctor", "doctors.add_workinghours",
                 "doctors.delete_workinghours", "accounts.view_patient", "appointments.view_appointment",
                 "appointments.view_appointment"):
        assert staff.has_perm(perm), perm
    for perm in ("accounts.add_user", "accounts.change_user", "auth.change_group", "doctors.delete_doctor",
                 "appointments.change_appointment", "appointments.add_appointment"):
        assert not staff.has_perm(perm), perm


def test_demoting_staff_removes_group_and_access():
    user = make("s@example.com", role=Role.STAFF)
    user.role = Role.PATIENT
    user.save()
    user = fresh(user)
    assert not user.groups.filter(name=STAFF_GROUP).exists()
    assert not user.has_perm("doctors.add_doctor")


def test_patients_and_doctors_are_never_in_the_group():
    assert not make("p@example.com").groups.exists()
    assert not make("d@example.com", role=Role.DOCTOR).groups.exists()


def test_superuser_is_not_added_to_the_group():
    root = User.objects.create_superuser(
        email="root@example.com", password="S3cure-pass-phrase")
    assert not root.groups.exists()

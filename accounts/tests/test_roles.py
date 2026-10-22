import pytest
from rest_framework.test import APIClient

from accounts.models import Role, User

pytestmark = pytest.mark.django_db


def make(email="u@example.com", **extra):
    return User.objects.create_user(email=email, password="S3cure-pass-phrase", **extra)


def test_default_role_is_patient_and_not_staff():
    user = make()
    assert user.role == Role.PATIENT
    assert user.is_staff is False


@pytest.mark.parametrize("role, expected", [(Role.PATIENT, False), (Role.DOCTOR, False), (Role.STAFF, True)])
def test_is_staff_is_derived_from_role_on_create(role, expected):
    assert make(role=role).is_staff is expected


def test_is_staff_cannot_be_set_directly():
    assert make(is_staff=True).is_staff is False  # role is patient -> signal wins


def test_promoting_to_staff_sets_is_staff():
    user = make()
    user.role = Role.STAFF
    user.save()
    user.refresh_from_db()
    assert user.is_staff is True


def test_demoting_from_staff_clears_is_staff():
    user = make(role=Role.STAFF)
    user.role = Role.DOCTOR
    user.save()
    user.refresh_from_db()
    assert user.is_staff is False


def test_superuser_keeps_admin_access_and_gets_staff_role():
    admin = User.objects.create_superuser(email="root@example.com", password="S3cure-pass-phrase")
    assert admin.role == Role.STAFF
    assert admin.is_staff is True and admin.is_superuser is True


def test_registration_ignores_role_in_payload():
    resp = APIClient().post(
        "/api/auth/users/",
        {"email": "sneaky@example.com", "password": "S3cure-pass-phrase", "full_name": "Sneaky", "role": "staff"},
        format="json",
    )
    assert resp.status_code == 201
    user = User.objects.get(email="sneaky@example.com")
    assert user.role == Role.PATIENT and user.is_staff is False

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Role, User
from doctors.models import Doctor

pytestmark = pytest.mark.django_db

PASSWORD = "S3cure-pass-phrase"
INLINE = {  # empty working-hours inline formset
    "working_hours-TOTAL_FORMS": "0",
    "working_hours-INITIAL_FORMS": "0",
    "working_hours-MIN_NUM_FORMS": "0",
    "working_hours-MAX_NUM_FORMS": "1000",
}


def new_doctor_payload(**overrides):
    return {
        "email": "new.doctor@example.com",
        "password": PASSWORD,
        "full_name": "Dr. New",
        "specialty": "ENT",
        "is_active": "on",
        **INLINE,
        **overrides,
    }


@pytest.fixture
def staff_client(db):
    staff = User.objects.create_user(
        email="staff@example.com", password=PASSWORD, role=Role.STAFF)
    client = APIClient()
    client.force_login(staff)
    return client


def test_staff_creates_doctor_login_and_profile_in_one_step(staff_client):
    resp = staff_client.post(
        reverse("admin:doctors_doctor_add"), new_doctor_payload())
    assert resp.status_code == 302, getattr(resp, "content", b"")[:500]

    doctor = Doctor.objects.get(user__email="new.doctor@example.com")
    assert doctor.user.role == Role.DOCTOR and doctor.user.is_staff is False
    assert doctor.full_name == "Dr. New"


def test_new_doctor_can_log_in_with_the_password_staff_set(staff_client):
    staff_client.post(reverse("admin:doctors_doctor_add"),
                      new_doctor_payload())
    resp = APIClient().post("/api/auth/login/",
                            {"email": "new.doctor@example.com", "password": PASSWORD}, format="json")
    assert resp.status_code == 200 and "access" in resp.json()


def test_duplicate_email_is_rejected_and_nothing_is_created(staff_client, doctor):
    resp = staff_client.post(reverse(
        "admin:doctors_doctor_add"), new_doctor_payload(email=doctor.user.email))
    assert resp.status_code == 200  # form re-rendered with errors
    assert Doctor.objects.count() == 1
    assert User.objects.filter(role=Role.DOCTOR).count() == 1


def test_weak_password_is_rejected_and_no_user_is_left_behind(staff_client):
    resp = staff_client.post(
        reverse("admin:doctors_doctor_add"), new_doctor_payload(password="12345678"))
    assert resp.status_code == 200
    assert not User.objects.filter(email="new.doctor@example.com").exists()


def test_staff_can_reset_a_doctors_password(staff_client, doctor):
    payload = {
        "new_password": "An0ther-strong-pass",
        "full_name": doctor.full_name,
        "specialty": "GP",
        "is_active": "on",
        "working_hours-TOTAL_FORMS": "0",
        "working_hours-INITIAL_FORMS": "0",
        "working_hours-MIN_NUM_FORMS": "0",
        "working_hours-MAX_NUM_FORMS": "1000",
    }
    resp = staff_client.post(
        reverse("admin:doctors_doctor_change", args=[doctor.pk]), payload)
    assert resp.status_code == 302
    doctor.user.refresh_from_db()
    assert doctor.user.check_password("An0ther-strong-pass")


def test_doctors_and_patients_cannot_use_the_admin(doctor, patient):
    for user in (doctor.user, patient.user):
        client = APIClient()
        client.force_login(user)
        # bounced to admin login
        assert client.get(reverse("admin:index")).status_code == 302

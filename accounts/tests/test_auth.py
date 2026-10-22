import pytest
from rest_framework.test import APIClient

from accounts.models import Patient, User

pytestmark = pytest.mark.django_db

REGISTER = "/api/auth/users/"
LOGIN = "/api/auth/jwt/create/"
ME = "/api/auth/users/me/"

PAYLOAD = {
    "email": "jane@example.com",
    "password": "S3cure-pass-word",
    "full_name": "Jane Wanjiru",
    "phone": "+254700000000",
}


@pytest.fixture
def client():
    return APIClient()


def test_register_creates_user_and_patient_profile(client):
    resp = client.post(REGISTER, PAYLOAD, format="json")
    assert resp.status_code == 201, resp.content
    assert "password" not in resp.json()

    user = User.objects.get(email="jane@example.com")
    assert user.role == "patient" and user.is_staff is False
    assert Patient.objects.get(user=user).full_name == "Jane Wanjiru"


def test_register_requires_full_name(client):
    payload = {k: v for k, v in PAYLOAD.items() if k != "full_name"}
    resp = client.post(REGISTER, payload, format="json")
    assert resp.status_code == 400
    assert "full_name" in resp.json()


def test_register_rejects_weak_password(client):
    resp = client.post(
        REGISTER, {**PAYLOAD, "password": "12345678"}, format="json")
    assert resp.status_code == 400
    assert Patient.objects.count() == 0  # nothing half-created


def test_login_and_me_returns_patient_id(client):
    client.post(REGISTER, PAYLOAD, format="json")
    token = client.post(
        LOGIN, {"email": PAYLOAD["email"], "password": PAYLOAD["password"]}, format="json")
    assert token.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.json()['access']}")

    me = client.get(ME)
    assert me.status_code == 200
    assert me.json()["patient_id"] == Patient.objects.get().id
    assert me.json()["role"] == "patient"


def test_protected_endpoint_requires_token(client):
    assert client.get(ME).status_code == 401

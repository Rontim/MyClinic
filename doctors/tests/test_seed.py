import pytest
from django.core.management import CommandError, call_command

from accounts.models import Role, User
from doctors.models import Doctor, WorkingHours

pytestmark = pytest.mark.django_db


def test_seed_creates_five_doctors_with_logins_and_hours():
    call_command("seed_doctors", password="S3cure-pass-phrase")
    assert Doctor.objects.count() == 5
    for doctor in Doctor.objects.select_related("user"):
        assert doctor.user.role == Role.DOCTOR
        assert doctor.user.check_password("S3cure-pass-phrase")
        assert doctor.working_hours.filter(weekday__lte=4).count() == 10
    assert WorkingHours.objects.filter(weekday=5).count() == 3


def test_seed_is_idempotent_and_does_not_reset_passwords():
    call_command("seed_doctors", password="S3cure-pass-phrase")
    call_command("seed_doctors", password="Different-pass-123")
    assert Doctor.objects.count() == 5 and User.objects.count() == 5
    assert User.objects.first().check_password("S3cure-pass-phrase")


def test_seed_generates_a_password_when_none_given(capsys):
    call_command("seed_doctors")
    out = capsys.readouterr().out
    assert "Generated password" in out
    password = out.split("(shown once): ")[1].strip()
    assert User.objects.get(
        email="amina.otieno@clinic.example").check_password(password)


def test_seed_rejects_a_weak_password():
    with pytest.raises(CommandError):
        call_command("seed_doctors", password="12345678")
    assert Doctor.objects.count() == 0

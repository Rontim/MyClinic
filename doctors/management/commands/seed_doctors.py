from datetime import time

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from accounts.models import Role, User
from doctors.models import Doctor, WorkingHours

# (email, full name, specialty, works Saturday mornings)
DEMO_DOCTORS = [
    ("amina.otieno@clinic.example", "Dr. Amina Otieno", "General Practice", True),
    ("brian.kimani@clinic.example", "Dr. Brian Kimani", "Paediatrics", False),
    ("cynthia.mwangi@clinic.example", "Dr. Cynthia Mwangi", "Dermatology", True),
    ("david.njoroge@clinic.example", "Dr. David Njoroge", "Cardiology", False),
    ("esther.wambui@clinic.example", "Dr. Esther Wambui", "Gynaecology", True),
]


class Command(BaseCommand):
    help = (
        "Create the 5 demo doctors (login + profile + working hours: Mon-Fri 08-12 and 14-17, "
        "some also Saturday 09-12). Safe to run repeatedly; existing doctors are left untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Password for the new doctor accounts. If omitted, a random one is generated and printed once.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        generated = not password
        if generated:
            password = get_random_string(16)
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))

        created = 0
        for email, name, specialty, works_saturday in DEMO_DOCTORS:
            if Doctor.objects.filter(user__email=email).exists():
                continue
            user = User.objects.create_user(email=email, password=password, role=Role.DOCTOR)
            doctor = Doctor.objects.create(user=user, full_name=name, specialty=specialty)
            created += 1
            for weekday in range(5):
                WorkingHours.objects.create(doctor=doctor, weekday=weekday, start_time=time(8), end_time=time(12))
                WorkingHours.objects.create(doctor=doctor, weekday=weekday, start_time=time(14), end_time=time(17))
            if works_saturday:
                WorkingHours.objects.create(doctor=doctor, weekday=5, start_time=time(9), end_time=time(12))

        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new doctor(s); {len(DEMO_DOCTORS) - created} already existed."))
        if created and generated:
            self.stdout.write(f"Generated password for the new doctor accounts (shown once): {password}")

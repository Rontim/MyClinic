from django.db import models
from django.db.models import F, Q

from accounts.models import Patient
from doctors.models import Doctor


class Appointment(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"

    class CancelledBy(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"
        STAFF = "staff", "Staff"

    # PROTECT: never lose appointment history because a doctor/patient was deleted.
    doctor = models.ForeignKey(
        Doctor, on_delete=models.PROTECT, related_name="appointments")
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="appointments")

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.BOOKED)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.CharField(
        max_length=10, choices=CancelledBy.choices, null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time"]
        constraints = [
            # The double-booking guard. Only *booked* rows count, so cancelling an
            # appointment frees its slot automatically and cancelled history is kept.
            models.UniqueConstraint(
                fields=["doctor", "start_time"],
                condition=Q(status="booked"),
                name="uniq_booked_slot_per_doctor",
            ),
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="appointment_end_after_start",
            ),
            # Booked rows carry no cancellation data; cancelled rows must carry all of it.
            models.CheckConstraint(
                condition=(
                    Q(status="booked", cancelled_at__isnull=True,
                      cancelled_by__isnull=True, cancellation_reason="")
                    | Q(status="cancelled", cancelled_at__isnull=False, cancelled_by__isnull=False)
                    & ~Q(cancellation_reason="")
                ),
                name="appointment_cancellation_fields_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=["patient", "start_time"],
                         name="appt_patient_start_idx"),
        ]

    def __str__(self):
        return f"{self.patient} with {self.doctor} at {self.start_time:%Y-%m-%d %H:%M} UTC ({self.status})"

    @property
    def is_cancelled(self) -> bool:
        return self.status == self.Status.CANCELLED

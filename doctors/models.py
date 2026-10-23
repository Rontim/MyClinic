from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import Role


def validate_on_slot_grid(value):
    """Validate that a time falls on a slot grid defined by (:00/:30, :15/:45, etc.)"""
    minutes = value.hour * 60 + value.minute
    if value.second or value.microsecond or minutes % settings.SLOT_MINUTES:
        raise ValidationError(
            f"Time must fall on a {settings.SLOT_MINUTES}-minute boundary (e.g. 09:00, 09:30).")


class Doctor(models.Model):
    """
    Represents a doctor in the system.
    Each doctor is linked to a user account with the 'doctor' role.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="doctor",
        limit_choices_to={"role": Role.DOCTOR},
    )
    full_name = models.CharField(max_length=150)
    specialty = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(
        default=True, help_text="Inactive doctors cannot be booked.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def clean(self):
        if self.user_id and self.user.role != Role.DOCTOR:
            raise ValidationError(
                {"user": "The linked user must have the 'doctor' role."})


class WorkingHours(models.Model):
    """
    Represents the working hours of a doctor for a specific day of the week.
    Each doctor can have one set of working hours per day of the week.
    """

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    doctor = models.ForeignKey(
        Doctor, on_delete=models.CASCADE, related_name="working_hours")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    start_time = models.TimeField(validators=[validate_on_slot_grid])
    end_time = models.TimeField(validators=[validate_on_slot_grid])

    class Meta:
        ordering = ["doctor", "weekday", "start_time"]
        verbose_name_plural = "working hours"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="working_hours_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(weekday__gte=0, weekday__lte=6),
                name="working_hours_weekday_valid",
            ),
        ]

    def __str__(self):
        return f"{self.doctor} {self.get_weekday_display()} {self.start_time:%H:%M}-{self.end_time:%H:%M}"

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError(
                {"end_time": "End time must be after start time."})
        if self.doctor_id and self.start_time and self.end_time:
            overlapping = (
                WorkingHours.objects.filter(
                    doctor_id=self.doctor_id,
                    weekday=self.weekday,
                    start_time__lt=self.end_time,
                    end_time__gt=self.start_time,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if overlapping:
                raise ValidationError(
                    "These hours overlap another interval for the same doctor and weekday.")

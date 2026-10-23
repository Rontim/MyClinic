from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from doctors import slots
from doctors.models import Doctor

from .exceptions import (
    AlreadyCancelled,
    AppointmentCancelled,
    AppointmentNotFound,
    AppointmentStarted,
    DoctorInactive,
    OffGrid,
    OutsideWorkingHours,
    ReasonRequired,
    SameSlot,
    SlotInPast,
    SlotTaken,
    TooSoon,
)

from .models import Appointment

SLOT_CONSTRAINT = "uniq_booked_slot_per_doctor"


def _clinic_tz():
    return timezone.get_default_timezone()


def _working_intervals(doctor: Doctor, weekday: int) -> list[tuple[time, time]]:
    return list(doctor.working_hours.filter(weekday=weekday).values_list("start_time", "end_time"))


def _is_slot_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None) == SLOT_CONSTRAINT or SLOT_CONSTRAINT in str(exc)


# Availabilty
def get_availability(doctor: Doctor, day: date, *, now: datetime | None = None) -> list[datetime]:
    now = now or timezone.now()
    tz = _clinic_tz()
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    booked = Appointment.objects.filter(
        doctor=doctor,
        status=Appointment.Status.BOOKED,
        start_time__gte=day_start,
        start_time__lt=day_end,
    ).values_list("start_time", flat=True)
    return slots.available_slots(
        day,
        _working_intervals(doctor, day.weekday()),
        booked,
        tz,
        settings.SLOT_MINUTES,
        earliest=now + timedelta(minutes=settings.BOOKING_MIN_LEAD_MINUTES),
    )

# Validation


def validate_slot(doctor: Doctor, start: datetime, *, now: datetime | None = None) -> datetime:
    """
    Validate that a slot is valid for booking.
    """
    now = now or timezone.now()
    minutes = settings.SLOT_MINUTES
    lead = settings.BOOKING_MIN_LEAD_MINUTES

    if not doctor.is_active:
        raise DoctorInactive()
    if timezone.is_naive(start):
        start = timezone.make_aware(start, _clinic_tz())

    local = start.astimezone(_clinic_tz())
    if not slots.is_on_grid(local, minutes):
        raise OffGrid(
            f"Appointments start on a {minutes}-minute boundary (e.g. 09:00 or 09:30).")
    if not slots.fits_within_hours(local, _working_intervals(doctor, local.weekday()), minutes):
        raise OutsideWorkingHours(
            f"{doctor.full_name} does not work at {local:%A %H:%M}.")
    if start <= now:
        raise SlotInPast("Cannot book a time in the past.")
    if start < now + timedelta(minutes=lead):
        raise TooSoon(
            f"Appointments must be booked at least {lead} minutes in advance.")

    return start.astimezone(dt_timezone.utc)

# Booking


def book_appointment(*, doctor: Doctor, patient, start: datetime, now: datetime | None = None) -> Appointment:
    start_utc = validate_slot(doctor, start, now=now)
    try:
        with transaction.atomic():
            return Appointment.objects.create(
                doctor=doctor,
                patient=patient,
                start_time=start_utc,
                end_time=start_utc + timedelta(minutes=settings.SLOT_MINUTES),
            )
    except IntegrityError as exc:
        if _is_slot_conflict(exc):
            raise SlotTaken() from exc
        raise


def _lock_appointment(appointment_id: int) -> Appointment:
    try:
        return Appointment.objects.select_for_update(of=("self",)).select_related("doctor").get(pk=appointment_id)
    except Appointment.DoesNotExist:
        raise AppointmentNotFound() from None


def cancel_appointment(
    *, appointment_id: int, reason: str, cancelled_by: str, now: datetime | None = None
) -> Appointment:
    """Cancel a booked appointment, freeing its slot. `cancelled_by` is one of
    Appointment.CancelledBy (patient / doctor / staff)."""
    now = now or timezone.now()
    reason = (reason or "").strip()
    if not reason:
        raise ReasonRequired()
    cancelled_by = Appointment.CancelledBy(
        cancelled_by).value  # reject anything unexpected

    with transaction.atomic():
        appointment = _lock_appointment(appointment_id)
        if appointment.is_cancelled:
            raise AlreadyCancelled()
        if appointment.start_time <= now:
            raise AppointmentStarted(
                "This appointment has already started and can no longer be cancelled.")
        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = reason
        appointment.cancelled_by = cancelled_by
        appointment.cancelled_at = now
        appointment.save(
            update_fields=["status", "cancellation_reason",
                           "cancelled_by", "cancelled_at", "updated_at"]
        )
    return appointment


def reschedule_appointment(*, appointment_id: int, new_start: datetime, now: datetime | None = None) -> Appointment:
    """
    Move a booked appointment to a new slot with the same doctor. Same appointment id;
    the old slot is freed by the same UPDATE that claims the new one.
    """
    now = now or timezone.now()

    with transaction.atomic():
        appointment = _lock_appointment(appointment_id)
        if appointment.is_cancelled:
            raise AppointmentCancelled()
        if appointment.start_time <= now:
            raise AppointmentStarted(
                "This appointment has already started and can no longer be rescheduled.")

        new_start_utc = validate_slot(appointment.doctor, new_start, now=now)
        if new_start_utc == appointment.start_time:
            raise SameSlot()

        appointment.start_time = new_start_utc
        appointment.end_time = new_start_utc + \
            timedelta(minutes=settings.SLOT_MINUTES)
        try:
            with transaction.atomic():
                appointment.save(
                    update_fields=["start_time", "end_time", "updated_at"])
        except IntegrityError as exc:
            if _is_slot_conflict(exc):
                raise SlotTaken() from exc
            raise
    return appointment

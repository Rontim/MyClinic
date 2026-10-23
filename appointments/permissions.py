"""Who can do what with appointments.

              book   view / cancel          reschedule   list own
  patient     yes    own appointments       yes (own)    /patients/{own id}/appointments/
  doctor      no     appointments assigned  no           /doctors/me/appointments/
                     to them (cancel too)
  staff       yes    all (book for patient) yes          any patient

Appointments you aren't allowed to see are *invisible* (404), not forbidden, so ids
don't leak. Actions a role never has (a doctor booking or rescheduling) are 403.
"""
from rest_framework.permissions import BasePermission

from accounts.models import Role

from .models import Appointment


def is_clinic_staff(user) -> bool:
    return bool(user and user.is_authenticated and (user.role == Role.STAFF or user.is_superuser))


def visible_appointments(user):
    """The only queryset views should read appointments from."""
    queryset = Appointment.objects.select_related("doctor", "patient")
    if is_clinic_staff(user):
        return queryset
    if user.role == Role.DOCTOR:
        return queryset.filter(doctor__user=user)
    if user.role == Role.PATIENT:
        return queryset.filter(patient__user=user)
    return queryset.none()


def cancelled_by_for(user) -> str:
    """Who to record as the canceller."""
    if is_clinic_staff(user):
        return Appointment.CancelledBy.STAFF
    if user.role == Role.DOCTOR:
        return Appointment.CancelledBy.DOCTOR
    return Appointment.CancelledBy.PATIENT


class IsPatientOrStaff(BasePermission):
    """Booking and rescheduling: patients (their own) and staff. Never doctors."""

    message = "Your account is not allowed to do this."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.role == Role.PATIENT or is_clinic_staff(user)))


class IsDoctor(BasePermission):
    message = "Only doctors can view their own schedule."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == Role.DOCTOR)

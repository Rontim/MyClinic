from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Patient, Role
from doctors.models import Doctor

from . import services
from .exceptions import AppointmentNotFound, DoctorNotFound, PatientNotFound
from .models import Appointment
from .permissions import (
    IsDoctor,
    IsPatientOrStaff,
    cancelled_by_for,
    is_clinic_staff,
    visible_appointments,
)
from .serializers import (
    AppointmentCreateSerializer,
    AppointmentSerializer,
    CancelSerializer,
    DoctorScheduleQuerySerializer,
    RescheduleSerializer,
)


def _resolve_patient(user, requested_id: int | None) -> Patient:
    """Patients book for themselves (identity comes from the token, never the body).
    Staff must say which patient they are booking for."""
    if is_clinic_staff(user):
        if requested_id is None:
            raise ValidationError(
                {"patient": ["Required when booking on behalf of a patient."]})
        patient = Patient.objects.filter(pk=requested_id).first()
        if patient is None:
            raise PatientNotFound()
        return patient

    own = getattr(user, "patient", None)
    if own is None:
        raise PermissionDenied("This account has no patient profile.")
    if requested_id is not None and requested_id != own.pk:
        raise PermissionDenied("You can only book appointments for yourself.")
    return own


class AppointmentViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AppointmentSerializer
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return visible_appointments(self.request.user)

    def get_permissions(self):
        if self.action in ("create", "reschedule"):
            return [IsPatientOrStaff()]
        return [IsAuthenticated()]

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            raise AppointmentNotFound() from None

    @extend_schema(request=AppointmentCreateSerializer, responses={201: AppointmentSerializer})
    def create(self, request):
        data = AppointmentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        doctor = Doctor.objects.filter(
            pk=data.validated_data["doctor"]).first()
        if doctor is None:
            raise DoctorNotFound()
        patient = _resolve_patient(
            request.user, data.validated_data.get("patient"))
        appointment = services.book_appointment(
            doctor=doctor, patient=patient, start=data.validated_data["start_time"]
        )
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=CancelSerializer, responses={200: AppointmentSerializer})
    @action(detail=True, methods=["patch"])
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        data = CancelSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        updated = services.cancel_appointment(
            appointment_id=appointment.pk,
            reason=data.validated_data["reason"],
            cancelled_by=cancelled_by_for(request.user),
        )
        return Response(AppointmentSerializer(updated).data)

    @extend_schema(request=RescheduleSerializer, responses={200: AppointmentSerializer})
    @action(detail=True, methods=["patch"])
    def reschedule(self, request, pk=None):
        appointment = self.get_object()
        data = RescheduleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        updated = services.reschedule_appointment(
            appointment_id=appointment.pk, new_start=data.validated_data["start_time"]
        )
        return Response(AppointmentSerializer(updated).data)


class PatientAppointmentsView(APIView):
    """GET /patients/{id}/appointments/: upcoming (future, still booked), soonest first."""

    @extend_schema(responses=AppointmentSerializer(many=True))
    def get(self, request, patient_id: int):
        user = request.user
        if is_clinic_staff(user):
            if not Patient.objects.filter(pk=patient_id).exists():
                raise PatientNotFound()
        else:
            own = getattr(user, "patient",
                          None) if user.role == Role.PATIENT else None
            if own is None or own.pk != patient_id:
                raise PermissionDenied(
                    "You can only view your own appointments.")

        appointments = (
            Appointment.objects.filter(
                patient_id=patient_id,
                status=Appointment.Status.BOOKED,
                start_time__gt=timezone.now(),
            )
            .select_related("doctor", "patient")
            .order_by("start_time")
        )
        return Response(AppointmentSerializer(appointments, many=True).data)


class DoctorScheduleView(APIView):
    """GET /doctors/me/appointments/: the logged-in doctor's own appointments.

    Defaults to today onwards (clinic time), soonest first. `date` narrows to one day
    (past days allowed); `status` filters booked / cancelled.
    """

    permission_classes = [IsDoctor]

    @extend_schema(parameters=[DoctorScheduleQuerySerializer], responses=AppointmentSerializer(many=True))
    def get(self, request):
        query = DoctorScheduleQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        appointments = visible_appointments(request.user)
        if "date" in query.validated_data:
            start, end = services.day_bounds(query.validated_data["date"])
            appointments = appointments.filter(
                start_time__gte=start, start_time__lt=end)
        else:
            appointments = appointments.filter(
                start_time__gte=services.day_bounds(timezone.localdate())[0])
        if "status" in query.validated_data:
            appointments = appointments.filter(
                status=query.validated_data["status"])

        return Response(AppointmentSerializer(appointments.order_by("start_time"), many=True).data)

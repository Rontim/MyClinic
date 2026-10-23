from datetime import timedelta

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from appointments import services
from appointments.exceptions import DoctorNotFound

from .models import Doctor
from .serializers import AvailabilityQuerySerializer, AvailabilitySerializer, DoctorSerializer


class DoctorViewSet(viewsets.GenericViewSet):
    """Doctors patients can book. Inactive doctors are not listed and have no availability."""

    queryset = Doctor.objects.filter(is_active=True)
    serializer_class = DoctorSerializer
    lookup_value_regex = r"\d+"

    def list(self, request):
        return Response(DoctorSerializer(self.get_queryset(), many=True).data)

    @extend_schema(parameters=[AvailabilityQuerySerializer], responses=AvailabilitySerializer)
    @action(detail=True, methods=["get"])
    def availability(self, request, pk=None):
        query = AvailabilityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        day = query.validated_data["date"]

        doctor = self.get_queryset().filter(pk=pk).first()
        if doctor is None:
            raise DoctorNotFound()

        step = timedelta(minutes=settings.SLOT_MINUTES)
        free = services.get_availability(doctor, day)
        payload = {
            "doctor_id": doctor.pk,
            "date": day,
            "slot_minutes": settings.SLOT_MINUTES,
            "slots": [{"start": slot, "end": slot + step} for slot in free],
        }
        return Response(AvailabilitySerializer(payload).data)

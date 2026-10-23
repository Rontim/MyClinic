from rest_framework import serializers

from accounts.serializers import PatientSummarySerializer
from doctors.serializers import DoctorSerializer

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    """Read representation. Datetimes are rendered in the clinic timezone (+03:00)."""

    doctor = DoctorSerializer(read_only=True)
    patient = PatientSummarySerializer(read_only=True)

    class Meta:
        model = Appointment
        fields = (
            "id", "doctor", "patient", "start_time", "end_time", "status",
            "cancellation_reason", "cancelled_by", "cancelled_at", "created_at", "updated_at",
        )
        read_only_fields = fields


class AppointmentCreateSerializer(serializers.Serializer):
    doctor = serializers.IntegerField(help_text="Doctor id.")
    start_time = serializers.DateTimeField(help_text="ISO 8601. No offset means clinic-local time.")
    patient = serializers.IntegerField(
        required=False, help_text="Staff only: the patient being booked. Patients are taken from their token."
    )


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class RescheduleSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField(help_text="ISO 8601. No offset means clinic-local time.")


class DoctorScheduleQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False, help_text="Only this clinic-local day (past days allowed).")
    status = serializers.ChoiceField(choices=Appointment.Status.choices, required=False)

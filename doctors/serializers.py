from rest_framework import serializers

from .models import Doctor


class DoctorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = ("id", "full_name", "specialty")
        read_only_fields = fields


class AvailabilityQuerySerializer(serializers.Serializer):
    date = serializers.DateField(help_text="Clinic-local date, YYYY-MM-DD.")


class SlotSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()


class AvailabilitySerializer(serializers.Serializer):
    doctor_id = serializers.IntegerField()
    date = serializers.DateField()
    slot_minutes = serializers.IntegerField()
    slots = SlotSerializer(many=True)

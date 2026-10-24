from django.db import transaction
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import Patient, User

PROFILE_FIELDS = ("full_name", "phone")


class RegistrationSerializer(DjoserUserCreateSerializer):
    """Custom serializer for user registration with profile fields."""

    full_name = serializers.CharField(write_only=True)
    phone = serializers.CharField(
        write_only=True, required=False, allow_blank=True)

    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = DjoserUserCreateSerializer.Meta.fields + PROFILE_FIELDS

    def validate(self, attrs):
        """Djoser validates the user fields, but profile fields are not User Column fields, so lest hide them."""
        profile_data = {field: attrs.pop(field) for field in PROFILE_FIELDS}
        attrs = super().validate(attrs)
        attrs.update(profile_data)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        profile_data = {field: validated_data.pop(
            field) for field in PROFILE_FIELDS}
        user = super().create(validated_data)
        Patient.objects.create(user=user, **profile_data)
        return user


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model, including profile fields."""

    patient_id = serializers.SerializerMethodField()
    doctor_id = serializers.SerializerMethodField()
    full_name = serializers.CharField(
        max_length=150, required=False, write_only=True)
    phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "role", "patient_id",
                  "doctor_id", "full_name", "phone")
        read_only_fields = ("id", "email", "role")

    def get_patient_id(self, obj) -> int | None:
        patient = getattr(obj, "patient", None)
        return patient.id if patient else None

    def get_doctor_id(self, obj) -> int | None:
        doctor = getattr(obj, "doctor", None)
        return doctor.id if doctor else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        patient = getattr(instance, "patient", None)
        doctor = getattr(instance, "doctor", None)
        profile = patient or doctor
        data["full_name"] = profile.full_name if profile else None
        data["phone"] = patient.phone if patient else None
        return data

    def update(self, instance, validated_data):
        if not validated_data:
            return instance
        patient = getattr(instance, "patient", None)
        if patient is None:
            raise PermissionDenied(
                "Only patient accounts can edit their profile here. Ask clinic staff to change other accounts.")
        for field, value in validated_data.items():
            setattr(patient, field, value)
        patient.save(update_fields=list(validated_data))
        return instance


class PatientSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ("id", "full_name", "phone")
        read_only_fields = fields

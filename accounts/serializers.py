from django.db import transaction
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers

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

    full_name = serializers.CharField(
        source="patient.full_name", read_only=True)
    phone = serializers.CharField(source="patient.phone", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "role", "full_name", "phone")


class PatientSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ("id", "full_name", "phone")
        read_only_fields = fields

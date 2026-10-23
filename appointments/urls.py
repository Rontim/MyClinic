from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AppointmentViewSet, DoctorScheduleView, PatientAppointmentsView

router = DefaultRouter()
router.register("appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [
    path("doctors/me/appointments/", DoctorScheduleView.as_view(), name="doctor-schedule"),
    path("patients/<int:patient_id>/appointments/", PatientAppointmentsView.as_view(), name="patient-appointments"),
    *router.urls,
]

from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    """
    Read-only on purpose: booking, cancelling and rescheduling go through the API
    services, which enforce working hours, lead time and the slot grid. Editing rows
    here would bypass those rules.
    """

    list_display = ("start_time", "doctor", "patient",
                    "status", "cancelled_by")
    list_filter = ("status", "doctor")
    search_fields = ("patient__full_name",
                     "patient__user__email", "doctor__full_name")
    date_hierarchy = "start_time"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

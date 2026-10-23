from django.contrib.auth.models import Group, Permission
from django.db.models import Q

STAFF_GROUP = "Clinic staff"

STAFF_PERMISSIONS = [
    ("doctors", "doctor", ("add", "change", "view")),
    ("doctors", "workinghours", ("add", "change", "delete", "view")),
    ("accounts", "patient", ("view",)),
    ("appointments", "appointment", ("view",)),
]


def ensure_staff_group() -> Group:
    """Create the staff group and assign the required permissions."""
    group, _ = Group.objects.get_or_create(name=STAFF_GROUP)
    query = Q()
    for app_label, model, actions in STAFF_PERMISSIONS:
        query |= Q(content_type__app_label=app_label,
                   codename__in=[f"{a}_{model}" for a in actions])
    group.permissions.add(*Permission.objects.filter(query))
    return group

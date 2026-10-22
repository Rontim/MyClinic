from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Role, User


@receiver(pre_save, sender=User, dispatch_uid="accounts.sync_is_staff_with_role")
def sync_is_staff_with_role(sender, instance: User, **kwargs):
    """Keep `is_staff` in step with `role` on every save.

    - role == staff        -> is_staff = True
    - any other role       -> is_staff = False (so demoting a user removes admin access)
    - superusers           -> left alone, so `createsuperuser` accounts keep admin access

    """
    if instance.is_superuser:
        instance.is_staff = True
    else:
        instance.is_staff = instance.role == Role.STAFF

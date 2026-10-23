from django.db.models.signals import post_save, pre_save
from django.contrib.auth.models import Group
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Role, User
from .permissions import STAFF_GROUP, ensure_staff_group


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


@receiver(post_save, sender=User, dispatch_uid="accounts.sync_staff_group")
def sync_staff_group(sender, instance: User, raw=False, **kwargs):
    """
    Keep the staff group membership in step with `is_staff` on every save.
    - is_staff = True      -> add to staff group
    - is_staff = False     -> remove from staff group
    - superusers           -> left alone, so `createsuperuser` accounts keep admin access
    """
    if raw:
        return
    if instance.is_staff and not instance.is_superuser:
        instance.groups.add(ensure_staff_group())
    else:
        group = Group.objects.filter(name=STAFF_GROUP).first()
        if group:
            instance.groups.remove(group)


def create_staff_group_after_migrate(sender, **kwargs):
    ensure_staff_group()

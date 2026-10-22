from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from . import signals  # noqa: F401

        # Connect the post_migrate signal to create the staff group after migrations
        post_migrate.connect(
            signals.create_staff_group_after_migrate,
            dispatch_uid="accounts.create_staff_group",
        )

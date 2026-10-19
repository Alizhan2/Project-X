from django.apps import AppConfig


class DisruptionsConfig(AppConfig):
    name = "apps.disruptions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import recovery  # noqa: F401  (registers the recover_booking job handler)

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import schema  # noqa: F401  (registers the OpenAPI auth extension)

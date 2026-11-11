"""Initialize a dedicated, empty hosted demonstration database without any reset operation."""
import os

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.accounts.models import User
from apps.core.models import AuditRecord
from apps.transport import demo_data

BOOTSTRAP_LOCK = 7_330_002
MARKER_ACTION = "demo.bootstrap_completed"
MARKER_ID = "render-free-demo-v1"


class Command(BaseCommand):
    help = "Initialize one explicitly enabled EMPTY hosted demo database once. Never resets existing data."

    def handle(self, *args, **options):
        enabled = os.environ.get("DOEDU_BOOTSTRAP_DEMO", "").lower() in ("1", "true", "yes", "on")
        if not enabled or not settings.IS_DEPLOYED or settings.LAUNCH_MODE != "demo" or not settings.SIMULATION_ENABLED:
            raise CommandError("Hosted demo bootstrap requires an explicitly enabled deployed demo launch.")
        password = os.environ.get("DEMO_USER_PASSWORD", "")
        admin_password = os.environ.get("DEMO_ADMIN_PASSWORD", "")
        if len(password) < 16 or len(admin_password) < 16 or password == admin_password:
            raise CommandError("Provide distinct generated DEMO_USER_PASSWORD and DEMO_ADMIN_PASSWORD values of at least 16 characters.")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [BOOTSTRAP_LOCK])
            if AuditRecord.objects.filter(action=MARKER_ACTION, object_type="deployment", object_id=MARKER_ID).exists():
                self.stdout.write("Hosted demo was already initialized; existing accounts and journeys are unchanged.")
                return
            # Migration-created Django auth/content-type rows are allowed; application data must be absent.
            for model in apps.get_models():
                if model._meta.app_config.name.startswith("apps.") and model.objects.exists():
                    raise CommandError("Refusing hosted demo bootstrap: this unmarked database is not empty.")
            reference = demo_data.reference_date()
            operators = demo_data.ensure_network()
            demo_data.extend_schedule(reference, 14)
            demo_data._ensure_demo_users(operators)
            administrator = User.objects.get(username="admin@doedu.test")
            administrator.set_password(admin_password)
            administrator.save(update_fields=["password"])
            demo_data._apply_scenarios(reference)
            demo_data._seed_demo_bookings(reference)
            AuditRecord.objects.create(action=MARKER_ACTION, object_type="deployment", object_id=MARKER_ID,
                                       detail={"synthetic": True, "reference_date": reference.isoformat()})
        self.stdout.write("Dedicated hosted demo initialized. Credentials are available only in the hosting environment.")

import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.transport import demo_data


class Command(BaseCommand):
    help = "Load (or reset) the deterministic synthetic demo dataset. Development only."

    def add_arguments(self, parser):
        parser.add_argument("--reference-date", help="YYYY-MM-DD; default today in the demo timezone. Env: DEMO_REFERENCE_DATE")

    def handle(self, *args, **opts):
        if not settings.ALLOW_DEMO_TOOLS:
            raise CommandError("Refusing to reset data: demo tools are disabled in this environment "
                               f"(DOEDU_ENV={settings.ENVIRONMENT}). They are only available in development/test, "
                               "or staging with DOEDU_ALLOW_DEMO_TOOLS=true, and never in production.")
        ref = demo_data.reference_date(opts["reference_date"] or os.environ.get("DEMO_REFERENCE_DATE"))
        demo_data.reset_transport_data(ref, with_bookings=True)
        self.stdout.write("Demo accounts (synthetic, password from DEMO_USER_PASSWORD, default in docs/demo-data.md): "
                          + ", ".join(e for e, *_ in demo_data.DEMO_USERS))
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded (SYNTHETIC), reference date {ref}, demo day {ref + timedelta(days=demo_data.DEMO_DAY)}."))

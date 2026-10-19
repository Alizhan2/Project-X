from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.transport import demo_data


class Command(BaseCommand):
    help = ("ADDITIVE: make sure the synthetic reference network exists and the timetable covers the next N days. "
            "Never deletes or modifies existing data, creates no user accounts, so it is safe to schedule daily in a hosted "
            "demonstration (DOEDU_LAUNCH_MODE=demo). Refused when simulation is not allowed (commercial launch mode).")

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14)

    def handle(self, *args, **opts):
        if not settings.SIMULATION_ENABLED:
            raise CommandError("Synthetic data may only be loaded when the launch mode allows simulation.")
        if not 1 <= opts["days"] <= 60:
            raise CommandError("--days must be between 1 and 60.")
        with transaction.atomic():
            demo_data.ensure_network()
            today = demo_data.reference_date()
            created = demo_data.extend_schedule(today, opts["days"])
        self.stdout.write(self.style.SUCCESS(f"synthetic network ensured; {created} new departures for the next {opts['days']} days (from {today})"))

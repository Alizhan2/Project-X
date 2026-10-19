import json

from django.core.management.base import BaseCommand

from apps.core import ops


class Command(BaseCommand):
    help = "Print queue, booking, recovery and worker health as JSON (no personal data). Exit 1 if something needs attention."

    def handle(self, *args, **opts):
        s = ops.snapshot()
        self.stdout.write(json.dumps(s, indent=2, sort_keys=True))
        problems = s["jobs"]["failed"] or s["jobs_stale_running"] or s["pending_bookings_overdue"] or s["capacity_inconsistencies"]
        raise SystemExit(1 if problems else 0)

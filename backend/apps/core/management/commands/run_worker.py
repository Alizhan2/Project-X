import logging
import os
import signal
import socket
import time
from datetime import timedelta

from django.conf import settings
from django.db import InterfaceError, OperationalError, connection
from django.utils import timezone

from django.core.management.base import BaseCommand

from apps.core import jobs
import apps.bookings.services  # noqa: F401  (registers job handlers)
import apps.disruptions.recovery


log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Background worker: runs durable jobs (reservation expiry etc.). Safe to stop/restart at any time."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process due jobs once and exit.")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **opts):
        from apps.core.models import WorkerHeartbeat

        name = f"{socket.gethostname()}-{os.getpid()}"
        started = timezone.now()
        total = 0
        last_cleanup = 0.0
        last_sync = -10**9
        stopping = []
        for sig in (signal.SIGTERM, signal.SIGINT):   # graceful shutdown: finish the current batch, then exit
            signal.signal(sig, lambda *_: stopping.append(1))
        backoff = 1
        while not stopping:
            try:
                n = jobs.run_pending() + self.sweep()
                total += n
                WorkerHeartbeat.objects.update_or_create(name=name, defaults={"started_at": started, "last_seen": timezone.now(), "jobs_processed": total})
                if settings.DEMO_SCHEDULE_DAYS and settings.SIMULATION_ENABLED and time.monotonic() - last_sync > 6 * 3600:
                    from django.core.management import call_command
                    call_command("sync_demo_schedule", days=settings.DEMO_SCHEDULE_DAYS, verbosity=0)   # additive; keeps a hosted demo usable
                    last_sync = time.monotonic()
                if time.monotonic() - last_cleanup > 3600:   # expired sessions are not removed automatically
                    from django.core.management import call_command
                    call_command("clearsessions")
                    WorkerHeartbeat.objects.filter(last_seen__lt=timezone.now() - timedelta(days=1)).delete()
                    last_cleanup = time.monotonic()
                backoff = 1
            except (OperationalError, InterfaceError) as exc:
                # Database outage: do not crash. Jobs are durable in PostgreSQL, so nothing is lost; retry with capped backoff.
                log.error("worker: database unavailable (%s); retrying in %ss", type(exc).__name__, backoff)
                connection.close()
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                if opts["once"]:
                    raise
                continue
            if opts["once"]:
                self.stdout.write(f"processed {n} job(s)")
                return
            if n == 0:
                time.sleep(opts["interval"])

    def sweep(self):
        """Safety net independent of the job table: expire any overdue pending booking."""
        return apps.bookings.services.expire_due_bookings() + apps.disruptions.recovery.expire_due_offers()

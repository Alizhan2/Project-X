"""Operational queries shared by readiness, metrics and management commands. No personal data is returned."""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Sum
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from .models import Job, WorkerHeartbeat


def database_ok() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        return False


def migrations_pending() -> bool:
    """Cached for 30 s: planning the migration graph on every probe would be wasteful."""
    hit = cache.get("ops:migrations_pending")
    if hit is not None:
        return hit
    executor = MigrationExecutor(connection)
    pending = bool(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    cache.set("ops:migrations_pending", pending, 30)
    return pending


def worker_state():
    """('ok' | 'stale' | 'unknown', age_seconds or None) from the newest worker heartbeat."""
    last = WorkerHeartbeat.objects.order_by("-last_seen").values_list("last_seen", flat=True).first()
    if last is None:
        return "unknown", None
    age = (timezone.now() - last).total_seconds()
    return ("ok" if age <= settings.WORKER_STALE_SECONDS else "stale"), round(age)


def snapshot() -> dict:
    """Queue, booking and recovery health in one dict (also the source of the Prometheus metrics)."""
    from apps.bookings.models import Booking
    from apps.disruptions.models import ReplacementOffer

    now = timezone.now()
    jobs = dict(Job.objects.values_list("status").annotate(n=Count("id")))
    oldest = Job.objects.filter(status=Job.Status.PENDING, run_at__lte=now).order_by("run_at").values_list("run_at", flat=True).first()
    stale_running = Job.objects.filter(status=Job.Status.RUNNING, locked_at__lt=now - timedelta(seconds=settings.JOB_LOCK_TIMEOUT_SECONDS)).count()
    state, age = worker_state()
    return {
        "jobs": {s: jobs.get(s, 0) for s in ("pending", "running", "done", "failed")},
        "jobs_oldest_due_age_seconds": round((now - oldest).total_seconds()) if oldest else 0,
        "jobs_stale_running": stale_running,
        "worker": {"state": state, "heartbeat_age_seconds": age},
        "bookings": dict(Booking.objects.values_list("status").annotate(n=Count("id"))),
        "pending_bookings_overdue": Booking.objects.filter(status="pending_payment", expires_at__lte=now - timedelta(minutes=1)).count(),
        "replacement_offers": dict(ReplacementOffer.objects.values_list("status").annotate(n=Count("id"))),
        "capacity_inconsistencies": len(capacity_inconsistencies()),
        "release": settings.RELEASE,
    }


def capacity_inconsistencies():
    """Departures whose counter disagrees with the reservation table (the counter is the lock target, the
    reservations are the audit trail of why). Expected result in a healthy system: empty."""
    from apps.transport.models import Departure

    from apps.bookings.models import Reservation
    live = {r["departure_id"]: r["n"] for r in Reservation.objects.filter(status__in=["held", "consumed"])
            .values("departure_id").annotate(n=Sum("places"))}
    bad = []
    for d in Departure.objects.filter(places_taken__gt=0).values("id", "places_taken", "baseline_places") | \
            Departure.objects.filter(id__in=live.keys()).values("id", "places_taken", "baseline_places"):
        expected = d["baseline_places"] + live.get(d["id"], 0)
        if d["places_taken"] != expected:
            bad.append({"departure": d["id"], "places_taken": d["places_taken"], "expected": expected})
    return bad

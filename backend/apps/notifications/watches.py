"""Watches: "tell me if this search gets cheaper" and "tell me when a journey becomes available".

Design notes
* No promise and no reservation: a watch only creates an in-app notification; availability is checked again at booking.
* Evaluation reuses planning.services.search, so what a notification says is exactly what the search screen then shows.
* Safe to run concurrently and repeatedly: each watch is processed under `SELECT ... FOR UPDATE SKIP LOCKED`, and
  notifications are de-duplicated per (user, key) in the database.
* Triggered by (a) the worker every few minutes, (b) a short-delay job after anything that can change results
  (fare, capacity or service edits, cancelled/expired bookings freeing places), (c) lazily when the owner lists their watches.
"""

import time as time_module
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db import transaction
from django.utils import timezone

from apps.core import jobs
from apps.planning import services as planner

from .models import Watch
from .services import notify

MAX_ACTIVE_PER_USER = 10
MAX_DAYS_AHEAD = 60
PERIODIC_SECONDS = 300
BURST_SECONDS = 10          # events within this window share one evaluation job


def search_snapshot(origin, destination, date, time, passengers, modes, now=None):
    """(journey count, cheapest total or None, currency or "") for the search the watch describes."""
    now = now or timezone.now()
    start = timezone.make_aware(datetime.combine(date, time))
    results = planner.search(origin, destination, start, passengers, "price", now=now, modes=frozenset(modes.split(",")))
    if not results:
        return 0, None, ""
    return len(results), min(r.total_price for r in results), results[0].currency


def search_link(w):
    """Frontend path that reproduces the watch's search (same parameter names as the search screen)."""
    params = {"origin": w.origin.code, "destination": w.destination.code, "date": w.date.isoformat(),
              "time": w.time.strftime("%H:%M"), "passengers": w.passengers, "modes": w.modes}
    return "/?" + urlencode(params)


def _money(value, currency):
    return f"{currency} {value:.2f}"


def evaluate(watch_id, now=None, wait=False) -> bool:
    """Evaluate one active watch. Returns True when a notification was created.

    `wait=False` (worker): skip a watch another process is handling right now. `wait=True` (a person listing their
    alerts): wait for that process, so the response reflects the finished evaluation instead of a stale read."""
    now = now or timezone.now()
    with transaction.atomic():
        w = (Watch.objects.select_for_update(skip_locked=not wait, of=("self",)).select_related("user", "origin", "destination")
             .filter(pk=watch_id, status=Watch.Status.ACTIVE).first())
        if w is None:
            return False
        if w.date < timezone.localdate(now):
            w.status = Watch.Status.EXPIRED
            w.save(update_fields=["status"])
            return False
        count, price, currency = search_snapshot(w.origin, w.destination, w.date, w.time, w.passengers, w.modes, now)
        w.last_checked_at = now
        notified = False
        route = f"{w.origin.name} → {w.destination.name}"
        if w.kind == Watch.Kind.AVAILABILITY:
            if count > 0:
                notify(w.user, "watch_available", f"Journeys are now available: {route}",
                       f"A journey for {w.date:%d %b} from {_money(price, currency)} is now available. Places are not held: check again before booking. "
                       "Simulated demonstration data.", dedupe_key=f"watch:{w.pk}:available", link=search_link(w))
                w.status, w.last_notified_at, notified = Watch.Status.TRIGGERED, now, True
        elif price is not None:
            if w.baseline_price is not None and price < w.baseline_price:
                notify(w.user, "watch_price", f"Price dropped: {route}",
                       f"The cheapest journey for {w.date:%d %b} fell from {_money(w.baseline_price, currency)} to {_money(price, currency)} "
                       f"for {w.passengers} passenger(s). Simulated demonstration data.",
                       dedupe_key=f"watch:{w.pk}:price:{price}", link=search_link(w))
                w.last_notified_at, notified = now, True
            w.baseline_price, w.currency = price, currency       # always follow the latest price: a later fall is a new drop
        w.save()
        return notified


def evaluate_user(user, now=None) -> int:
    return sum(evaluate(pk, now, wait=True) for pk in Watch.objects.filter(user=user, status=Watch.Status.ACTIVE).values_list("pk", flat=True))


def evaluate_all(now=None, limit=1000) -> int:
    ids = list(Watch.objects.filter(status=Watch.Status.ACTIVE).order_by("last_checked_at", "pk").values_list("pk", flat=True)[:limit])
    return sum(evaluate(pk, now) for pk in ids)


def schedule_evaluation():
    """Queue a prompt re-evaluation after something that can change search results. Call from the code that made the
    change; it only runs once the surrounding transaction has committed, and bursts collapse into one job."""
    bucket = int(time_module.time() // BURST_SECONDS)
    transaction.on_commit(lambda: jobs.enqueue("evaluate_watches", {}, dedupe_key=f"evaluate_watches:burst:{bucket}"))


def ensure_periodic(now=None):
    """Called by the worker loop: one evaluation per PERIODIC_SECONDS window, even with several workers."""
    bucket = int((now or timezone.now()).timestamp() // PERIODIC_SECONDS)
    jobs.enqueue("evaluate_watches", {}, dedupe_key=f"evaluate_watches:periodic:{bucket}")


@jobs.handler("evaluate_watches")
def _evaluate_job():
    evaluate_all()

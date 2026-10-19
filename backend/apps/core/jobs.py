"""Tiny durable job queue on PostgreSQL (no broker needed at MVP scale).

enqueue() is called inside the caller's transaction so a job exists iff the business change committed.
run_pending() claims jobs with SELECT … FOR UPDATE SKIP LOCKED so several workers never double-run a job, and
re-claims jobs whose worker died (locked_at older than JOB_LOCK_TIMEOUT_SECONDS) => restart/crash safe.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Job

log = logging.getLogger(__name__)
HANDLERS = {}
MAX_ATTEMPTS = 5


def handler(kind):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(kind, payload, run_at=None, dedupe_key=None):
    """Create a job. With `dedupe_key`, a second enqueue for the same logical work is a no-op."""
    defaults = {"kind": kind, "payload": payload, "run_at": run_at or timezone.now()}
    if dedupe_key is None:
        return Job.objects.create(**defaults)
    job, _ = Job.objects.get_or_create(dedupe_key=dedupe_key, defaults=defaults)
    return job


def _claim(now):
    stale = now - timedelta(seconds=settings.JOB_LOCK_TIMEOUT_SECONDS)
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(run_at__lte=now)
            .filter(status=Job.Status.PENDING)
            .order_by("run_at", "id").first()
        ) or (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=Job.Status.RUNNING, locked_at__lt=stale)
            .order_by("run_at", "id").first()
        )
        if job is None:
            return None
        job.status, job.locked_at = Job.Status.RUNNING, now
        job.attempts += 1
        job.save(update_fields=["status", "locked_at", "attempts"])
        return job


def run_pending(limit=100):
    """Process due jobs; returns the number executed. Safe to call repeatedly and concurrently."""
    done = 0
    while done < limit:
        job = _claim(timezone.now())
        if job is None:
            break
        try:
            HANDLERS[job.kind](**job.payload)
        except Exception as exc:  # noqa: BLE001 - recorded, retried with backoff
            log.exception("job %s failed", job.pk)
            job.last_error = repr(exc)[:2000]
            if job.attempts >= MAX_ATTEMPTS:
                job.status = Job.Status.FAILED
            else:
                job.status = Job.Status.PENDING
                job.run_at = timezone.now() + timedelta(seconds=2 ** job.attempts)
        else:
            job.status = Job.Status.DONE
        job.locked_at = None
        job.save(update_fields=["status", "last_error", "run_at", "locked_at"])
        done += 1
    return done

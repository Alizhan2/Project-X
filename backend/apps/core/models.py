from django.db import models


class Job(models.Model):
    """Durable background work item, stored in PostgreSQL and claimed by `manage.py run_worker`.

    Handlers MUST be idempotent: a job can run more than once (retry after a crash/restart).
    A job claimed (`running`) but not finished within JOB_LOCK_TIMEOUT is considered abandoned and re-claimed.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    run_at = models.DateTimeField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Prevents duplicate jobs for the same logical work (e.g. one expiry per booking).
    dedupe_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "run_at"])]


class AuditRecord(models.Model):
    """Append-only record of significant actions (who did what to which object)."""

    actor = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["object_type", "object_id"])]
        ordering = ["-created_at", "-id"]


class WorkerHeartbeat(models.Model):
    """One row per worker process name; updated each loop so readiness/metrics can show worker liveness."""

    name = models.CharField(max_length=64, unique=True)
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField()
    jobs_processed = models.PositiveIntegerField(default=0)

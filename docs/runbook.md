# Operations runbook
Conventions: commands run in the app image (`docker compose --env-file .env.production -f docker-compose.prod.yml exec web …` or the platform's exec). Every
API response carries `X-Request-ID`; every log line has the same `request_id`: ask the reporter for it. Never paste credentials into tickets/chats.
First look at any incident: `manage.py ops_status` (JSON, exit 1 when something needs attention), `/api/health/ready/`, the last 100 log lines of web and worker.

## Application unavailable
1. `GET /api/health/live/`: if it fails the process/ingress is down → restart `web`, check ingress/DNS/TLS certificate expiry.
2. Live OK but `/api/health/ready/` 503: read `database` / `migrations` in the body → the matching sections below.
3. 5xx spike: search logs for `"level": "ERROR"` and the `request_id`; check recent release (rollback section of docs/release-procedure.md).
4. Rate limiting everyone (429 for all): `DOEDU_TRUSTED_PROXIES` wrong (all clients share the proxy IP) → fix the value and redeploy.

## Database unavailable
Symptoms: readiness 503 `database: unreachable`; API answers 503 `service_unavailable` + `Retry-After`; the worker logs "database unavailable" and backs off (no crash).
Liveness stays green on purpose. Check the DB host/service, disk full, connection limit (`max_connections`), credentials rotated, network. When the DB returns the app and
worker recover on their own (verified). If the data was lost or corrupted → restore (docs/backup-restore.md), then `check_integrity`.

## Reservations not expiring / worker backlog
Symptoms: `ops_status` shows `pending_bookings_overdue > 0`, `jobs_oldest_due_age_seconds` growing, `worker.state = stale|unknown`, metric `doedu_worker_heartbeat_age_seconds` high.
Correctness does not depend on the worker (expiry also happens lazily when a booking is opened/paid and in the worker sweep), but places stay held until then.
1. Is the worker running? Restart it. 2. Look for repeating errors in its log. 3. `ops_status`: `jobs.failed > 0` → inspect rows in Django Admin → *Jobs* (`last_error`, `attempts`);
failed jobs stop after 5 attempts and stay visible. Fix the cause, then set `status=pending` and `attempts=0` on those rows to retry (handlers are idempotent).
4. A job stuck `running` with an old `locked_at` is reclaimed automatically after `JOB_LOCK_TIMEOUT_SECONDS`.
5. As an emergency one-off: `manage.py run_worker --once`.

## Unexpected capacity inconsistency
Symptoms: `check_integrity`/`ops_status` report `capacity_inconsistencies > 0`, or customers see "sold out" with free seats.
1. `manage.py check_integrity` lists departures (`places_taken` vs expected = baseline + live reservations). 2. **Find the cause before repairing**: audit records
(`booking.*`, `service.*`, `capacity.*`), recent deployments, manual SQL. 3. Preview `manage.py repair_capacity`; apply with `--apply` (locks, refuses to exceed capacity, audited).
4. Re-run `check_integrity`. The database CHECK constraints make *overselling* impossible even when counters drift; drift therefore shows as lost availability, not double sales.

## Notification failure
Notifications are in-app rows (no e-mail/SMS yet). Passengers not seeing them: check readiness/DB, that `/api/notifications/` answers (401 when signed out is normal), the
`recover_booking`/`journey_*` jobs in Admin, and that the browser can poll (15 s). Duplicates are prevented by `(user, dedupe_key)`; missing ones can be re-created by re-running the job
(`dedupe_key` makes it safe).

## Failed migration
`safe_migrate` failed: **do not start the new web/worker.** Read the error; the advisory lock is released automatically. If the migration was transactional nothing was applied
(PostgreSQL DDL is transactional; `CREATE INDEX CONCURRENTLY` migrations are not: check for an invalid index with `\d+` and drop it). Fix forward with a new migration or
roll the release back (old code + old/unchanged schema). Restore from backup only if data was damaged. Record the incident.

## Rollback
See docs/release-procedure.md §7. Rolling back code does not undo migrations.

## Suspected credential exposure
1. Decide scope: which secret (secret key, DB role, admin password, `METRICS_TOKEN`, backup storage key, a user's password).
2. **Rotate** in the secret store, then redeploy: `DJANGO_SECRET_KEY` (invalidates all sessions: acceptable, users sign in again), DB role passwords (`setup_db_roles` re-applies them: update the
secret store first), `METRICS_TOKEN`, backup credentials. 3. Review `AuditRecord` and web logs around the exposure (look for operator actions, bookings, role changes).
4. A user account: reset requires admin action (no self-service reset exists; Django Admin → set password) and revoking sessions. 5. Record what was exposed and for how long;
whether personal-data notification duties apply is a **legal/organisational decision** for the controller, not something this repository decides.

## Routine tasks
* **First administrator** (no seed accounts exist in production): `manage.py createsuperuser`. Create operators/passengers in Django Admin; an *operator* user needs `role = operator` **and** an Operator membership
  (Transport → Operator memberships). Use named individual accounts; never share admin credentials.
* **Hosted-demo data**: `manage.py sync_demo_schedule --days 14` (additive; the worker also does this every 6 h when `DEMO_SCHEDULE_DAYS>0`). Demo bookings/accounts are not created: people use real registrations or accounts you create.
* **Restore drill**: `ops/verify-restore.sh <backup dir>` (weekly) and record the date.
* **Rotate the metrics token / secrets**: update the secret store, redeploy (see "credential exposure").
* **Who is running what?** `curl -s https://<host>/api/config/` shows the release id and launch mode.

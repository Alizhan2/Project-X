# Observability
## Logs (stdout; collect with the platform)
JSON lines when deployed, readable text locally. Fields: `ts, level, logger, request_id, message` plus, on access lines: `method, path, status, duration_ms, user_id`.
**Never logged**: request/response bodies, headers, cookies, session ids, passwords, tokens, client IPs (the ingress access log has IPs; set its retention accordingly),
query strings. Messages and tracebacks are additionally scrubbed of e-mail addresses and credential-looking values (`apps/core/logging.py`, tested).
Unhandled errors return `{"code":"server_error","request_id":…}` with no internals; the request id correlates the response with the logged traceback.

## Audit trail (separate from logs)
`core_auditrecord` (Django Admin → Audit records, read-only): who did what to which object: bookings created/cancelled/paid, replacements accepted, operator service
changes, capacity repairs. In production the database makes it append-only for the app role. Debug logs may be discarded; audit records are business history.

## Health and metrics
`/api/health/live/`, `/api/health/ready/` (see docs/deployment.md). `GET /api/ops/metrics/` (Prometheus text, `Authorization: Bearer $METRICS_TOKEN`, 404 without it): `doedu_jobs{status}`,
`doedu_jobs_oldest_due_age_seconds`, `doedu_jobs_stale_running`, `doedu_worker_heartbeat_age_seconds` (-1 = never), `doedu_bookings{status}`, `doedu_pending_bookings_overdue`,
`doedu_replacement_offers{status}`, `doedu_capacity_inconsistencies`, `doedu_release_info`. No personal data. CLI equivalent: `manage.py ops_status`.
Failed bookings/recoveries are visible as: payment attempts with status failed (Admin → Payment attempts), `doedu_jobs{status="failed"}`, replacement offers `invalidated`/`expired`.

## Suggested alerts (to agree with whoever is on call)
| Condition | Severity |
|---|---|
| readiness failing > 2 min | page |
| `doedu_jobs{status="failed"} > 0` | ticket, same day |
| `doedu_jobs_oldest_due_age_seconds > 300` or worker heartbeat age > 120 s | warn → page after 15 min |
| `doedu_pending_bookings_overdue > 0` for > 10 min | warn |
| `doedu_capacity_inconsistencies > 0` | page (business invariant) |
| 5xx ratio > 2 % over 5 min, p95 latency > 1 s (see targets in the verification report) | warn |
| no successful backup in 26 h; last restore drill > 35 days | warn |
External monitoring (uptime checks, a metrics/log service, error tracking) is **not connected**: it needs your decision (cost, account, data leaving the environment). The app is prepared through
configuration only (`METRICS_TOKEN`, stdout JSON logs). Connect Sentry-style error reporting only after a data-minimisation review of what it would receive.

# Release procedure (hosted demonstration)
Nothing here has been performed against a real hosted environment yet: the procedure was rehearsed locally (docs/verification-report.md).

## 0. Version identification
Releases are git tags `vMAJOR.MINOR.PATCH`. The pipeline builds the image with `DOEDU_RELEASE=<tag>-<sha>`. That id is visible in: the UI footer,
`GET /api/config/`, `GET /api/health/ready/`, the `doedu_release_info` metric, every structured log (via the deployment) and the image label
`org.opencontainers.image.revision`. Record the id of the running and the previous release in the change log before starting.

## 1. Required checks (all green, on the tagged commit)
Backend tests on PostgreSQL · `makemigrations --check` · `check --deploy` gate · OpenAPI valid and committed · frontend build + lint · Playwright suite against
the production-like stack · `check_integrity` after the browser run · `pip-audit` + `npm audit --audit-level=high` · secret scan · image builds and runs as non-root.
(`.github/workflows/ci.yml`; locally: see README "Release candidate checks".)

## 2. Before touching production
1. Take a **fresh backup** (`ops/backup.sh`) and confirm the file + checksum exist off-host.
2. Confirm the latest **restore rehearsal** is recent (`ops/verify-restore.sh`, docs/backup-restore.md). A backup that was never restored is not a backup.
3. Read the release's migrations. Classify each: additive (safe) or destructive (needs explicit approval and a separate release).
4. Note how to roll back (step 7) *before* starting.

## 3. Migrate (once)
`docker compose --env-file .env.production -f docker-compose.prod.yml run --rm db-roles` then `... run --rm migrate` (or the platform's one-shot job).
`safe_migrate` takes an advisory lock, applies migrations, creates the cache table and applies history protection. If it fails: stop, do **not** deploy
the new web/worker, go to the runbook "failed migration".

## 4. Deploy
Start the new `web` and `worker` (rolling if the platform supports it; Compose: `up -d`). The old and new versions may overlap briefly: that is why
migrations must be backward compatible. Readiness stays 503 until the schema matches.

## 5. Smoke test (no real data needed)
`/api/health/ready/` is `ok` with the new release id; `/api/config/` shows `launch_mode=demo`; open the site, search, sign in with a *demo* account that the
operator created for this environment, book + simulated-pay one journey, open My journeys; `manage.py ops_status` and `check_integrity` exit 0.
Never run `seed_demo` in production (it refuses to start) and never use load tests there.

## 6. Monitor (first hour, then daily)
Queue age, failed jobs, worker heartbeat, 5xx rate, readiness, `capacity_inconsistencies` (must be 0). Alert thresholds: docs/observability.md.

## 7. Rollback decision and execution
* **Code-only problem, migrations additive**: redeploy the previous image tag (web + worker). The newer schema stays; the old code ignores new columns.
* **Problem caused by a migration**: *application rollback does not reverse a migration.* Options: (a) fix forward with a new migration (preferred);
  (b) restore the pre-release backup (loses everything after it: decide with the product owner; see RPO) ; (c) a hand-written reverse migration reviewed
  like any other change. Never run `migrate <app> <older>` against production without that review.
* Always: capture logs and the request ids involved, then record the incident (runbook).

## Migration rules (summary)
Additive first; defaults for new NOT NULL columns; indexes with `AddIndexConcurrently` (+ `atomic = False`) on large tables; constraints added `NOT VALID`
then validated when tables are large; no data-destroying operations on purchases, payments, refunds or audit records without approval; every migration is
exercised by the test suite (tests create the database through migrations) and by the clean-checkout rehearsal.

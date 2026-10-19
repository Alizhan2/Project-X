# Deployment architecture
Launch modes: (1) local development, (2) **hosted demonstration** (synthetic data, simulated payments, non-valid confirmations),
(3) commercial operation (not possible yet: docs/commercial-readiness.md). This document targets mode 2 and the path to mode 3.
Infrastructure readiness does **not** make the simulated booking flow commercially operational.

## Topology (one small host or a managed container platform)
```
Internet ──HTTPS──> [ingress: TLS, request limits]  ──HTTP──>  web (gunicorn: API + admin + static + SPA)  ──> PostgreSQL 17
                                                               worker (run_worker)  ────────────────────────┘      │
                                                               backup (pg_dump, daily) ───> backup storage (off-host)
```
* **web**: image `Dockerfile` (multi-stage; non-root uid 10001; read-only root filesystem; no shell tools beyond Python; HEALTHCHECK).
  gunicorn `gthread` (2×4), 30 s request timeout, graceful shutdown on SIGTERM. Serves `/api`, `/admin`, hashed `/assets` (immutable cache),
  Django-admin static files and the SPA `index.html` fallback (deep links) through WhiteNoise. No separate web server is required for the demo;
  a CDN/nginx may be put in front later without code changes.
* **worker**: same image, `python manage.py run_worker`: reservation expiry, disruption recovery jobs, session cleanup, heartbeat. Survives DB
  outages (backoff), exits cleanly on SIGTERM, restarts under `restart: unless-stopped`. Run **one or more**: claiming is `SKIP LOCKED` (tested).
* **db**: PostgreSQL 17 (supported until 2029-11). Production must use a managed/regularly patched instance or a hardened container with a persistent volume.
  The development cluster under `~/.doedu-tools` is a convenience binary (no `pg_dump`/`psql`, trust auth, no backups) and **must not be used in production**.
* **No** Kubernetes, queue broker or Redis: the single-tenant demo load does not need them (measured in docs/verification-report.md).
* **Static/uploaded files**: build output is baked into the image; there are no user uploads (no `FileField`, no `MEDIA_ROOT`). Any future upload feature
  needs object storage, size/type validation and a security review first.

## Database roles and privileges (least privilege; verified, see verification report)
| Role | Used by | Can |
|---|---|---|
| `POSTGRES_ADMIN_USER` (bootstrap) | `db-roles` job, backup job | everything; never on web/worker |
| `MIGRATE_POSTGRES_USER` (`doedu_migrator`) | `migrate` job only | owns the schema: DDL |
| `POSTGRES_USER` (`doedu_app`) | web, worker | SELECT/INSERT/UPDATE/DELETE, sequences. **No** DDL, TRUNCATE, CREATE ROLE/DATABASE. After `safe_migrate` (demo tools off) also: audit table append-only; payments/refunds cannot be deleted |

## Migrations: when and how
* Migrations run **once per release, before** the new web/worker start, as the `migrate` job (`manage.py safe_migrate`): PostgreSQL advisory lock
  (replicas/pipelines cannot race), `createcachetable`, history protection. Web and worker never migrate on boot.
* Compatibility rule (expand → deploy → contract): a release's migrations must work with the **previous** application version still running
  (additive: new nullable/defaulted columns, new tables, `CREATE INDEX CONCURRENTLY`). Removing/renaming columns happens only in a *later* release after
  no running code uses them. Destructive migrations need explicit approval. Details: docs/release-procedure.md.
* Readiness (`/api/health/ready/`) is 503 while migrations are pending, so a new version never takes traffic against an old schema.

## Probes
`/api/health/live/` (process only; never touches the DB so a DB outage does not restart healthy servers), `/api/health/ready/` (DB + migrations; worker
state informational), no versions/credentials in the body (release id only). Metrics: `/api/ops/metrics/` (token). See docs/observability.md.

## HTTPS and HSTS rollout (required for production)
TLS terminates at the ingress; the app trusts `X-Forwarded-Proto` only when `DJANGO_SECURE_SSL=true`. Rollout: (1) verify the site works over HTTPS and
http→https redirects; (2) deploy with `DOEDU_HSTS_SECONDS=3600` (1 h); (3) after a week without problems raise to 86400, then 31536000; (4) consider
`DOEDU_HSTS_SUBDOMAINS=true` only if every subdomain is HTTPS-only; (5) do **not** enable HSTS preload without a deliberate, separate decision (hard to reverse).
Rollback of a bad HSTS decision: lower the value; browsers keep the previous max-age until it expires, which is why the start is 1 hour.

## Hosting approaches (provider NOT chosen: nothing is provisioned, no prices assumed)
| Approach | Fits when | Provides | You still handle |
|---|---|---|---|
| A. One VM + Docker Compose (`docker-compose.prod.yml`) + a TLS proxy (Caddy/nginx) | smallest, cheapest to reason about, demo scale | everything in this repo as-is | OS patching, firewall, off-host backup copy, monitoring, host failure |
| B. Managed container platform (any PaaS/container service) with a **managed PostgreSQL** | least operations; automatic TLS | image + env + a one-shot job for `safe_migrate`, worker as a second service | provider-specific wiring; managed-DB backup/restore settings; roles via `setup_db_roles` |
| C. Managed Kubernetes | only if an existing platform team requires it | same images | complexity not justified by current load |
Required capabilities (any provider): run 3 long-lived processes + 2 one-shot jobs from one image; PostgreSQL 17 with automated backups and point-in-time
recovery if available; TLS termination with an `X-Forwarded-Proto` header; secret storage; log collection from stdout; an off-host backup target; a scheduled job runner.
**Decision needed from you:** provider and region, domain name, whether public self-registration should be open (see docs/security.md), who receives alerts.

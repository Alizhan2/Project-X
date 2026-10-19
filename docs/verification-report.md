# Verification report: production preparation
Machine: one macOS laptop (arm64 binaries run under x86_64 PostgreSQL 17.10 build; Python 3.14.8, Node 24.21). The load generator, application and database shared this machine,
so absolute numbers are **not** representative of hosting hardware; they show relative behaviour and, above all, correctness under contention.
Legend: **RAN** = executed with the result shown · **REVIEWED** = read/syntax-checked only · **NOT RUN** = blocked by the environment.

## 1. Baseline and dependency health
| Check | Result |
|---|---|
| Git state | no commits yet (files staged only); nothing was committed or pushed |
| Supported versions (endoflife.date, queried today) | Django 6.1.2 (latest, supported to 2027-04-30; **non-LTS**: plan the move to 6.2/LTS before 2027-04), Python 3.14.8 (to 2030), Node 24 (maintenance to 2028), PostgreSQL 17 (to 2029-11; local dev binary is 17.10, latest 17.11) |
| Python dependency pinning | **fixed**: only top-level packages were pinned. Now `requirements.in` → hash-locked `requirements.txt` (pip-compile, 17 pinned packages incl. transitive, sha256 for every wheel). RAN: installs with `--require-hashes` in a clean venv; 174 tests pass on that set (re-run after the final code change) |
| Vulnerabilities | RAN `pip-audit` on the locked set: none. RAN `npm audit`: 0. (point-in-time; CI repeats) |
| Secret scan | RAN detect-secrets: 8 reviewed false positives baselined (`.secrets.baseline`); gate passes; a planted AWS key + password **is** detected |
| Django deploy checks | RAN: production-style settings start and `check --deploy` leaves only W005/W021 (HSTS subdomains/preload: deliberate, rollout in docs/deployment.md); CI gate encodes this |

## 2. Test evidence (final build)
| Suite | Result |
|---|---|
| Backend (`manage.py test`, PostgreSQL) | RAN **174 passed** (also 174 in a clean-checkout copy: new venv installed with `--require-hashes`, new database) |
| Browser (Playwright, 23 tests incl. axe WCAG scan ×2 viewports, keyboard, deep-link refresh) | RAN **23 passed** on the dev stack; RAN **23 passed** against the production-like stack (gunicorn + WhiteNoise + restricted DB roles + separate worker, new empty database brought up by `ops/run-staging.sh`) |
| Migrations | RAN `makemigrations --check` clean; migrations applied on empty databases (dev, staging) and via `safe_migrate` under an advisory lock; the concurrent-index migration rolled back and re-applied on a scratch database |
| OpenAPI | RAN `spectacular --validate --fail-on-warn`: valid; committed `docs/openapi.yaml`; unit test guards it |
| Lint / types | RAN production build (includes `tsc`): OK; oxlint 0 errors, 6 warnings (React style) |
| Mutation checks (do the tests have teeth?) | RAN: removing the departure row lock makes the concurrency tests fail 3/3 (booking last place and replacement last place); DB CHECK constraint is the backstop |

## 3. Stage 6–7 properties re-verified (disruption recovery, concurrency, idempotency, restart)
Re-run in the suite on PostgreSQL: last place with threads, repeated checkout/payment, reservation expiry racing payment, cancel racing replacement acceptance, repeated disruption events,
stale/expired/invalidated offers, failed simulated payment, cross-passenger access, stale-lock job recovery. Plus over **real HTTP against gunicorn** (production-like, restricted DB role):
* **40 simultaneous passengers for the last place → exactly 1 booking, 39 conflicts, 0 server errors** (p95 138 ms).
* **25 identical checkouts (same Idempotency-Key) → exactly 1 booking**.
* After all load: `check_integrity` OK, 0 capacity inconsistencies, 0 failed jobs.

## 4. Production-like behaviour
| Scenario | Result (RAN) |
|---|---|
| Frontend refresh / deep links | `/booking/DD-…`, `/journeys`, `/status` hard-refresh load the SPA; unknown `/api/…` is a JSON 404; assets cached `immutable`; CSP with no violations; cookies `Secure/HttpOnly/SameSite=Lax` |
| Database stopped under a running stack | liveness 200, readiness 503 (`unreachable`), API → sanitised 503/500 with request id (no internals), SPA and `/api/config/` keep serving; **recovered by itself** when PostgreSQL returned (no app restart) |
| Worker `kill -9` with an overdue reservation and a stale `running` job | restarted worker reclaimed the job; booking expired; places freed |
| Database stopped under a *running worker* | worker stayed up (found and fixed: it previously crashed), backed off, recovered; heartbeat resumed |
| Worker not running | readiness `worker: stale` (200), `ops_status` flags overdue reservations (exit 1), metric ages grow; restart clears it; SIGTERM exits cleanly |
| Many workers | 5 concurrent workers, 60 jobs: each ran exactly once (`SKIP LOCKED`); poison job stops after 5 attempts and stays visible as `failed` |
| Rate limiting | 429 observed from real limits against staging; per-account lockout and per-IP limits tested; a bypass via an existing session was found and fixed |
| Least-privilege database | app role: DML only; DROP/ALTER/TRUNCATE/CREATE TABLE/CREATE ROLE/DROP DATABASE all denied; with history protection: audit append-only, payments/refunds undeletable |
| Hosted-demo data path | new database, demo tools off: `sync_demo_schedule` (additive, no accounts) loaded the network; worker auto-sync keeps it ahead; `seed_demo` refuses |

## 4b. Backup and restore (see docs/backup-restore.md)
RAN a cold physical backup → `DROP DATABASE` → restore to a fresh data directory: state fingerprint identical to pre-backup, integrity OK, app reconnected, 1 s (14 MB, not representative).
**NOT RUN**: `ops/backup.sh`, `restore.sh`, `verify-restore.sh` (no `pg_dump`/`pg_restore`/`psql` locally). Do not treat the pg_dump route as verified until its first real run.

## 5. Performance (bounded, local only; `ops/loadtest.py` refuses non-local hosts without an explicit flag)
Proposed targets for discussion: read endpoints p95 < 300 ms at 20 concurrent users; checkout p95 < 1 s at 30 concurrent; 0 oversells; 5xx < 1 %. Measured on this laptop:
| Scenario | Result |
|---|---|
| Reads, 20 concurrent users × 20 s (search, stops, config, readiness) | 8,801 requests, **440 req/s, p50 42 ms, p95 99 ms, p99 123 ms, 0 errors** (first run: `/api/search` alone p50 61 ms, p95 112 ms) |
| Purchase flow, 30 concurrent users (register → search → reserve → pay) | **30/30 completed**; register p95 857 ms (password hashing), checkout p50 255 ms / p95 409 ms, pay p50 14 ms / p95 196 ms |
| Data volume | 34,448 departures + 100,009 bookings/legs/payments in a scratch DB: expiry sweep 0.006 ms, booking by reference 0.008 ms, job claim 0.008 ms (index scans); in-process multimodal search median 8 ms |
| Finding | search window query used a sequential scan: added `departs_at` index (non-blocking migration). No measurable change at this size: kept for headroom |
Targets met on this hardware; **not evidence for hosted hardware or real traffic**: repeat on the chosen platform before announcing capacity.

## 5b. GitHub Actions, first real runner execution (commit `ac46440`, all 5 jobs green)
First run (`5f8e023`) failed in 2 jobs and found real issues, fixed in `ac46440`: the secret-scan baseline was stale, and the e2e job lacked `DEMO_USER_PASSWORD` (the safeguard that a deployed environment must not use the well-known demo password worked as intended). Also masked the CI throw-away secret key in logs.
**Passing on the runner:** backend (hash-locked install, `check`, deploy-check gate, migrations check, OpenAPI valid+committed, tests) · frontend (type-check build, lint) · security (pip-audit, npm audit, secret scan) ·
**container** (compose file validates, **Docker image builds**, runs as uid 10001, liveness answers without a database) · **e2e** (`ops/run-staging.sh` bring-up on an empty PostgreSQL 17.11 service, then the 23 Playwright tests on Linux/Chromium, then `check_integrity`).
Still not exercised by CI: the full `docker-compose.prod.yml` stack (db-roles → migrate → web → worker as containers), read-only root filesystem at runtime, `pg_dump` scripts, TLS/HSTS.

## 6. Not executed (reviewed only)
The full `docker-compose.prod.yml` stack and the read-only-filesystem runtime (the image build and a non-root liveness check DID run in CI, §5b); `release.yml` (never triggered);
`pg_dump` scripts; real TLS/HSTS/proxy header behaviour; an independent penetration test; manual screen-reader testing.

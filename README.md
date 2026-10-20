# Doedu (provisional name)

Multimodal transport booking MVP (bus · train · taxi) with disruption recovery.
**Everything is simulated**: transport data, payments, tickets. Not production software.

Interface: **English · Русский · Қазақша**, including account emails and PDF/calendar downloads. [Localization behavior and maintenance](docs/localization.md).

Handoff / current blockers: [docs/HANDOFF.md](docs/HANDOFF.md)

Status: **MVP complete (Stages 0–7) and prepared for a hosted demonstration.** Production-readiness assessment: [docs/production-readiness.md](docs/production-readiness.md) · evidence: [docs/verification-report.md](docs/verification-report.md). Commercial operation is **not** ready: [docs/commercial-readiness.md](docs/commercial-readiness.md).

## Layout
- `backend/` Django + DRF modular monolith (`apps/accounts, transport, planning, bookings, payments, disruptions, notifications, core`)
- `frontend/` React + TypeScript + Vite (+ Playwright in `e2e/`)
- `docs/` architecture, demo script, release checklist, limitations, OpenAPI (`openapi.yaml`), plan, backlog, [business rules & state machines](docs/business-rules.md), [demo data](docs/demo-data.md), [decision log](docs/decisions.md); API docs at `/api/docs/` when running
- `docker-compose.yml` db + backend + frontend

## Launch modes
1. **Local development** (below). 2. **Hosted demonstration**: synthetic data, simulated payments, non-valid confirmations (`DOEDU_LAUNCH_MODE=demo`; docs/deployment.md). 3. **Commercial**: not possible yet, the app refuses to start in that mode.

## Setup A — Docker Compose (development)
```bash
cp .env.example .env        # development values (DOEDU_ENV=development); never reuse for hosting
docker compose up --build
```
After start-up: `docker compose exec backend python manage.py seed_demo` (dev-only demo data).
Open http://localhost:5173 (API docs: http://localhost:5173/api/docs/, health: /api/health/).

## Setup B — without Docker (what was verified on the author's machine)
Needs Python 3.14, Node 24, and a running PostgreSQL 16+ with a `doedu` database/user.
```bash
cp .env.example .env
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
cd backend && set -a && source ../.env && set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000      # terminal 1
cd backend && .venv/bin/python manage.py run_worker        # terminal 3: reservation expiry (durable jobs)
cd ../frontend && npm ci && npm run dev                  # terminal 2
```

## Demo data
`cd backend && .venv/bin/python manage.py seed_demo` (see [docs/demo-data.md](docs/demo-data.md)). Required before using search.

## Background worker
`manage.py run_worker` expires unpaid reservations (default 10 min, `RESERVATION_MINUTES`). It is also a Compose service. Expiry additionally happens lazily on access/payment, so the app stays correct if the worker is down; the worker just releases places promptly.

## Tests
```bash
cd backend && set -a && source ../.env && set +a && .venv/bin/python manage.py test
cd frontend && npx playwright install chromium && npm run e2e   # stack running + `manage.py seed_demo` first (tests consume the seeded scenarios, so re-seed before every run; they run serially)
```
Backend tests run against PostgreSQL (the DB user needs CREATEDB). Do not hard-code counts from this README; run the suites.
Demo walk-through: [docs/demo-script.md](docs/demo-script.md).

## Configuration
All config is via environment variables (`.env.example`). `.env` is git-ignored. With `DJANGO_DEBUG=true` and no
`DJANGO_SECRET_KEY`, an ephemeral key is generated; with debug off the key is mandatory.

## Production-style stack (hosted demonstration, staging)
Portable image + compose: `Dockerfile`, `docker-compose.prod.yml`, `.env.production.example` (see [docs/deployment.md](docs/deployment.md), [docs/configuration.md](docs/configuration.md)).
The same sequence works **without containers** against any PostgreSQL (verified locally, this is what CI runs): `ops/run-staging.sh` (roles → locked migrate → static → gunicorn + worker → readiness).
Hosted-demo data: `manage.py sync_demo_schedule` (additive; also run by the worker when `DEMO_SCHEDULE_DAYS>0`). `seed_demo` (destructive reset) never runs in production.
Accounts in a hosted environment: `manage.py createsuperuser` for the first administrator; operators/passengers via Django Admin (Operator users need role `operator` + an Operator membership).

## Release candidate checks (all commands verified locally)
```bash
cd backend && set -a && source ../.env && set +a
python manage.py test                                   # PostgreSQL-backed suite
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file ../docs/openapi.yaml
cd ../frontend && npm ci && npm run build && npm run lint && npm audit --audit-level=high
pip-audit -r backend/requirements.txt --require-hashes   # pip install pip-audit
python manage.py check_integrity && python manage.py ops_status   # after browser tests
```
Dependencies: edit `backend/requirements.in`, then `pip-compile --generate-hashes --output-file=requirements.txt requirements.in` (slow: it hashes every wheel) and install with `pip install --require-hashes -r requirements.txt`.
Operations: [runbook](docs/runbook.md) · [backups](docs/backup-restore.md) · [release procedure](docs/release-procedure.md) · [security](docs/security.md) · [privacy](docs/privacy.md) · [observability](docs/observability.md).

## Account recovery and local backup tools
Password recovery and optional email verification are available. For local development keep `manage.py run_worker` running; email previews are private files in `.local-mail/` (not actual inbox delivery). Hosted SMTP setup and security rules: [docs/account-email.md](docs/account-email.md).

Native backup/restore works without Docker. Put PostgreSQL 17 client tools on PATH, export the libpq connection variables, run `ops/backup.sh`, then rehearse recovery into a scratch database with `ops/verify-restore.sh`. Detailed instructions: [docs/backup-restore.md](docs/backup-restore.md). Current implementation/test evidence: [docs/local-improvements.md](docs/local-improvements.md).

## Faster journey planning
Save directions to your account, repeat a previous journey as a fresh search, filter allowed transport and transfers, and compare up to three current offers with factual explanations. See [docs/search-convenience.md](docs/search-convenience.md) for behaviour, API parameters and verification.

Choose **Arrive by** to find journeys that reach your destination by a chosen date/time, with latest departures first. The deadline is checked again before reserving. See [arrive-by search](docs/arrive-by.md).

## Travel companion

Signed-in passengers see their next confirmed journey on the search page. Confirmed booking pages offer calendar (.ics) and PDF downloads using current timetable estimates. Downloads are static, private, demonstrative copies, not valid tickets. See [travel companion](docs/travel-companion.md).

### Kazakhstan preparation

Open `/kazakhstan` for 20 Kazakhstan cities, three-language region names, KZT and local time (Asia/Almaty). Real supplier access and ticket sales are not enabled. See [Kazakhstan integration and 1TR.kz access](docs/kazakhstan.md).

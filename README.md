# Doedu (provisional name)

Multimodal transport booking MVP (bus · train · taxi) with disruption recovery.
**Transport services, fares, payments, refunds and tickets are simulated.** The Kazakhstan city directory uses official geography; it does not establish real transport coverage. Not commercial software.

Interface: **English · Русский · Қазақша**, including account emails and PDF/calendar downloads. [Localization behavior and maintenance](docs/localization.md).

Handoff / current blockers: [docs/HANDOFF.md](docs/HANDOFF.md)

Temporary hosted demo: [Doedu Kazakhstan](https://doedu-kazakhstan-test-x3wv.onrender.com/) · [legacy fictional network](https://doedu-kazakhstan-test-x3wv.onrender.com/demo). Public release **`12836e8525bb`** is live as of 11 November 2026. [All five CI jobs](https://github.com/Alizhan2/Project-X/actions/runs/43070073333) passed for the deployed commit `12836e8`. Local checks passed with 373 backend tests, 35 frontend unit tests, build/lint and 63 browser scenarios including PWA. Public mobile-browser checks passed for 90 cities, EN/RU/KK city selection, arrive-by/accessibility/budget filters, comparison/reload, cancellation with lost requests/replies, simulated payment, translated PDF/calendar exports and immediate offline invalidation after cancellation. The prior own account and its legacy booking/refund survived the update. Physical-phone/mobile-data testing and ten-user purchase performance remain to be verified. See the [deployment record](docs/render-free-test.md).

Status: **Core demonstration MVP and temporary hosted demo available; production hardening incomplete.** Production-readiness assessment: [docs/production-readiness.md](docs/production-readiness.md) · current hosted evidence: [docs/render-free-test.md](docs/render-free-test.md). Commercial operation is **not** ready: [docs/commercial-readiness.md](docs/commercial-readiness.md).

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
After start-up: `docker compose exec backend python manage.py prepare_kazakhstan_demo` adds Kazakhstan geography and scoped demo operators without resetting existing data. For the older acceptance fixtures, `seed_demo` is a destructive, development-only reset for a fresh disposable database; see [demo data](docs/demo-data.md).
Open http://localhost:5173 for Kazakhstan demo search and booking; `/demo` retains the earlier fictional network (API docs: http://localhost:5173/api/docs/, health: /api/health/).

## Setup B — without Docker (what was verified on the author's machine)
Needs Python 3.14, Node 24, and a running PostgreSQL 16+ with a `doedu` database/user.
```bash
cp .env.example .env
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
cd backend && set -a && source ../.env && set +a
.venv/bin/python manage.py safe_migrate
.venv/bin/python manage.py prepare_kazakhstan_demo
.venv/bin/python manage.py runserver 127.0.0.1:8000      # terminal 1
cd backend && .venv/bin/python manage.py run_worker        # terminal 3: reservation expiry (durable jobs)
cd ../frontend && npm ci && npm run dev                  # terminal 2
```

## Demo data
`prepare_kazakhstan_demo` is additive: 90 city hubs, 180 fictional bus/rail stops, transfer links and two operator accounts. Kazakhstan search generates services only for the selected pair and dates, preserving later operator edits and existing bookings. It does not prebuild a national route mesh. See [Kazakhstan demo behaviour](docs/kazakhstan.md).

The legacy `seed_demo` command is only for resetting disposable development/test fixtures; see [docs/demo-data.md](docs/demo-data.md). Never use it to update an existing user's database.

## Background worker
`manage.py run_worker` expires unpaid reservations (default 5 min, `RESERVATION_MINUTES`). It is also a Compose service. Expiry additionally happens lazily on access/payment, so the app stays correct if the worker is down; the worker just releases places promptly.

## Tests
```bash
cd backend && set -a && source ../.env && set +a && .venv/bin/python manage.py test
cd frontend && npx playwright install chromium && npm run e2e   # use a disposable seeded stack; prepare_kazakhstan_demo adds scoped KZ operators
```
Backend tests run against PostgreSQL (the DB user needs CREATEDB). Browser fixtures consume state: reset only a fresh disposable development/test database with `seed_demo`, then run `prepare_kazakhstan_demo` before the suite. Never reset a user's or live study database for a test run. Do not hard-code counts from this README; run the suites.
Demo walk-through: [docs/demo-script.md](docs/demo-script.md).

## Configuration
All config is via environment variables (`.env.example`). `.env` is git-ignored. With `DJANGO_DEBUG=true` and no
`DJANGO_SECRET_KEY`, an ephemeral key is generated; with debug off the key is mandatory.

## Production-style stack (hosted demonstration, staging)
Portable image + compose: `Dockerfile`, `docker-compose.prod.yml`, `.env.production.example` (see [docs/deployment.md](docs/deployment.md), [docs/configuration.md](docs/configuration.md)).
The same sequence works **without containers** against any PostgreSQL (verified locally, this is what CI runs): `ops/run-staging.sh` (roles → locked migrate → static → gunicorn + worker → readiness).
Hosted legacy schedules: `manage.py sync_demo_schedule` (additive; also run by the worker when `DEMO_SCHEDULE_DAYS>0`). Kazakhstan uses `prepare_kazakhstan_demo` plus generation for the requested pair/date. `seed_demo` (destructive reset) never runs in production.
Accounts in a hosted environment: `manage.py createsuperuser` for the first administrator; operators/passengers via Django Admin (Operator users need role `operator` + an Operator membership).
The Render launcher runs locked migrations, the explicitly enabled guarded legacy bootstrap, then additive `prepare_kazakhstan_demo` before web/worker startup. Kazakhstan operators are `ops.kzbus@doedu.test` and `ops.kzrail@doedu.test`; hosted credentials come from private `DEMO_USER_PASSWORD` (at least 16 characters). Existing passwords, roles, memberships and access revocations are preserved; conflicts require administrator review. See the [study deployment instructions](docs/render-free-test.md).

## Release candidate checks
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

### Kazakhstan demonstration

The home page `/` (also `/kazakhstan`) supports all **90 cities in the official KATO release of 4 November 2026**, multilingual names/regions/aliases, private plans and sharing. In simulation mode it returns bookable generated bus/train offers with KZT prices, five-minute holds, simulated payment/refund and recovery. Kazakhstan timestamps use `Asia/Almaty` (UTC+5) through search, bookings, operator screens and exports; old EUR/Berlin journeys retain their original market. Timetables, prices, durations, stops and accessibility are invented examples. No supplier API, real charge or valid ticket is involved. See [Kazakhstan demo and future integration](docs/kazakhstan.md).

## Installable app (PWA)
Production builds register a service worker (`frontend/public/sw.js`): it caches only static, content-hashed files and the last good `index.html`, never `/api/` or `/admin/`.
Confirmed upcoming bookings are also kept as an on-device copy (see docs/privacy.md) so My journeys works offline. Service worker tests need a production build:
`cd frontend && npm run build && BACKEND_URL=http://127.0.0.1:8000 npx vite preview --host 127.0.0.1 --port 5302` then `PWA_PREVIEW=1 BASE_URL=http://127.0.0.1:5302 npx playwright test pwa` (skipped on the dev server). Also verified against gunicorn + WhiteNoise + the production CSP.

## Alerts (watches)
Passengers can ask to be told when a searched price drops or a journey becomes available (`/alerts`). The worker (`manage.py run_worker`) checks them every 5 minutes and right after relevant changes; opening the Alerts page also checks them, so the feature works without a worker, only less promptly. Alerts only notify: nothing is reserved.

## November requirements alignment

Kazakhstan demo search is the home page; older fictional bookings remain under `/demo` with historic-link compatibility. Five-minute holds, shared walking/boarding connection margins, strict accessibility, constrained recovery, full replacement payments and separate refund/reconciliation states are described in [business rules](docs/business-rules.md). The earlier [requirements alignment](docs/requirements-alignment-2026-11-10.md) is dated evidence; current local/deployment status is in [HANDOFF](docs/HANDOFF.md).

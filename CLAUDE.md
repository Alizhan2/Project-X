# Doedu — working notes for Claude Code

Multimodal (bus/train/taxi) booking MVP. **All data, payments and tickets are simulated.** Not production software.

## Layout
- `backend/` Django 6 + DRF modular monolith. Apps in `backend/apps/`: accounts, transport, planning, bookings, payments, disruptions, notifications, core.
- `frontend/` React 19 + TS + Vite (router: react-router-dom). `frontend/e2e/` Playwright.
- `docs/` plan, backlog, business rules, demo data. Update docs with every feature.
- Same-origin: browser → Vite (:5173) proxies `/api`, `/admin` to Django (:8000).

## Commands
Env: `cp .env.example .env`; load it with `set -a && source .env && set +a` (Django does not read .env itself).
- Backend venv: `python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt`
- Run API: `cd backend && .venv/bin/python manage.py runserver 127.0.0.1:8000`
- Migrate: `manage.py makemigrations <app>` then `manage.py migrate`; CI runs `makemigrations --check`.
- Worker (reservation expiry): `manage.py run_worker [--once]`
- OpenAPI: `manage.py spectacular --validate --fail-on-warn --file ../docs/openapi.yaml`
- Seed/reset demo data (dev only, refuses if DEBUG off): `manage.py seed_demo [--reference-date YYYY-MM-DD]`
- Backend tests (PostgreSQL required, DB user needs CREATEDB): `manage.py test`
- Frontend: `cd frontend && npm ci && npm run dev | build | lint`; e2e: `npm run e2e` (stack running + seeded).
- Docker path: `docker compose up --build` (written, not verified on the author's machine — no Docker there).
- Local PostgreSQL without Docker: see README "Setup B".

## Concurrency rules (see docs/business-rules.md)
Lock departures `ORDER BY pk` with `select_for_update` before touching `places_taken`; booking row lock before departure locks; idempotency keys on checkout/pay; jobs must be idempotent.

## Recovery (Stage 6)
`disruptions/recovery.py`: offers are non-reserving, accept = one all-or-nothing transaction (lock order booking → offer → departures by id). Rules in docs/business-rules.md. E2E dates use Europe/Berlin (`frontend/e2e/demo-day.ts`).

## Production preparation (see docs/production-readiness.md)
- Config is validated at startup (`config/settings.py`): `DOEDU_ENV` (development|test|staging|production) and `DOEDU_LAUNCH_MODE` (development|demo|commercial → refuses). Never relax these checks to make something start.
- Ops commands: `ops_status`, `check_integrity`, `repair_capacity [--apply]`, `state_fingerprint`, `safe_migrate` (advisory lock; the ONLY way migrations run in deployments), `setup_db_roles`, `sync_demo_schedule`, `run_worker`.
- Production-like local run: `ops/run-staging.sh` with the variables from `.env.production.example` (DOEDU_ENV=staging). Load test only local/authorised hosts: `ops/loadtest.py`.
- Dependencies are hash-locked (`backend/requirements.in` → `requirements.txt`). Migrations must be additive/backward compatible; use `AddIndexConcurrently` on big tables.
- Logs are redacted JSON; never add logging of bodies, headers, cookies, IPs or e-mail addresses. Audit records are separate from logs.
- Tools used for evidence live outside the repo (`~/.doedu-tools`: Postgres binaries, pip-tools/pip-audit/detect-secrets). Docker, `pg_dump` and GitHub runners were NOT available: say so rather than claiming they ran.

## Rules of the codebase
- Money: `Decimal`, explicit currency; never floats. Datetimes timezone-aware (UTC stored, `Europe/Berlin` display).
- Capacity is whole-service per departure (`Departure.places_taken`); CHECK constraint prevents oversell.
- Search results are *offers*, not bookings. Bookings must snapshot price, times and cancellation policy.
- Permissions are enforced server-side (object ownership, operator boundary). UI hiding is not access control.
- Config only through env vars; never commit secrets or `.env`.
- Frontend uses the real API; no static stand-in data.

## Definition of done
Frontend+backend work together · state persisted in PostgreSQL · permissions enforced · failure cases handled ·
business-rule tests pass · docs updated · never claim tests pass unless they were actually run.

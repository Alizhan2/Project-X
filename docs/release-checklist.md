# MVP demo release checklist (superseded for hosting by docs/production-readiness.md and docs/release-procedure.md)
Evidence column says what was actually run on the author's machine (macOS, PostgreSQL 17.10 local, Python 3.14, Node 24).
| Item | Status |
|---|---|
| Fresh checkout: new venv + empty DB → `migrate` → `seed_demo` → health OK | done (verified in a temp copy) |
| `makemigrations --check` clean | done |
| Backend tests (`manage.py test`) on PostgreSQL | done: 174 passed (also in a clean copy, hash-locked install) |
| Browser tests (`npm run e2e`) after `seed_demo` | done: 23 passed (dev stack and production-like stack) |
| Frontend `npm ci`, `npm run build`, lint | build ok; lint has 6 warnings (React fast-refresh and setState-in-effect style), 0 errors |
| OpenAPI schema validates (`--fail-on-warn`) | done |
| `check --deploy` with DEBUG off | only SECURE_HSTS_PRELOAD (deliberate) |
| Concurrency (last place, duplicate/parallel payment/acceptance, cancel races) on PostgreSQL | done; lock mutation check fails the tests as expected |
| Restart recovery (stale job reclaimed by a new worker process) | done |
| Anonymous/role access sweep over every API route | done (automated test) |
| Accessibility: axe scan 13 pages × 2 viewports; keyboard test | done (automated only) |
| `docker compose up --build` | **NOT RUN** (Docker unavailable) |
| GitHub Actions workflow | **NOT RUN** (syntax-checked only) |
| Manual screen-reader pass, real-device mobile test | **not done** |
| Production payments/deploy/privacy/legal | out of scope |
Before a demo: re-run `seed_demo`, start backend + frontend + worker, walk through `docs/demo-script.md`.

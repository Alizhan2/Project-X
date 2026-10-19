# Environment configuration guide
Settings are read from environment variables only (`backend/config/settings.py`). **Startup validation**: in `staging`/`production` an unsafe or
incomplete configuration makes the app refuse to start with a message listing every problem (tested in `apps/core/test_hardening.py`).
Templates: `.env.example` (local development), `.env.production.example` (hosted). Real `.env*` files are git-ignored; keep real values in your
platform's secret store, never in the repository, logs, chat or screenshots.

## Environments and launch modes
| `DOEDU_ENV` | Meaning | Defaults |
|---|---|---|
| `development` | local work | `DEBUG` allowed, ephemeral secret key, lenient rate limits, demo tools on, Swagger on, cookies not `Secure` |
| `test` | `manage.py test` (auto-detected) | like development, fast password hasher, in-memory cache |
| `staging` | production rehearsal | everything below must be set explicitly; demo tools only with `DOEDU_ALLOW_DEMO_TOOLS=true`; strict rate limits |
| `production` | hosted | as staging **plus** `DJANGO_SECURE_SSL=true`, https-only trusted origins, demo tools impossible, Swagger off |

| `DOEDU_LAUNCH_MODE` | Meaning |
|---|---|
| `development` / `demo` | synthetic data, **simulated** payments/transport, banner "not valid travel tickets" (driven by `/api/config/`) |
| `commercial` | **refuses to start**: real transport/payment integrations do not exist yet (docs/commercial-readiness.md) |

## Variables
| Variable | Required in prod | Purpose / notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes | ≥ 50 random chars. Rotating it logs everyone out (see runbook "credential exposure") |
| `DJANGO_DEBUG` | must be `false` | |
| `DJANGO_ALLOWED_HOSTS` | yes | explicit host names, no `*` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | yes | `https://` origins of the site |
| `DJANGO_SECURE_SSL` | yes (prod) | HTTPS redirect, HSTS, trust `X-Forwarded-Proto`. Roll out per docs/deployment.md |
| `DOEDU_HSTS_SECONDS` / `DOEDU_HSTS_SUBDOMAINS` | no | default 3600 / false: start small, raise deliberately |
| `DOEDU_TRUSTED_PROXIES` | yes behind a proxy | number of proxies, for the real client IP (rate limits). Wrong value = all users share one limit, or IPs can be spoofed |
| `DJANGO_SECURE_COOKIES` | no | defaults to true when deployed |
| `POSTGRES_HOST/PORT/DB` | yes | |
| `POSTGRES_USER`/`POSTGRES_PASSWORD` | yes | **runtime role**: DML only (`setup_db_roles`) |
| `MIGRATE_POSTGRES_USER`/`_PASSWORD` | migrate job only | owner role used for DDL |
| `POSTGRES_ADMIN_USER`/`_PASSWORD` | role-setup job + backup only | bootstrap superuser; never given to web/worker |
| `DB_CONNECT_TIMEOUT`, `DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS`, `DB_IDLE_TX_TIMEOUT_MS`, `DB_CONN_MAX_AGE` | no | bounded DB behaviour: 5 s / 20 s / 8 s / 30 s / 60 s (deployed) |
| `GUNICORN_*`, `WEB_CONCURRENCY` | no | bind, workers (2), threads (4), timeout (30 s), graceful timeout (30 s), max requests (2000) |
| `THROTTLE_LOGIN/REGISTER/SEARCH/BOOKING` | no | `10/min`, `5/hour`, `120/min`, `30/min` per client (login/register: IP; others: user or IP) when deployed |
| `LOGIN_FAILURE_LIMIT`, `LOGIN_FAILURE_WINDOW_SECONDS` | no | per-account lockout: 5 failures / 15 min → HTTP 429 |
| `SESSION_COOKIE_AGE_SECONDS` | no | 7 days |
| `REGISTRATION_ENABLED` | no | public sign-up switch. **No e-mail verification or password reset exists** (docs/security.md) |
| `ENABLE_API_DOCS` | no | Swagger UI; off in production (the committed `docs/openapi.yaml` is the reference) |
| `METRICS_TOKEN` | no | enables `GET /api/ops/metrics/` (Bearer token). Empty = endpoint answers 404 |
| `RESERVATION_MINUTES`, `REPLACEMENT_OFFER_MINUTES`, `JOB_LOCK_TIMEOUT_SECONDS`, `WORKER_STALE_SECONDS` | no | 10 / 30 / 60 / 60 |
| `DOEDU_RELEASE` | set by the pipeline | git tag/sha; shown in the footer, `/api/config/`, readiness, metrics and logs |
| `DOEDU_ALLOW_DEMO_TOOLS` | no | staging only; **production refuses to start if set** |
| `LOG_LEVEL` | no | `INFO` |
| `FRONTEND_DIST` | image sets it | directory of the built SPA served by the app server |
| `BACKUP_RETENTION_DAYS`, `BACKUP_INTERVAL_HOURS` | backup job | 14 / 24 |

## CORS
The SPA and API are same-origin (the app server serves both; Vite proxies in development), so no CORS headers are sent
(tested). Add `django-cors-headers` only if a genuinely cross-origin client appears, with an explicit origin allow-list.

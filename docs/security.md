# Security review and controls
Scope: the hosted-demonstration launch mode (synthetic data, simulated payments). A review of a codebase by its authors is not a penetration test; commission an
independent one before any commercial launch.

## Reviewed and verified (with evidence)
| Area | Control | Evidence |
|---|---|---|
| Passenger ownership | every booking/offer/notification query is filtered by the signed-in user; other users get **404** (no existence leak) | `bookings/tests.py OwnershipTests`, `disruptions/test_recovery.py` (offer access), e2e |
| Operator boundary | operator routes need role `operator` + membership; every query scoped to the operator; foreign objects 404; no contact data in impact views | `disruptions/tests.py OperatorPermissionTests` |
| Admin | Django Admin requires staff; passengers/operators redirected; audit/payments/refunds read-only in Admin | `core/tests.py SecuritySweepTests` |
| Anonymous access | an automated sweep over **every** `/api/` route proves anonymous requests are refused unless on an explicit public list | `SecuritySweepTests` (fails if a new endpoint is left open) |
| CSRF | enforced on every unsafe method incl. login/register (custom auth class); token rotates on login; SPA re-reads the cookie | `accounts/tests.py` |
| Sessions | `HttpOnly`, `SameSite=Lax`, `Secure` when deployed; 7-day age; logout flushes the session; expired sessions purged hourly by the worker | settings; staging run (cookie flags captured) |
| Passwords | Django PBKDF2, 4 validators (length, common, numeric, similarity); never returned or logged | `core/test_hardening.py` |
| Abuse resistance | per-IP login/register limits, per-account lockout (5 fails/15 min → 429, other accounts unaffected), search and booking limits per user/IP | `AbuseResistanceTests`; real 429s observed against staging |
| Injection | ORM everywhere; the only raw SQL is constant or parameterised (grep-verified); identifiers composed with `psycopg.sql.Identifier` | code review |
| XSS | React escaping; no `dangerouslySetInnerHTML`/`innerHTML`/`eval` (grep: 0); CSP `script-src 'self'; style-src 'self'` verified with no violations on the deployed-style stack | Playwright console check |
| Clickjacking / sniffing / referrer | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy`, `Cross-Origin-*` | header tests |
| Data exposure in errors | generic JSON 500/503 + request id; no stack traces, SQL or hostnames (DB outage test uses a fake IP and asserts absence) | `DatabaseOutageTests` |
| Dev endpoints | demo reset/seed refuse to run in production (also refuses to *start* if the flag is set); Swagger off in production; metrics need a token | `StartupValidationTests` |
| Dependencies | `pip-audit` (hash-locked set) and `npm audit` clean on the day of the check; CI re-runs them | verification report |
| Secrets | no secrets committed (scan baselined and proven to detect planted keys); startup refuses placeholder secrets in deployed environments | `.secrets.baseline`, verification report |
| Least-privilege DB | runtime role cannot DDL/TRUNCATE/create roles; audit append-only; payments/refunds undeletable by the app | staging privilege probe |
| Idempotency/replay | checkout, payment, acceptance keys + DB unique constraints; concurrent duplicates tested over HTTP | load test `dup`, tests |

## Known gaps (must be decided before public launch)
1. **No e-mail infrastructure → no account verification and no self-service password reset.** There is deliberately **no fake reset flow**. Consequences:
   anyone can register with any e-mail address (the address is unverified contact data); a user who forgets a password needs an administrator (Django Admin → set password).
   Launch options: (a) keep `REGISTRATION_ENABLED=false` and create accounts for invited testers; (b) allow open registration only for the clearly-labelled synthetic demo and accept the above;
   (c) build verified e-mail + reset first (needs an e-mail provider: external account → your approval).
2. **Ingress-level protection is still required**: application throttling is not DoS protection. Put the app behind a managed ingress/WAF or proxy with connection and request-rate limits, request-size limits and TLS hardening; limit `/admin/` to trusted networks/VPN.
3. No MFA, no password-breach checking, no IP-based anomaly detection.
4. Admin accounts: use a few named, individual staff accounts with strong unique passwords. The `admin@doedu.test` demo account exists **only** in synthetic dev/staging data (never create demo accounts in a public environment).
5. `SECURE_HSTS_PRELOAD` and includeSubDomains are intentionally off (docs/deployment.md rollout).
6. Rate-limit counters live in the shared database cache; under attack that adds database load: another reason for ingress limits.
7. No automated vulnerability monitoring beyond CI runs; subscribe to Django/gunicorn/Postgres security announcements.

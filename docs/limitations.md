# Known limitations and unresolved items
**Product/model**
- Everything is simulated: data, payments, refunds, taxis, confirmations. Not production software; no legal tickets.
- Capacity is per whole service run: a passenger blocks a place from first to last stop (conservative; documented simplification). Seeded "places taken" are plain counters.
- Planner is bounded and not exhaustive (≤3 legs, 24 h window, waits ≤180 min, max 40 results; replacements: 6 h window, ≤6 h later arrival, ≤3 offers). No walking before the first leg except during recovery.
- Taxis: per-vehicle price, ≤4 passengers, pickups 05:00–23:59, no real dispatch. One currency, one timezone.
- Completed legs are *derived* from live times (no stored flag); retained legs are never modified. A leg already travelled is not refunded.
- Replacement offers are non-reserving by design: a place can disappear between offer and acceptance (revalidated, passenger is told).
- Cancellation is whole-journey only; no partial cancellation, no changing traveller names after purchase.
- Notifications are in-app and polled every 15 s; no email/SMS. Single accessibility preference is only informational (no filtering by accessibility).
**Security/ops**
- No rate limiting/lockout on login, no password reset or email verification, no MFA. Demo accounts share a documented dev password and exist only after `seed_demo` (refuses to run unless DEBUG).
- Django dev server used locally; production needs a WSGI server, HTTPS (`DJANGO_SECURE_SSL=true`), backups, monitoring. `SECURE_HSTS_PRELOAD` intentionally not enabled.
- Personal data kept: name per passenger and one contact email per booking; no retention/deletion policy implemented.
**Verification**
- Docker Compose and the GitHub Actions workflow were reviewed and syntax-checked only; **never executed** (no Docker, no runner).
- Accessibility: automated axe-core WCAG 2.1 A/AA scan + a keyboard test; no manual screen-reader or user testing.
- Browser tests run serially against a freshly seeded database and depend on it. Tested on Chromium only, macOS.
- 6 `oxlint` warnings (React fast-refresh export style and "setState in effect" pattern) are unresolved; 0 lint errors.
- Production preparation: see docs/production-readiness.md (blockers/decisions), docs/security.md (known gaps: no e-mail verification or password reset, no MFA), docs/privacy.md (retention/deletion not built).
- Django 6.1 is a non-LTS release (support ends 2027-04-30): plan the upgrade.

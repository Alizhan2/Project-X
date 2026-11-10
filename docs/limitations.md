# Known limitations and unresolved items
**Product/model**
- Booking inventory, payments, refunds, taxis and confirmations are simulated. Kazakhstan city geography is real, but supplier inventory is not connected. No valid tickets or commercial sales.
- Capacity is per whole service run: a passenger blocks a place from first to last stop (conservative; documented simplification). Seeded "places taken" are plain counters.
- Planner is bounded and not exhaustive (≤3 legs, 24 h departure window forward from depart-after or backward from arrive-by, waits ≤180 min, max 40 results; replacements: 6 h window, ≤6 h later arrival, ≤3 offers). Arrival deadlines are checked before reservation, not guaranteed or stored as contractual promises. No walking before the first leg except during recovery.
- Fictional demo taxis: per-vehicle price, ≤4 passengers, pickups 05:00–23:59, no real dispatch. Demo bookings retain EUR/Europe-Berlin; Kazakhstan plans use KZT/Asia-Almaty without currency conversion.
- Boarded/completed markers protect used legs; schedule-derived times remain a fallback for historic demo rows. There is no real boarding scan or live vehicle tracking. Retained legs are never replaced or refunded as unused.
- Replacement offers are non-reserving by design: a place can disappear between offer and acceptance (revalidated, passenger is told).
- Cancellation is whole-journey only; no partial cancellation or changing traveller names after purchase. Whole cancellation releases its live reservation counters, including used services; used legs receive no refund. Recovery separately preserves used/retained legs. A general amendment/per-leg cancellation workflow remains outside this increment.
- Notifications are in-app and polled every 15 s; no journey email/SMS (account-security emails are separate). Strict accessibility filters require confirmed vehicles, stops and transfer paths; unknown excludes an offer and may leave few demo matches.
**Security/ops**
- Login has rate limiting and account lockout. Password recovery and optional email verification are implemented (account-email.md); hosted delivery still needs configured SMTP. No MFA. Demo accounts share a documented development password; seed/reset tools are restricted to allowed development/staging environments.
- Django dev server used locally; production needs a WSGI server, HTTPS (`DJANGO_SECURE_SSL=true`), backups, monitoring. `SECURE_HSTS_PRELOAD` intentionally not enabled.
- Personal data kept: name per passenger and one contact email per booking; no retention/deletion policy implemented.
**Verification**
- CI ran successfully at `ac46440` (5 jobs, including image build/non-root liveness). Full Docker Compose and read-only container runtime remain unverified. Check the GitHub Actions run for the current commit; the historical run does not verify later changes. Logical backup/restore scripts were exercised on PostgreSQL 17.11 without Docker on 2026-10-20.
- Accessibility: automated axe-core WCAG 2.1 A/AA scan + a keyboard test; no manual screen-reader or user testing.
- Browser tests run serially against a freshly seeded database and depend on it. Tested on Chromium only, macOS.
- 5 `oxlint` warnings (React fast-refresh export style and "setState in effect" pattern) are unresolved; 0 lint errors.
- Production preparation: see docs/production-readiness.md (blockers/decisions), docs/security.md (known gaps: hosted SMTP not connected, verification optional, no MFA), docs/privacy.md (retention/deletion not built).
- Django 6.1 is a non-LTS release (support ends 2027-04-30): plan the upgrade.

## November 2026 alignment

The main page is Kazakhstan planning and `/demo` is the fictional booking network. Recovery preferences, full-price replacement charges, separate refund operations and payment reconciliation are documented in business-rules.md. They remain simulators, not supplier-backed settlement. Review requirements-alignment-2026-11-10.md for current verification and remaining scope; historical counts above do not certify newer revisions.

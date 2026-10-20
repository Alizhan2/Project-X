# Handoff
Updated 2026-10-20. Current evidence: [travel-companion.md](travel-companion.md), [search-convenience.md](search-convenience.md) and [local-improvements.md](local-improvements.md).

## Current state
- Latest update: English/Russian/Kazakh SPA, API presentation messages, queued account emails, PDF and calendar downloads. See [localization.md](localization.md). No new dependencies or migrations; restart the worker with the web service. Local checks: 224 backend tests, nine frontend checks, 23 existing browser scenarios. This localization change has not been pushed or checked in GitHub Actions yet.
- Previous update: arrive-by search and arrival-deadline validation at itinerary/checkout, plus keyboard focus preservation during sorting. Local checks: 218 backend tests, five frontend tests and 23 browser scenarios passed. No new dependencies or migrations. See arrive-by.md and GitHub Actions for this revision's CI result; preceding commit 942792d passed all five jobs.
- Previous update: next-journey card, current booking timeline, private calendar/PDF downloads. Local verification: 205 backend tests, five frontend tests and 23 browser scenarios passed. Install the updated hash-locked requirements (ReportLab); no migration is required. Consult GitHub Actions for this revision's CI result; the preceding feature commit fa843f8 passed all five jobs.
- Previous feature update: saved directions/repeat search, server-side filters and three-journey comparison. Additive accounts migration 0003 applied locally. Local checks passed: 197 backend tests, 5 comparison tests and 23 browser scenarios. Consult GitHub Actions for this revision's CI result; the prior account-email/UI commit 82829f7 passed all five jobs.
- Repository: https://github.com/Alizhan2/Project-X (public). This update contains the account-email, UI and backup changes. Earlier CI at `ac46440` passed all five jobs; consult the GitHub Actions run for the current commit before deploying.
- MVP stages 0–7 plus production preparation already existed. Added password recovery, optional email verification, UI improvements, native logical backup verification and documentation corrections.
- Transport, payments, refunds and tickets remain simulated. No commercial launch or server deployment occurred.
- Existing local PostgreSQL (:5432), Django (:8000) and Vite (:5173) were reused. An additive account migration was applied; the user's database was not reseeded. The local worker is now running for email and reservation jobs.
- Account mail uses private `.local-mail/` preview files locally. Run `manage.py run_worker` after restarting the environment. Actual SMTP is not connected. See account-email.md.
- PostgreSQL 17.11 client tools live at `~/.doedu-tools/postgres-client-17/bin`; logical backup/restore was verified without Docker.

## Next deployment work
Choose server/hosting project, SSH access and exact hostname/DNS provider before any deployment. Inspect existing services/ports first, then follow deployment.md and release-procedure.md. Full Docker Compose verification is deferred by the user's choice to continue without Docker. If using a native deployment, explicitly arrange service supervision, least-privilege DB roles, TLS and backups; do not run Django's development server publicly.

## Remaining unverified items
Full container stack and read-only filesystem runtime, release-image publishing workflow, real TLS/HSTS/proxy setup, actual SMTP inbox delivery, hosted/off-host backup scheduling, independent security review and manual screen-reader testing. Earlier CI image build/liveness and current native logical backup evidence should not be confused with these checks.

## Kazakhstan preparation (2026-10-20)

Added `/kazakhstan` and `/api/kazakhstan/{catalog,search}/`: 20 real cities, EN/RU/KK names, KZT, Asia/Almaty. Search returns explicit `provider_not_connected` (503), not fabricated inventory. The OneTR boundary awaits official partner documentation/access. No migrations or changes to historic/demo bookings. Booking remains disabled. See [integration milestones and access request](kazakhstan.md).

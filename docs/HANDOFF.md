# Handoff

Updated 11 November 2026. See [requirements alignment](requirements-alignment-2026-11-10.md) for the requirements increment, [business rules](business-rules.md) for current behaviour and the [temporary Render study deployment](render-free-test.md) for hosting preparation. Earlier dated verification documents are historical evidence, not certification of the current revision.

## Current product

- Kazakhstan planning is `/`: 20 real cities, EN/RU/KK, KZT, Asia/Almaty, private plans and parameter-only sharing. Provider access is not connected; no fabricated inventory or ticket sale.
- Fictional demo booking is `/demo`: EUR, Europe/Berlin, buses/trains/on-demand taxis, up to three legs, arrive-by, filters, comparison, favourites, repeats, upcoming trip, calendar/PDF and offline copies. Historic fictional root links redirect preserving parameters. `/kazakhstan` remains compatible.
- Five-minute default reservations. Explicit walking/boarding connection margins and risk statuses; strict accessibility excludes unknown vehicles, stops and transfer paths.
- Recovery preferences: reachable location, earliest departure, deadline, payment-now budget, accessibility. Usable onward legs may be retained. Full new fare is charged; eligible old-leg refunds are separate.
- Durable payment attempts support unknown/pending results, same-key reconciliation and full compensation after failed confirmation. Refund requests, pending outcomes, completion, failures and retries are visible.
- Accounts, email recovery/verification, operator changes, notices, audits, alerts/followed lines and Help remain available. All new presentation strings have RU/KK translations.

## Local update and verification

Additive migrations are required for transport transfer metadata, booking access/used markers, offer constraints and payment/refund lifecycle fields. Apply via `manage.py safe_migrate` and restart both application and worker. Do not reseed the user's database. A private pre-migration PostgreSQL backup was saved for this local update.

For the earlier requirements increment, local checks passed: 315 backend tests, 27 frontend unit tests, build/lint/schema checks, 51 standard browser scenarios and 2 separately enabled PWA scenarios. Combined evidence is recorded in requirements-alignment-2026-11-10.md; those counts are not a rerun of the current hosting changes.

For the Render preparation, all 326 backend tests passed, including eleven focused runtime/bootstrap tests. The native production-mode rehearsal completed ten concurrent purchases, passed the integrity check, and preserved all 18 users' password hashes and 14 bookings across a launcher restart; its temporary database and role were removed. Render then built and deployed the image. Public HTTPS, worker readiness, a 390px mobile browser walkthrough, registration/booking/payment/downloads, Kazakhstan plan/sharing and repeat-deployment persistence passed. See [hosted evidence and release CI](render-free-test.md); physical-phone and hosted ten-user performance checks remain for the session.

## Remaining boundaries

- All booking inventory, payments, refunds and confirmations remain simulated; commercial mode is still refused.
- Recorded used markers and recovery preserve used legs, but general per-leg cancellation/amendment is not implemented; whole cancellation retains its documented capacity-counter simplification.
- Actual mail delivery, off-host backup scheduling, full Compose/read-only runtime and manual screen-reader/user studies remain separate work. The Render app container with managed PostgreSQL is running, but that does not verify the full local Compose topology or a read-only filesystem. Render Free blocks normal SMTP ports; email delivery is excluded from the temporary study.
- Process-plan activities, team hours/approvals and usability participant responses must be recorded from real events, not generated from software state.

## Deployment

Repository: https://github.com/Alizhan2/Project-X. The temporary Render study deployment is live at https://doedu-kazakhstan-test-x3wv.onrender.com/ (`/demo` for fictional booking), release `e2e4b5a3c649`: one Docker web service with a cohosted worker and a dedicated synthetic PostgreSQL 17 database, both free. All five [release CI jobs](https://github.com/Alizhan2/Project-X/actions/runs/43047350403) passed. The plan was reviewed and explicitly approved by the user. The unrelated `sanapath-ai` service was not changed.

Public capacity results: ten simultaneous browser searches passed (max 2.41s), and ten simultaneous registrations succeeded with p95 47.9s. The public purchase batch verified three completed flows; seven search responses were interrupted in the Python client, with no matching application-log entries. This does not establish ten-user public purchase concurrency. All created check bookings were cancelled; shared recovery fixtures remain intact. Stagger registration or create accounts before the session, and exclude the marked hosted test accounts from participant observations. Full details are in the [study evidence](render-free-test.md).

Review the Blueprint before approving resource creation, leave automatic deployment off, and follow [render-free-test.md](render-free-test.md). Never transfer the user's local database. Guarded bootstrap seeds only a new empty study database once; generated passenger/operator credentials stay private in Render Dashboard, and the administrator has a separate password. The normal ten-account booking task uses NG-BUS → RV-BUS tomorrow at 16:00; shared recovery/operator fixtures require moderation.

Free web sleep pauses the worker; warm the site before testing. Free PostgreSQL expires after 30 days without automatic backups. This study uses the managed database-owner credential for runtime as well as migrations, so full database least privilege and production operation are not established. Kazakhstan plans do not expose real ticket inventory. Follow [deployment.md](deployment.md) and [release-procedure.md](release-procedure.md) for the broader hardening work; never expose Django's development server publicly or relax startup gates. Real supplier integration needs official documentation, permitted fixtures and server-side credentials.

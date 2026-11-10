# Handoff

Updated 10 November 2026. See [requirements alignment](requirements-alignment-2026-11-10.md) for this increment and [business rules](business-rules.md) for current behaviour. Earlier dated verification documents are historical evidence, not certification of the current revision.

## Current product

- Kazakhstan planning is `/`: 20 real cities, EN/RU/KK, KZT, Asia/Almaty, private plans and parameter-only sharing. Provider access is not connected; no fabricated inventory or ticket sale.
- Fictional demo booking is `/demo`: EUR, Europe/Berlin, buses/trains/on-demand taxis, up to three legs, arrive-by, filters, comparison, favourites, repeats, upcoming trip, calendar/PDF and offline copies. Historic fictional root links redirect preserving parameters. `/kazakhstan` remains compatible.
- Five-minute default reservations. Explicit walking/boarding connection margins and risk statuses; strict accessibility excludes unknown vehicles, stops and transfer paths.
- Recovery preferences: reachable location, earliest departure, deadline, payment-now budget, accessibility. Usable onward legs may be retained. Full new fare is charged; eligible old-leg refunds are separate.
- Durable payment attempts support unknown/pending results, same-key reconciliation and full compensation after failed confirmation. Refund requests, pending outcomes, completion, failures and retries are visible.
- Accounts, email recovery/verification, operator changes, notices, audits, alerts/followed lines and Help remain available. All new presentation strings have RU/KK translations.

## Local update and verification

Additive migrations are required for transport transfer metadata, booking access/used markers, offer constraints and payment/refund lifecycle fields. Apply via `manage.py safe_migrate` and restart both application and worker. Do not reseed the user's database. A private pre-migration PostgreSQL backup was saved for this local update.

Local checks passed: 315 backend tests, 27 frontend unit tests, build/lint/schema checks, 51 standard browser scenarios and 2 separately enabled PWA scenarios. Final combined evidence is recorded in requirements-alignment-2026-11-10.md. No push, GitHub CI run, remote server or external publication is implied by local checks.

## Remaining boundaries

- All booking inventory, payments, refunds and confirmations remain simulated; commercial mode is still refused.
- Recorded used markers and recovery preserve used legs, but general per-leg cancellation/amendment is not implemented; whole cancellation retains its documented capacity-counter simplification.
- Actual SMTP delivery, public server/domain/HTTPS, off-host backup scheduling, full container/read-only runtime and manual screen-reader/user studies remain separate work.
- Process-plan activities, team hours/approvals and usability participant responses must be recorded from real events, not generated from software state.

## Deployment

Repository: https://github.com/Alizhan2/Project-X. Choose hosting, exact hostname and DNS provider before deploying. Inspect services first; follow deployment.md and release-procedure.md. Never expose Django's development server publicly or relax startup safety gates. Real supplier integration needs official documentation, permitted fixtures and server-side credentials.

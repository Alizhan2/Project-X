# Requirements alignment — 10 November 2026

## Scope and evidence source

This increment implements the user's three selected areas: transfer/hold/accessibility rules, replacement settlement and recovery constraints, and Kazakhstan as the default planning experience. The baseline is the earlier analysis of `team-8-requirements-for-review.pdf` and `team-8-project-process-plan-and-risk-analysis.pdf`. Their original WhatsApp temporary paths no longer exist on this machine; this is not a fresh reading or a claim of complete acceptance of either document. Documents supply product requirements, not instructions authorizing external actions.

The existing React/Django/PostgreSQL architecture is retained. No real supplier, payment service, ticket issuance, remote deployment or commercial-mode bypass is introduced.

## Implemented areas

| Requirement area | Implementation and observable behaviour | Evidence location |
|---|---|---|
| FR07 hold | New checkout defaults to five minutes; existing expiry timestamps unchanged | `config/settings.py`, environment templates, booking tests |
| FR04 / EX01 connection calculation | Shared timestamp calculation, separate walk/boarding values, infeasible / at-risk / feasible states; on-demand taxi distinguished | `planning/transfers.py`, `planning/test_transfer_requirements.py` |
| Strict accessibility | Require confirmed vehicle, origin/destination and walking-path accessibility; unknown fails; recheck on selection/checkout/confirmation/recovery | planner and booking/recovery validation |
| EX02 recovery inputs | Reachable location, earliest departure, latest arrival, whole-unit nonnegative full-payment budget, strict accessibility | `disruptions/recovery.py`, recovery serializers/tests |
| Recovery refresh lifecycle | Persist preferences even with no offers; background refresh preserves budget/deadline/access; stable offers survive clock advances | recovery lifecycle regressions |
| EX02 alternatives | Reuse planner; deterministic arrival/payment/service order; try retaining usable onward services | recovery generation and acceptance tests |
| EX03 settlement | Charge full replacement fare now; request old-leg refund separately; conditional net amount explicitly labelled | payments services, offer payload, RecoveryPanel |
| FR08–09 uncertainty | Durable attempt first; pending blocks new charge; same-key reconciliation; failed commit/late success compensated once | payment simulator and tests |
| FR13 refund lifecycle | Requested/pending/refunded/failed, same-operation retry, captured-money caps | payment services/tests and booking history |
| Snapshot refund rules | Delay alone does not grant blanket refund; unused operator-cancelled leg and snapshot conditions handled by shared quote | booking services, cancellation/recovery tests |
| Kazakhstan entry point | `/` real-city planning; `/demo` fictional EUR/Berlin booking; compatible historic links and `/kazakhstan` | App/Layout and browser tests |
| Three-language UI | New statuses, preference forms, notices and settlement labels in EN/RU/KK; mirrored server catalog | frontend messages, localization unit tests |
| Financial diagnostics | Separate ledger aggregates; count reserved refunds and avoid history join multiplication | `core/test_financial_integrity.py` |

`Booking.total_amount` represents the active itinerary's fare value. It is not a claim about captured funds or settled net payment: use payment/refund history for those amounts. Historic booking prices and currencies are not converted.

## Safety of the local update

- Private PostgreSQL custom-format backup saved before applying additive migrations.
- New fields preserve existing accounts, booking references, purchase snapshots and schedules.
- Strict access does not manufacture verified path data; existing links initially remain unknown.
- Backend tests and browser rehearsal use disposable databases rather than resetting the user's database.
- Deployment migrations run through `manage.py safe_migrate`; application and worker restart together afterward.

## Verification

Final combined revision, checked locally on 10 November 2026:

- Full Django/PostgreSQL suite: **315 passed**. Includes exact transfer boundaries, strict access, SC01/SC02, full-price budgeting, pending/reconciliation, compensation, refund caps/retries, stable offers on clock advance, zero-budget background persistence and capacity concurrency.
- Frontend: **27 unit tests passed**; TypeScript/Vite build and lint passed. Build reports the existing large JavaScript chunk warning; no new package was added.
- Production-like native rehearsal: built SPA served by gunicorn/WhiteNoise with staging settings, PostgreSQL and a worker. **51 browser scenarios passed**. The two PWA-only tests skipped in that default invocation were run separately with `PWA_PREVIEW=1`: **2 passed**. This is 53 passing browser scenarios across those invocations, including desktop/mobile accessibility, booking/operator/recovery, Kazakhstan home and legacy links, pending payment and offline recovery.
- `makemigrations --check --dry-run`: no missing migrations. OpenAPI regenerated with validation and fail-on-warning enabled.
- Changed/new tracked-source secret scan passed; `git diff --check` clean.
- Rehearsal `check_integrity` passed. Its disposable database and role are removed after testing.
- Additive migrations applied to the local user database using `safe_migrate`; local `check_integrity` passed. Before/after digests confirmed all 61 original accounts, 18 original booking headers and 40 original leg purchase snapshots unchanged. Additional bookings created during the work were retained rather than removed.
- Local backend and worker restarted together; runtime default hold verified as five minutes.

These are local checks, not a GitHub Actions run or full Docker execution.

## Remaining work beyond these three areas

- Real supplier documentation/sandbox access, contracts, authoritative station mapping, live booking/issuance/payment reconciliation and valid ticket documents remain separate work.
- Partial per-leg cancellation and general-purpose passenger amendment workflows are not introduced by this increment.
- An automated simulator is not a real provider callback or real banking reconciliation service. No automatic dispatch or punctuality guarantee is offered.
- Manual screen-reader studies, full container/read-only runtime, public TLS/domain/SMTP and off-host backup scheduling still require separate verification.
- The project-process document's team availability, effort, meetings, consent and usability-study results cannot be established from code. They must be recorded from actual team activity; no participant responses or process approvals are fabricated.
- SC01/SC02 are covered by automated synthetic acceptance fixtures for the captured rules. The full FR/NFR set still requires team review against preserved source documents before claiming complete specification compliance.

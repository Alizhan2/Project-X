# Architecture notes
One repository, one PostgreSQL database, one Django project (modular monolith) plus a React SPA served same-origin
(Vite proxy in dev). Worker = same codebase, separate process (`manage.py run_worker`).

| Domain (`backend/apps/`) | Owns |
|---|---|
| accounts | `User` (role), session login/register/logout with CSRF on every unsafe request |
| transport | operators, hubs/stops, routes, dated departures (capacity counter), fares, cancellation policies, transfer links, taxi offers; operator workspace API (`operator_views.py`); demo data |
| planning | pure read logic: bounded multi-leg search, itinerary validation (`build_itinerary`) used at checkout and recovery |
| bookings | checkout/reservations, bookings + leg snapshots, expiry, cancellation + refund rules |
| payments | simulated payment attempts (initial/replacement), refunds |
| disruptions | operator change handling, live re-timing/assessment, replacement offers + acceptance |
| notifications | in-app notifications (polled), idempotent creation |
| core | health, durable job queue (`Job`), audit trail (`AuditRecord`) |

## Request/consistency model
- Offers (search results, replacement offers) are read-only views of the data; nothing is reserved until checkout/acceptance.
- Money/capacity writes happen in short transactions: **booking row → offer row → departure rows ordered by id**. `Departure.places_taken` has a CHECK
  constraint (`<= capacity`), so a locking bug fails loudly rather than overselling.
- Idempotency: `Idempotency-Key` on checkout and payment/acceptance; unique constraints back it (`(user,key)`, `(booking,key)`, one initial payment
  per booking, `refund (booking,key)`, live replacement fingerprint).
- Background work: jobs in PostgreSQL (`FOR UPDATE SKIP LOCKED`, stale-lock reclaim, retries with backoff, `dedupe_key`). Handlers are idempotent.
  Expiry additionally runs lazily and in a worker sweep, so correctness never depends on the worker being alive.

## Disruption flow
operator `apply_change` (one transaction: change, event row, notifications, audit, queued `recover_booking` jobs) → `ensure_offers` (planner search from the
remaining journey, ≤3 offers, fingerprinted) → passenger `accept_offer` (revalidate everything, replace legs, settle money, all-or-nothing).
Rules: `docs/business-rules.md`. Data: `docs/demo-data.md`. API: `docs/openapi.yaml` (generated, validated) and `/api/docs/`.

## Regenerating API docs
`cd backend && python manage.py spectacular --validate --fail-on-warn --file ../docs/openapi.yaml`

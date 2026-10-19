# Stage 0 — scope, assumptions, architecture, risks
Legend: **[done]** implemented and verified · **[proposed]** planned, not built.

## Workspace findings
Workspace was empty (no code, no repo instructions, no git). Docker and PostgreSQL were not installed.

## Scope [proposed]
Per the product brief: one demo region (fictional, Europe/Berlin timezone), EUR, synthetic data, ≤3 legs, capacity by
passenger count per departure, simulated payments/refunds/taxi. Out of scope: real payments, legal tickets, driver app,
seat selection, geocoding, ML, dynamic pricing.

## Assumptions (reversible)
1. Region is fictional ("Doedu Valley") so synthetic data is never mistaken for real timetables.
2. Stored datetimes are UTC; display/planning in Europe/Berlin. Demo dates are generated relative to a reference date.
3. Capacity is per scheduled departure (whole-service): a bus departure has N places; no per-segment capacity. Limitation:
   a passenger riding only part of a route consumes a place for the whole route.
4. Operator users have exactly one operator membership.
5. Replacement of a disrupted journey re-plans only from the disrupted leg onward; price difference settled by
   simulated extra payment or refund.
6. Taxi offers are simulated per request (fixed price table by hub pair + pickup delay), not stored timetables.
7. Python 3.14 / Node 24 (only versions available locally); Django 6.1.2, DRF 3.18.3, PostgreSQL 17, React 19, Vite 8.

## Open questions
- Is a fictional region acceptable, or should it mimic a real one (naming only)?
- Language: English-only UI for MVP?
- Refund rule defaults (e.g. full refund until 24h before departure, 50% until 2h, none after) — proposed, confirm.

## Architecture [proposed, skeleton done]
Modular monolith, one Django project, one PostgreSQL. SPA same-origin with API (Vite proxy in dev). Session auth + CSRF.
Domains: accounts (users/roles) · transport (operators, stops, routes, departures, fares, policies, capacity) · planning
(pure search/connection logic over transport data) · bookings (reservations, bookings, legs, snapshots) · payments
(attempts, refunds, simulator) · disruptions (events, replacement offers) · notifications · core (health, audit).
Background worker: a Django management command polling a PostgreSQL `jobs` table with `SELECT … FOR UPDATE SKIP LOCKED`
(reservation expiry, disruption processing); jobs are durable and idempotent so restart is safe.
Concurrency: row lock on departure capacity rows inside a transaction; idempotency keys with unique constraints.

## State machines (to be finalised in Stage 3 before coding)
- Reservation: held → consumed | expired | released
- Booking: pending_payment → confirmed → cancelled (| failed)
- Payment attempt: created → succeeded | failed (terminal; one succeeded per booking, enforced by constraint)
- Refund: pending → completed (unique per booking+reason)

## Initial data model (entities)
User, Operator, OperatorMembership, Stop (hub flag), TransferLink (stop↔stop walk time), Route, RouteStop,
Departure (service date, status, delay, capacity), DepartureStop (arr/dep UTC), Fare, CancellationPolicy,
AccessibilityAttrs, TaxiOffer, SearchResult (ephemeral, signed offer), Reservation, Booking, BookingLeg (snapshots of
price/times/policy), PaymentAttempt, Refund, DisruptionEvent, ReplacementOffer, Notification, AuditRecord, Job.
Money: `DecimalField(max_digits=10, decimal_places=2)` / integer cents. All timestamps `timestamptz`.

## Acceptance criteria — Stage 1
Frontend opens; health endpoint responds; PostgreSQL connected; migrations run; no committed secrets; setup reproducible.
(See status below.) Later stages: see brief §11/§13 and `backlog.md`.

## Key risks
1. Concurrency correctness (oversell, double charge) → PostgreSQL-backed tests with real threads.
2. Multi-leg planning complexity/time zones → keep planner pure, test midnight crossing early.
3. Scope creep → strict stage gates.
4. Docker path unverified locally (no Docker) → document; verify on a Docker machine.
5. Custom User model fixed at first migration (done up front).

## Stage 1 status
| Item | Status |
|---|---|
| Frontend opens (Vite) | done, verified in Chromium incl. mobile viewport |
| Backend health + PostgreSQL 17.10 | done, `/api/health/` verified through frontend proxy |
| Migrations | done (`accounts.0001`); `makemigrations --check` clean |
| No committed secrets | `.env` git-ignored; `.env.example` holds placeholders only |
| Backend tests | 3 pass on PostgreSQL; Playwright smoke 2 pass |
| Docker Compose | **written, NOT run** — Docker is not installed on this machine |

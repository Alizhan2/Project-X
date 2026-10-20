# Backlog
- [x] Stage 0 plan · [x] Stage 1 foundation
- [x] Stage 2 demo dataset (resettable, relative dates) + direct bus search API + results UI (20 backend tests, 5 e2e)
- [x] Stage 3 auth, reservations, simulated payments, confirmation, My Journeys, idempotency, concurrency tests (55 backend tests, 7 e2e)
- [x] Stage 4 trains/taxis/transfers, planner ≤3 legs, comparison, coordinated reservations (74 backend tests, 8 e2e)
- [x] Stage 5 cancellation/refunds, operator UI, delays/cancellations, notifications polling
- [x] Stage 6 disruption recovery, replacement offers, demo scenarios (see demo-script.md)
- [~] Stage 7 hardening: done except full Docker Compose execution and manual a11y (see release-checklist.md, limitations.md)
- [x] CI executed on a GitHub runner at ac46440; all five jobs passed.
- [ ] Verify full `docker compose up` and read-only runtime on a Docker host (local development continues without Docker).
- [ ] Post-MVP: commercial discovery (separate phase)

## Known gaps / to polish
- [x] Search page setState-in-effect warning removed during search-convenience work.
- [x] Booking cancellation and refunds implemented in Stage 5.
- [x] Password recovery, optional email verification and refreshed responsive UI.
- [ ] Configure hosted SMTP and verify actual inbox delivery.

## Production preparation (this milestone)
- [x] Config validation, security headers, rate limits, structured logs, probes, metrics, integrity tooling, DB roles, locked migrations, hash-locked deps, CI/CD files, runbook/docs
- [ ] Choose hosting + domain (decision) · build image and run compose on a host with Docker
- [x] Run pg_dump backup + `verify-restore.sh` locally without Docker; CI already ran at ac46440
- [ ] Decide registration policy; assign alert/backup owners; approve any external monitoring account
- Commercial backlog: docs/commercial-readiness.md

## Search convenience
- [x] Account-owned saved directions and repeat search from previous bookings.
- [x] Planner-level transport, transfer-count and connection-time filters.
- [x] Compare up to three journeys with factual price/time/transfer differences.
- Details and test evidence: search-convenience.md.

## Travel companion
- [x] Next confirmed/in-progress journey with current timetable and disruption state.
- [x] Private calendar download with one event per active leg.
- [x] PDF journey plan with current times and clear simulation/disruption labels.
- Details: travel-companion.md.

## Arrival deadline
- [x] Arrive-by search with latest departure ranking, multimodal connections and taxi opening hours.
- [x] Deadline retained through selection/comparison and checked again before reserving seats.
- Details: arrive-by.md.

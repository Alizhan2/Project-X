# Backlog
- [x] Stage 0 plan · [x] Stage 1 foundation
- [x] Stage 2 demo dataset (resettable, relative dates) + direct bus search API + results UI (20 backend tests, 5 e2e)
- [x] Stage 3 auth, reservations, simulated payments, confirmation, My Journeys, idempotency, concurrency tests (55 backend tests, 7 e2e)
- [x] Stage 4 trains/taxis/transfers, planner ≤3 legs, comparison, coordinated reservations (74 backend tests, 8 e2e)
- [x] Stage 5 cancellation/refunds, operator UI, delays/cancellations, notifications polling
- [x] Stage 6 disruption recovery, replacement offers, demo scenarios (see demo-script.md)
- [~] Stage 7 hardening: done except Docker/CI execution and manual a11y (see release-checklist.md, limitations.md)
- [ ] Verify `docker compose up` and the CI workflow on a machine/runner that has them (blocked here)
- [ ] Post-MVP: commercial discovery (separate phase)

## Known gaps / to polish
- Search page lint warning (setState in effect)
- Booking cancellation of confirmed bookings + refunds: Stage 5 (rules in business-rules.md)

## Production preparation (this milestone)
- [x] Config validation, security headers, rate limits, structured logs, probes, metrics, integrity tooling, DB roles, locked migrations, hash-locked deps, CI/CD files, runbook/docs
- [ ] Choose hosting + domain (decision) · build image and run compose on a host with Docker · run pg_dump backup + `verify-restore.sh` once · run CI on a real runner
- [ ] Decide registration policy; assign alert/backup owners; approve any external monitoring account
- Commercial backlog: docs/commercial-readiness.md

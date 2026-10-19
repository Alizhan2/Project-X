# Decision log (newest last)
| # | Decision | Why |
|---|---|---|
| 1 | Modular monolith, one DB, same-origin SPA+API | Simplest thing that meets the brief; no broker/Redis until needed |
| 2 | Custom `User` with `role` before first migration | Changing the user model later is painful |
| 3 | Whole-service capacity as a counter on `Departure` + CHECK constraint | Easy to lock and reason about; DB guarantees no oversell even if code is wrong (mutation-tested) |
| 4 | Stop times as minute offsets from `departs_at` | Midnight crossing needs no special case; delays shift everything |
| 5 | Search = offers; booking = snapshot | Price/policy edits cannot rewrite purchases |
| 6 | Idempotency via `Idempotency-Key` header + unique (user,key) / (booking,key) | Safe retries/double clicks for checkout and payment |
| 7 | Partial unique index: one succeeded payment per booking | Double-charge protection independent of app logic |
| 8 | Jobs table with `FOR UPDATE SKIP LOCKED` + stale-lock reclaim + periodic sweep | Durable, restart-safe expiry without extra infrastructure |
| 9 | Failed payment keeps the hold until expiry | Lets the passenger retry without losing places |
| 10 | Other users' bookings return 404 (not 403) | Avoids leaking which references exist |
| 11 | CSRF enforced on login/register too (custom auth class) | Prevents login CSRF; SPA re-reads the rotated cookie each request |
| 12 | Demo seed is dev-only and wipes dependents (bookings, jobs) before transport data | Reset must work after real use; accounts preserved |
| 13 | Planner = bounded in-memory DFS over a snapshot of the network, ≤3 legs, no repeated stops, wait ≤180 min | Simple, testable, exact for the demo region; documented as not exhaustive |
| 14 | Transfers between different stops need an explicit `TransferLink`; same-stop change = 5 min | Brief requires explicit movement between locations |
| 15 | "Transfer buffer" = spare minutes beyond required change time, only for connections into bus/train | A taxi leaves when you are ready, so there is nothing to miss; never presented as reliability |
| 16 | Taxi priced per vehicle, no capacity pool, simulated availability window | Matches "simulated taxi availability"; keeps whole-service capacity model for bus/train only |
| 17 | Checkout recomputes every leg + connection from the DB under departure locks | Client data is never trusted; delays after search surface as `connection_missed` |
| 18 | Replacement offers are non-reserving, fingerprinted, expire after 30 min, re-validated on acceptance | Avoids holding places for people who never answer; honest availability warning |
| 19 | Acceptance = one transaction; failed simulated top-up recorded separately and changes nothing else | Existing booking, places and payments stay coherent on any failure |
| 20 | Completed legs derived from live times, not stored | One source of truth; retained legs are never modified |
| 21 | Payment `purpose` (initial/replacement); one-succeeded-per-booking index applies to `initial` only | Allows a top-up without weakening double-charge protection |
| 22 | e2e demo day computed in Europe/Berlin | The seed uses the demo timezone; the machine clock can be a day ahead |
| 23 | One settings module with validated environment profiles (DOEDU_ENV / DOEDU_LAUNCH_MODE) instead of four files | One place to audit; invalid production config refuses to start; fewer drifting copies |
| 24 | App server serves API + admin + static + SPA (WhiteNoise); no separate nginx container | Verifiable locally, fewer moving parts at demo scale; a CDN/proxy can be added without code changes |
| 25 | Hash-locked dependencies (pip-compile) | Reproducible, tamper-evident installs |
| 26 | Three DB roles (admin, migrator, app) + append-only audit/payments for the app role | A compromised app cannot alter schema or erase financial/audit history |
| 27 | Migrations run once per release via `safe_migrate` (advisory lock); web/worker never migrate | No replica races; readiness blocks traffic on a mismatched schema |
| 28 | Liveness never touches the DB; readiness does; worker state informational | A DB outage must not restart healthy app servers |
| 29 | Rate limits in the shared DB cache + per-account lockout; documented as NOT DoS protection | Works across processes with no new infrastructure; ingress limits still required |
| 30 | `commercial` launch mode refuses to start; simulation flag gates payment endpoints | Infrastructure readiness must not imply a real sale is possible |
| 31 | `sync_demo_schedule` additive command (and worker auto-sync) for the hosted demo instead of allowing the destructive seed in production | Keeps the demo alive without a wipe path; creates no accounts |
| 32 | Capacity drift is repaired only by an audited, dry-run-first command | Counters are a lock target; blind edits would hide bugs |

# Arrive-by search

The search form offers **Depart after** (existing default) and **Arrive by**. In arrival mode the date/time is the latest acceptable arrival, in Europe/Berlin. Results default to latest departure first. Transport, transfer-count, connection-time and price/duration/buffer sorting remain available.

The URL stores `time_mode=arrival`, date and time. Reload/history preserve the mode; changing the submitted mode resets sorting to its default and clears comparison. Saved directions and repeat-journey links still open a fresh departure search.

## Planner
- API: provide exactly one of `depart_after` or `arrive_by`. A past arrival deadline is rejected. Missing/invalid dates are field errors.
- Naive arrival times use Europe/Berlin. Nonexistent or ambiguous clock-change times require another time (or an explicit UTC offset for ambiguity). Offset-bearing API requests represent absolute instants.
- The reverse planner explores journeys with a first departure within the 24 hours before the deadline, strictly after now. Arrival exactly at the deadline is allowed. Journeys can start on the previous day.
- Existing limits remain: at most three legs, 14-hour journey duration, connection waiting limits and a maximum of 40 results. Search is bounded, not exhaustive: at intermediate reverse edges only two latest service departures are explored per route/origin-stop.
- Current delays, cancellations, capacity, directed transfer links, required walking/transfer times and taxi opening hours are respected. Direct taxis are timed toward the deadline, including pickups before closing on the previous day when necessary.
- Candidate journeys are replayed forward in memory using the same immediate on-demand taxi rule as checkout. Filters and the deadline apply before final sorting/result truncation.
- The existing forward/recovery planner is unchanged apart from the additional available `latest_departure` sort.

## Selection and booking
The arrival deadline is carried through result links, comparison links, journey details and the booking form. `/api/itinerary/` rechecks it against current timings. Checkout accepts optional `arrive_by` and checks it while service rows are locked, before reserving any capacity. A new delay that misses the deadline returns `409 arrival_deadline_missed`. Existing checkout retries remain idempotent.

This is a planning constraint, not a punctuality guarantee or a new refund promise. It is checked when reserving and is not stored as a contractual booking deadline. Later disruption/recovery behaviour follows the existing rules. Payment does not introduce a new arrival-time guarantee.

## Verification
- All 218 PostgreSQL tests passed, including 13 new tests covering exact deadlines, latest departure ranking, previous-day departures, taxi hours/party size, first/intermediate taxis, round-trip itinerary revalidation, filters before the result cap, delays/cancellations/capacity, invalid/past/DST times, explicit offsets and checkout rejection/idempotency.
- Frontend build and five unit tests passed; lint retains its five existing warnings. All 23 existing browser regression scenarios passed on a disposable PostgreSQL/gunicorn stack.
- Manual browser flow verified arrival search, comparison links, reload persistence, login continuation and the deadline in the actual reservation request. The created synthetic reservation was cancelled afterward.
- Desktop/mobile form and result-card screenshots were visually inspected; an axe WCAG A/AA scan of arrival-mode results found no violations. Axe injection used a separate test context with CSP bypass, without changing application policy.
- A keyboard regression exposed sort-control unmounting during refresh; the control now stays mounted so native keyboard selection retains focus.
- No data migration, reseed, external service or new dependency is needed.

# Saved directions, repeat search, filters and comparison
Implemented 2026-10-20. Transport, payments and tickets remain simulated.

## Saved directions and repeating a journey
- Signed-in users can save a searched origin/destination under **Saved directions**, revisit it from the search page and remove it. These are account-owned PostgreSQL records, available across sessions/devices. Anonymous users are invited to sign in.
- A direction stores stop references only, never a quoted price or a reserved departure. Saving it twice is idempotent. Reverse directions are distinct. There is a limit of 50 per account, serialized with a user-row lock; uniqueness and distinct-stop constraints also exist in the database.
- `GET/POST /api/favorites/` and `DELETE /api/favorites/<id>/` require authentication; writes require session CSRF. Another user's ID returns 404 on deletion and never appears in the list.
- **Repeat journey** in My journeys opens a new search with the booking's endpoint codes and passenger count, starting on today's date in Europe/Berlin. The passenger can choose a different date/time before booking. No old fare, passenger identity, payment, hold or booking status is copied. Saved directions start a one-passenger search.
- Additive migration: `accounts.0003_favoriteroute`; run `safe_migrate` in deployments. Resetting the synthetic transport dataset removes saved references to deleted stops. The existing local database was migrated, not reseeded.

## Search filters
- `modes`: comma-separated allowed modes, default `bus,train,taxi`. Every leg must use an allowed mode. The UI keeps at least one mode selected; an empty or invalid API value returns 400.
- `max_transfers`: `any`, `0`, `1` or `2`. The planner currently supports at most three legs; `any` means at most two transfers.
- `max_connection_minutes`: optional integer 5–180, measured from a leg's arrival to the next leg's departure, including any walking time. This is distinct from the spare connection buffer shown on results. UI presets: 15, 30, 60, 120, 180 minutes.
- Filters are applied inside the bounded planner, before sorting and the 40-result cap. Safety limits and the existing recovery planner's defaults are unchanged. A regression test places a cheaper excluded bus ahead of a valid train with a one-result cap, and confirms the train still appears.
- Search/filter state is in the URL and survives reload/back/forward. Search form drafts are retained while changing filters; changing the actual search endpoints/date restores the corresponding form values. URL-backed controls use synchronous router updates so checkboxes do not briefly revert while navigation is scheduled.

## Comparing journeys
Select **Compare** on up to three result cards. The first selected journey is the reference; later options explain differences relative to it. Removing the reference makes the next selection the reference. Changing any search parameter clears comparison, including navigating back to an older search; stale selected offers are not restored.

The responsive comparison shows total party price, departure/arrival dates and times, duration, transport modes, transfers, the tightest spare connection buffer and cancellation-policy labels. Facts are derived from the returned itineraries; no AI service or subjective ranking is used. Prices are compared in integer cents using BigInt. Arrival comparisons use absolute instants, so midnight and timezone offsets work. Prices with different currency or party size are not directly compared. A direct journey has no connection buffer; a larger buffer is never presented as a punctuality guarantee. Offer prices/availability are revalidated on the normal details/booking path.

## Verification
- Full PostgreSQL backend suite: **197 passed** (including account isolation, duplicate saves, cap, CSRF and planner-filter tests).
- `npm test`: **5 passed**, covering exact cent differences, duration versus arrival, midnight, direct journeys and mismatched currencies/party sizes. Added to frontend CI.
- Existing Playwright regression suite: **23 passed** on the final build. Tests use a fresh disposable database and a built SPA/gunicorn stack, not the user's bookings.
- The regression run exposed an existing replacement-options message bug: refreshing options cleared the explanation after rejecting a stale offer. The refresh now preserves that explanation; the stale-offer recovery scenario passes.
- Browser walkthrough: save/reload/remove favourite, repeat from My journeys, three-selection cap, comparison reset on filters and history navigation, transport persistence after reload; desktop and 390px comparison screenshots inspected.
- Build and lint checked; five pre-existing lint warnings remain (the previous Search set-state-in-effect warning was removed). OpenAPI regenerated with schema validation.
- Hosted/container deployment and live commercial integrations remain outside this change.

# Business rules and state machines
Status legend: **[Stage N]** implemented in that stage. Refund rules and recovery are implemented (Stages 5–6); the tables below describe the code.

## Core principles
1. A search result is an *offer*; nothing is held. A booking exists only after checkout creates reservations.
2. Booking status and payment status are separate state machines.
3. Capacity: `Departure.places_taken` = held + consumed places. Changes only inside a transaction holding a row lock on the
   departure (`SELECT … FOR UPDATE`), locks always acquired in ascending departure id. DB CHECK `places_taken <= capacity`.
4. No transaction is held open across user interaction. Checkout (reserve) and payment are separate short transactions.
5. Every mutating request that can be retried carries an idempotency key; repeats return the original outcome.
6. Reservation lifetime: `RESERVATION_MINUTES` (default 10). Expiry is enforced three ways: lazily on access/payment,
   by the worker's durable `expire_booking` job, and by a periodic sweep (restart safe).

## Booking — [Stage 3]
| From | Event | To | Side effects |
|---|---|---|---|
| (none) | checkout accepted | `pending_payment` | places held, expires_at set, expiry job queued |
| pending_payment | payment succeeded | `confirmed` | reservations consumed |
| pending_payment | passenger abandons | `cancelled` | reservations released, places returned |
| pending_payment | now ≥ expires_at | `expired` | reservations expired, places returned |
| confirmed | passenger cancels | `cancelled` | places returned; refund per policy (**[planned]** Stage 5) |
| confirmed | operator cancels service | affected → recovery flow (**[planned]** Stage 6) |
Terminal: cancelled, expired. Any other transition is rejected with 409.

## Reservation (one per booking leg) — [Stage 3]
held → consumed (payment ok) · held → released (abandon / failed checkout) · held → expired (timeout) ·
consumed → released (confirmed booking cancelled). Terminal: released, expired.

## Payment attempt — [Stage 3]
created → succeeded | failed (both terminal). Unique key per attempt. At most one `succeeded` per booking (partial unique
index). A failed attempt leaves the booking `pending_payment` so the passenger may retry before expiry. Paying a booking that is
already confirmed with a different key is rejected (409), never charged twice. Repeating the same key returns the first result.
The simulator accepts `outcome=success|failure`; no card data is ever collected.

## Refund — [Stage 5]
pending → completed. Unique per (booking, reason) so repeated cancellation cannot create a second refund.
Policy (snapshotted per leg at purchase): full refund if cancelled ≥ `full_refund_hours_before` before that leg departs;
`partial_refund_percent` if ≥ `partial_refund_hours_before`; otherwise 0. Departed legs refund 0. Operator-cancelled legs refund
100%. Refund = sum over legs, rounded half-up to cents. (Default policy values are an assumption awaiting product confirmation.)

## Disruption recovery — [Stage 6]
**Leg classes** (derived from live times, nothing extra stored): a booked leg is *completed* once its live arrival is in the
past; *affected* = the first booked leg that cannot be used (service cancelled, connection no longer possible, or taxi pickup
outside service hours) **and every booked leg after it**; legs before it are *retained*. Retained legs are never touched, even if
completed. Affected legs become `replaced` when an offer is accepted (their rows, prices and policies are kept as history).
A disruption is **informational** when every connection still holds (passenger gets a "delayed" notice, no action); it is
**actionable** when `assess()` reports `broken`.

**Offers are non-reserving.** They show an availability warning, expire after `REPLACEMENT_OFFER_MINUTES` (30) and are
re-validated (schedule, price, capacity, connections, relevance) on acceptance.

Replacement offer: `proposed → accepted | declined | expired | invalidated`; only `proposed` can be accepted.
| From | Event | To |
|---|---|---|
| proposed | passenger accepts, all checks pass | accepted |
| proposed | passenger declines | declined |
| proposed | now ≥ expires_at | expired |
| proposed | disruption cleared / changed, price or times changed, capacity gone, another offer accepted | invalidated |
accepted is idempotent (repeating returns the same result). Offers are recomputed whenever a service changes again; unchanged
alternatives keep their offer, others are invalidated and new ones proposed (unique live fingerprint per booking).

**Price difference** = price of replacement legs − amount paid for the replaced legs. `> 0` → simulated top-up payment
(`purpose=replacement`, one attempt per request key); `< 0` → simulated refund (`key=replacement:<offer id>`, unique); `= 0` → none.
A failed simulated top-up records a failed attempt and changes nothing else. `Booking.total_amount` becomes net paid.

**Acceptance is one short transaction**: lock booking → lock offer → lock departures (new ∪ replaced, ascending id) → revalidate →
acquire new places → mark old legs `replaced` and release their places → settle money → mark offer accepted. Any failure rolls
the whole thing back, so the original booking, places and payments stay exactly as they were.

**No alternative**: the passenger is told so, and cancellation is offered with a full refund of unused legs (existing
`cancel` rules, `disrupted = true`).

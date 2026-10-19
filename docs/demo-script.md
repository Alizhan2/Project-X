# Demonstration script (everything is SYNTHETIC and simulated)

Setup once: follow README, then `cd backend && python manage.py seed_demo` (dev only; re-run to reset all demo data).
Run three things: backend, frontend, and (optional but recommended) `python manage.py run_worker`.
Accounts (password `doedu-demo-2026`, or `DEMO_USER_PASSWORD`): passengers `demo.passenger@`, `demo.pay@`, `demo.refund@`,
`demo.noalt@doedu.test`; operators `ops.valley@` (buses VC*), `ops.greenline@` (GL*), `ops.rail@` (trains DR*); admin `admin@doedu.test`
(Django Admin at http://127.0.0.1:8000/admin/). **Demo day = seed reference date + 1** (printed by the seed command). Use two browser
windows (or one normal + one private) for passenger and operator. Each recovery scenario is consumed once per seed; re-seed to repeat.

## 0. Search and compare (1 min, no login)
Search Northgate Bus Station → Portmouth Marina (taxi rank) on the demo day, 11:00. See Bus → Train → Taxi itineraries; try sorting by
price / duration / **largest transfer buffer**. Note the buffer wording: spare minutes, not a punctuality prediction. Taxi is priced per vehicle.

## 1. Book (2 min)
Pick a result → traveller details (register) → reserve (countdown) → payment simulator: *Simulate failed payment* (hold stays), then success.

## 2. Recovery, equal price — `demo.passenger@`
Operator `ops.valley@`: Operator → VC1 14:00 on the demo day → set delay **45** → *Preview consequences* (shows the journey would be broken,
no personal data) → confirm. Passenger: Notifications → open booking: disruption banner, *Kept as booked* (bus), *Cannot be used* (train + taxi),
up to 3 options with arrival, price difference (here none), expiry, availability warning. Choose an option → confirm.
**Invalidated offer variant:** before confirming, have `ops.rail@` cancel the first offered train; the passenger's confirm is refused
("options were refreshed") and a fresh option is accepted.

## 3. Recovery, extra simulated payment — `demo.pay@`
`ops.valley@`: **cancel** VC1 12:00. Passenger: pick the "Extra to pay EUR 0.10" option → *Simulate failed payment* (nothing changes, booking
and places intact) → *Pay … and confirm*. Booking now shows "Replacement top-up: succeeded" and the original leg under history.

## 4. Recovery, cheaper replacement — `demo.refund@`
`ops.greenline@`: **cancel** GL1 12:30. Passenger: pick "You get back EUR 0.10" → confirm; a simulated refund "Cheaper replacement journey" appears.

## 5. No alternative — `demo.noalt@`
`ops.rail@`: delay DR1 18:10 by **60** (train → last Lakeside bus VC2 19:30 can no longer be caught; nothing else arrives within the
replacement window). Passenger: "No replacement found" + cancellation with a **full** refund of unused legs.

## 6. Cancellation rules (any confirmed booking)
*Cancel this journey…* shows a per-leg refund table (Standard policy: ≥24 h full, ≥2 h 50 %, else 0; taxi free until 1 h before) before you confirm.

## 7. Restart safety
Create an unpaid reservation, stop the worker, wait past `RESERVATION_MINUTES`, start `run_worker --once`: the places are released
(also happens lazily when the booking is opened or paid).

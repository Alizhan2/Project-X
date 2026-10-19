# Demonstration data (SYNTHETIC)
Loaded by `python manage.py seed_demo [--reference-date YYYY-MM-DD]` (or env `DEMO_REFERENCE_DATE`). Dev only: refuses to run
unless `DJANGO_DEBUG=true` (or `DOEDU_ALLOW_SEED=1`). It deletes and rebuilds all transport data; for a given reference date the
result is identical every time (tested). Timetables run for 7 days from the reference date; **demo day = reference + 1**.

Everything is invented: the region "Doedu Valley", place names, operators, prices (EUR 1.50 + per-minute rate) and timetables.

| Scenario (demo day) | Where |
|---|---|
| One place left | GL1 Northgate→Riverton Express, 07:30 (capacity 16, 15 taken) |
| Cancelled service | VC1 Northgate→Riverton 10:00 |
| Sold out | GL2 Riverton→Portmouth 11:30 |
| Delay (+45 min) | VC1 Northgate→Riverton 08:00 (breaks onward connections once trains exist, Stage 4) |
| Crosses midnight | GL3 night bus 23:30 → 00:40 next day |
| Unknown accessibility | Lakeside stop and VC2 vehicle (unknown ≠ no) |
| Not accessible | Riverton Station, Oakbridge Crossing, GL2 vehicle |

Operators: Valley Coaches (VC*, buses), Greenline Express (GL*, buses), Doedu Rail (DR1/DR1R trains), Valley Cabs (simulated taxis). Seeded "places taken" are plain counters, not backed by booking rows.

## Multimodal network (Stage 4)
- Trains: DR1 Northgate Central → Riverton Station → Portmouth Harbour (hourly 06:10–23:10 from Northgate; leaves Riverton at hh:45),
  DR1R in reverse (hourly :30). The 23:10 train **crosses midnight** (arrives Portmouth 00:30).
- Explicit walking links (minutes): NG bus↔rail 8, RV bus↔rail 10, PM bus↔rail 7. Changing at the same stop needs 5 min
  (`MIN_SAME_STOP_TRANSFER_MIN`). Pairs without a link cannot be connected.
- Taxis (simulated, priced **per vehicle**, max 4 passengers, pickups 05:00–23:59): PM-RAIL↔PM-MARINA €14 (8 min wait, 12 min ride),
  NG-BUS↔NG-RAIL €6.50, LK-BUS→RV-RAIL €38 (one-way on purpose: no taxi back to Lakeside).
- **Bus → Train → Taxi**: Northgate Bus Station → Portmouth Marina = VC1 → walk → DR1 → taxi.
- **Delay breaks a connection**: VC1 08:00 is +45 min, arrives Riverton 09:40, walk 10 ⇒ ready 09:50, misses the 09:45 train
  (next is 10:45). Without the delay there would be 40 min to spare.

## Accounts and pre-booked journeys (Stage 6)
`seed_demo` also creates SYNTHETIC accounts (password `DEMO_USER_PASSWORD`, default `doedu-demo-2026`; dev only) and four confirmed, paid bookings
made through the real checkout/payment services. Walk-through: `docs/demo-script.md`.
| Account | Booking (demo day) | Operator action that triggers the scenario |
|---|---|---|
| demo.passenger@ | VC1 14:00 → DR1 (RV 15:45) → taxi | ops.valley: delay VC1 14:00 by ≥ 45 min → replacement, equal price |
| demo.pay@ | VC1 12:00 NG→RV (7.00) | ops.valley: cancel VC1 12:00 → replacement GL1 costs +0.10 (simulated top-up) |
| demo.refund@ | GL1 12:30 NG→RV (7.10) | ops.greenline: cancel GL1 12:30 → VC1 replacement −0.10 (simulated refund) |
| demo.noalt@ | DR1 18:10 → VC2 19:30 (last Lakeside bus) | ops.rail: delay DR1 18:10 by 60 → no alternative |
Operators: ops.valley@, ops.greenline@, ops.rail@; admin: admin@ (all `@doedu.test`). Passwords are not secrets: the accounts exist only in dev data.

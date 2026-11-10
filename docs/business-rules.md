# Business rules and state machines

Current implementation rules for the November 2026 requirements alignment. All transport, charges and refunds remain simulated. This change addresses the three requested development areas; it is not a claim that every requirement in the review PDFs is complete.

## Search, transfer time and accessibility

- Search returns offers, not bookings. A journey has at most three transport legs. The bounded planner is not exhaustive.
- Shared `planning/transfers.py` rules are used by forward search, arrive-by search, checkout and disruption assessment.
- Connection margin = next departure − forecast arrival − walking time − boarding buffer, using timezone-aware full timestamps. Midnight crossings do not reset the calculation.
- A negative margin is infeasible and cannot be selected. Zero to under five minutes is `at_risk`; at least five minutes is `feasible`. These are schedule calculations, not punctuality guarantees.
- Same-stop connections have zero walking and the existing five-minute boarding minimum. Directed links between different stops store walking and boarding minutes separately. The additive migration preserves existing walking values, adds a zero boarding buffer, and marks path accessibility unknown until explicitly verified.
- Connections into on-demand taxis report `on_demand`, with no claim of a fixed-service safety margin. Taxi pickup waiting and operating hours still apply.
- `wheelchair_required=true` requires confirmed accessible vehicles, boarding/alighting stops and every walking transfer path. Unknown is excluded. The preference is rechecked at checkout, payment confirmation and recovery acceptance.
- Administrators maintain transfer walking, boarding and accessibility metadata in Django Admin. Unknown data is not silently promoted to accessible.

## Reservation and capacity

- Default hold lifetime is five minutes (`RESERVATION_MINUTES=5`), starting when checkout creates the booking. Previously issued expiry timestamps are not rewritten.
- Expiry runs lazily on access/payment and through durable background jobs/sweeps. It releases capacity even while a payment outcome is unresolved.
- Capacity writes use short transactions and departure row locks in ascending primary-key order. Where applicable lock booking → offer/attempt → departures. No transaction waits for passenger input or a provider response.
- The database capacity constraint remains a second line of defence against overselling.

## Payment attempts

- An attempt with its idempotency key, purpose and amount is persisted before recording a simulated charge outcome.
- Statuses: `created` → `pending` (outcome unknown) → `succeeded` or `failed`; created attempts may resolve directly. Terminal outcomes are immutable.
- Repeating an ordinary payment request returns its existing result. Explicit reconciliation resolves the same pending attempt and key. A new key is refused while a created/pending attempt exists.
- Reusing an attempt key for another offer or payment purpose is rejected.
- There is at most one successful initial charge per booking. Replacement charges are separate full-price payments tied to their offers.
- Success is followed by booking/replacement commit revalidation. An expired hold, invalidated offer or definitive commit failure triggers a full compensation refund of that new charge, independent of fare policy. Repeated reconciliation must neither confirm twice nor refund twice.
- No payment details, wallet balance or real provider credentials are collected.

## Refunds

- Refund operations have stable keys and visible `requested`, `pending`, `completed` (refunded) and `failed` states.
- Background work completes ordinary simulator refunds; failed outcomes remain visible and can be retried as the same operation. A completed operation is terminal.
- Completed and reserved requested/pending refunds count against captured money. Retrying a failure rechecks the cap. Financial histories are aggregated separately so multiple payments/refunds do not multiply one another through a database join.
- Fare conditions come from the purchase snapshot. A delay or missed connection does not automatically grant a full refund of every unused leg. Operator cancellation grants the eligible unused cancelled leg a full refund; other legs retain their snapshot conditions.
- A shared per-leg quote is reused for cancellation and replacement refunds. Already reserved/refunded leg value cannot be paid twice.
- Cancelling a trip and completing its refund are separate events; the UI must not say money was returned while the refund is only requested/pending/failed.

## Recovery and replacement settlement

- Recovery preferences include a reachable current stop, earliest departure, latest acceptable arrival, nonnegative whole-currency-unit payment-now limit and optional strict accessibility.
- The passenger cannot teleport to an unrelated stop. Search and acceptance validate location against the retained/affected journey and explicit transfer links. Used legs are protected from replacement.
- Recovery preferences are persisted on the booking. Background refreshes and ordinary reloads preserve them, including zero budgets and searches with no offers. Advancing the clock alone does not replace an otherwise unchanged offer.
- Deadline and payment-now limit are hard constraints. A zero budget is valid. They are never silently relaxed when no option matches.
- Alternatives rank by final arrival time, full payment required now and deterministic service identifiers. At most three are shown.
- Offers snapshot their constraints and expire. Browsing an offer does not reserve capacity; acceptance checks current times, accessibility, price, eligibility and capacity again.
- Full new-leg price is payable now. Eligible old-leg refunds are requested separately after successful replacement. Conditional net extra cost = new charge − eligible old refund, labelled conditional until the refund completes.
- Example: new price 1,800 ₸ and eligible old refund 400 ₸ mean pay 1,800 ₸ now and request 400 ₸ separately. A 1,500 ₸ payment-now limit excludes the offer. Conditional net extra cost is 1,400 ₸.
- Failed or pending payment keeps the original booking intact. New places and leg replacement commit together after successful payment revalidation. Definitive failure after a successful charge requests full charge compensation.
- No-match screens explain the constraints and show the actual cancellation quote, without promising an unconditional full refund.

## Markets and existing data

- `/` is Kazakhstan planning: real city names, KZT and `Asia/Almaty`. Without a supplier it supports private plans and shared search parameters, not fabricated inventory.
- `/demo` is the fictional transport network, with EUR, `Europe/Berlin` and simulation labels. `/kazakhstan` remains compatible; historic root links containing fictional stop codes redirect to `/demo` preserving parameters.
- Existing accounts, references, amounts, currencies, dates and policy snapshots are retained. This is not an exchange-rate conversion or reseed of historical data.
- New database fields are additive. Historic rows without newer payment/offer linkage remain readable; their interpretation must not invent provider transactions.

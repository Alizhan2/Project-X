# Doedu Kazakhstan demonstration

The current work implements the owner's clarified scope: **a working Kazakhstan demonstration without external APIs**. The home page `/` (also `/kazakhstan`) searches generated bus/train services, reserves places and uses the existing simulated payment, refund and replacement lifecycle. Private plans and share links remain available. A saved plan alone does not reserve a place.

The earlier 90-city increment passed combined local verification and all five [CI jobs at `44cdde6`](https://github.com/Alizhan2/Project-X/actions/runs/43055303104). The new search-preferences increment adds arrival deadlines, accessibility/price filters and search restoration. Its combined local checks and local migration-preservation check passed; current-revision CI remains pending. Public deployment is still awaiting the owner's manual Render update. The last observed public release remains `e2e4b5a3c649`, which predates Kazakhstan booking; consult [HANDOFF](HANDOFF.md) and the [deployment record](render-free-test.md) before describing a public release as updated.

## Geography and language

- The directory contains **all 90 city settlements in KATO NK RK 11-2025, updated 4 November 2026**, including cities that are not regional centres. It does not include every village or settlement type.
- Source: the Bureau of National Statistics [KATO classifier](https://stat.gov.kz/ru/classifiers/statistical/21/) and its [4 November workbook](https://stat.gov.kz/upload/iblock/3af/er0488xunb664axbufnw46sagt10aqsm/%D0%9A%D0%90%D0%A2%D0%9E_04.11.2026.xlsx). Source date, retrieval date and checksum are recorded in `catalog.py` and exposed as catalogue metadata.
- Russian and Kazakh source names are preserved. English labels are editorial Latin transliterations. City lookup matches the catalogue's EN/RU/KK city names, region names and recorded aliases.
- Existing first-20 `kz-*` identifiers remain stable so saved plans and shared links continue to resolve. KATO geography identifiers are separate from any future supplier station identifiers.

## Generated transport and booking

Simulation-enabled launches use the internal `kazakhstan_demo` provider. Catalogue and search responses explicitly report that they are simulated; no supplier request is made.

`GET /api/kazakhstan/catalog/` returns cities, geography provenance, KZT, `Asia/Almaty`, simulation/provider status and whether demo booking is enabled. `GET /api/kazakhstan/search/` validates different cities, a future date within one year, local time, 1–9 passengers and bus/train modes. It returns generated direct itineraries and accepts these additional search preferences:

- `time_mode=departure` (default) treats the date/time as the earliest departure and searches the next 24 hours. `time_mode=arrival` treats them as an inclusive arrival deadline and searches departures in the preceding 24 hours, clipped to the current time. Previous-local-day departures may qualify. Departures that have already left and journeys arriving after the deadline are excluded; current delays are included.
- Arrival mode defaults to `latest_departure` sorting. Both modes support `departure`, `latest_departure`, `price` and `duration` sorting.
- `wheelchair_required=true` requires explicitly accessible vehicles and both stops. Unknown or false accessibility is excluded using the existing planner accessibility rule. This preference follows the selected journey through comparison and checkout, where current accessibility is checked again. Accessibility data remains illustrative.
- Optional `max_price` is an inclusive maximum **total KZT price for the entire passenger party**, represented as a nonnegative decimal with up to ten integer digits and two decimal places. Omit it for no price filter; zero is a real zero-price limit. This is a search filter, not a locked spending cap. Existing price revalidation can show a changed fare before a passenger chooses whether to proceed.

Generation is limited to the selected origin/destination pair and the local days needed for that search window. The pair gets a two-day example timetable, avoiding a prebuilt complete national route mesh. Repeating a search reuses existing rows and preserves current operator fares, delays, cancellations, capacity and booked places. Route/day generation markers prevent moved or deleted departure slots from being recreated; purchase snapshots remain unchanged.

**Timetables, fares, durations, stops, operators and accessibility values are illustrative.** They are not calculations of road/rail distance or evidence that real transport serves a city pair. The directory represents real city names; the bus/rail stops and services used by this demo are fictional. Initial Kazakhstan search results are direct bus/train journeys. Existing transfer and multimodal acceptance scenarios remain in the legacy network.

Selecting an offer uses the existing checkout and five-minute reservation flow. Successful, failed and uncertain payments are simulated. Cancellation quotes use the policy saved at purchase; refunds have their existing requested/pending/completed/failed states. A disrupted booking can offer eligible generated alternatives or cancellation. Replacement payment and old-leg refunds remain separate. No valid ticket, real charge or actual supplier reservation is produced.

Generated route identifiers remain internal: passenger cards show localized transport and city names, while details and operator tools retain the original demo code. Authored route numbers such as `VC1` remain unchanged.

## Tenge and local time

KZT amounts remain `Decimal`; no legacy EUR price is converted. New KZ stop identifiers use `KZ-{nine-digit KATO}-B` or `-R`. Their transport market determines the `Asia/Almaty` timezone, currently UTC+5. Currency alone never determines timezone: old non-KZ KZT acceptance fixtures and historic EUR journeys keep Berlin time.

Search/booking/travel-plan/recovery/operator responses include market timezone metadata and explicit `+05:00` timestamp offsets for Kazakhstan. Naive recovery and operator inputs use the booking or selected route timezone. Payment/refund activity timestamps, departure notices and PDF times follow that market. Calendar exports retain UTC instants so calendar applications can display the correct local time. Existing stored snapshots and old Berlin journeys are preserved.

Kazakhstan arrival search returns `arrive_by` with an explicit `+05:00` offset. The interface carries that exact instant through result selection, comparison, itinerary revalidation and checkout. Do not replace it with a naive timestamp: the shared legacy itinerary/checkout datetime fields otherwise use the legacy timezone. The deadline is checked against the current timetable before reserving; it is not a punctuality guarantee.

## Additive setup and operator access

After applying migrations with `manage.py safe_migrate`, run:

```bash
python manage.py prepare_kazakhstan_demo
```

The command adds missing **90 hubs, 180 fictional bus/rail stops and their transfer links, two operators and the example policy**. Services are created when a city pair/date is searched. The earlier geography/generation increment required no new migration. The new search-preferences increment adds migration `accounts.0006_journeyplan_search_preferences`: saved plans gain `time_mode`, `wheelchair_required` and nullable `max_price`, with valid-mode/nonnegative-budget constraints. Existing plans default to departure mode, no accessibility requirement and no price limit; their original trip fields and notes are preserved. Apply it through `safe_migrate`; do not reset or reseed an existing database. Preparation neither resets records nor copies a user's local records to hosting.

New operator accounts are scoped to their own transport operator:

| Account | Operator |
| --- | --- |
| `ops.kzbus@doedu.test` | Kazakhstan synthetic buses |
| `ops.kzrail@doedu.test` | Kazakhstan synthetic trains |

Hosted setup requires a private generated `DEMO_USER_PASSWORD` of at least 16 characters. Keep its value in hosting configuration, outside Git, chat and public instructions. Existing passwords, roles, memberships and access revocations are preserved. An existing account with a conflicting role, staff/admin privileges, missing/reassigned membership is left unchanged and reported for administrator review. Re-running setup does not grant revoked access back.

The hosted launcher runs locked migrations, the explicitly enabled guarded legacy bootstrap and then this additive command before starting Gunicorn and the worker. The legacy empty-database bootstrap and the additive Kazakhstan preparation serve different purposes. Never run the destructive development `seed_demo` command to update an existing database.

Persistent database defaults in `0006` let the previous application version insert plans during rolling updates. `accounts.0007_journeyplan_database_defaults` also repairs those defaults on databases that applied the first version of `0006`; it changes no saved rows. Both migrations were applied locally with private backups and preservation checks, including all saved preference fields. A historical `0005` model insert against the latest schema verifies old-version write compatibility.

## Private plans and sharing

Plans remain account-owned: create/list/edit/repeat/delete through `GET/POST /api/kazakhstan/plans/` and `PUT/DELETE /api/kazakhstan/plans/{id}/`. They persist the time mode, accessibility preference and optional total-price limit alongside the original trip fields and private note. Up to 50 plans per account; saving requires a future date within one year. Past plans remain readable and deletable. Authentication, CSRF and ownership checks apply server-side. While editing a plan, searching is disabled until the traveller saves or cancels editing. Saving an edit updates the same plan through `PUT`; it does not create a duplicate or discard the private note.

Share links whitelist public trip fields: origin, destination, date, time, passengers, modes, time mode, accessibility requirement and optional total-price limit. Executed-search links additionally include `search=1` and a permitted sort value. They contain no private note, user ID or plan ID and do not expose saved plans. Old links without the executed-search marker remain prefill-only. Invalid shared values fall back with a warning and do not automatically execute a search. Public links use the deployment origin; localhost links work only on that machine.

Submitting a search records its public parameters in the address. Browser Back and reload restore those parameters and rerun the availability query, so returned results reflect current fares/capacity rather than a cached reservation. Comparisons reset when the search changes. City filtering preserves the selected city until a traveller selects another. Kazakhstan repeat-booking links start a new search on the next Kazakhstan calendar day at 06:00 and retain the accessibility requirement; they do not silently reuse an expired departure time.

## Verification status

For the current search-preferences increment, final local verification passed:

- **373 backend tests**, **35 frontend unit tests**, frontend **build/lint**, **57 Playwright scenarios**, including **2 PWA scenarios**. All 57 passed together against the final production build.
- OpenAPI schema validation, migration dry-run consistency, secret scan and whitespace checks passed.
- Migration `accounts.0006_journeyplan_search_preferences` was applied to the local user database after a private logical backup. Before/after checks preserved accounts/passwords/roles, memberships, original plan fields and notes, and bookings. The integrity check passed and the native API/worker were ready.
- A 390px browser check confirmed no horizontal overflow, explicit `+05:00` deadline context, and restored results after Back/reload. The edit/save workflow retained the same plan ID through `PUT` and prevented draft loss; the Kazakhstan screen no longer briefly showed the unrelated provider state during configuration loading.
- Current-revision CI and an observed public deployment remain pending. These local results do not establish either outcome.

Historical evidence for the earlier 90-city increment at `44cdde6`:

- Final combined local backend suite: **353 tests passed**, including the geography/generation/setup, market-timezone, booking/export, recovery/operator and followed-line cases.
- Frontend: **29 unit tests**, **build** and **lint** passed.
- Browser verification: **54 Playwright scenarios passed**, plus **2 separately enabled PWA scenarios**. These combined results supersede earlier focused counts; do not add those focused counts to the totals.
- On 11 November, [all five CI jobs](https://github.com/Alizhan2/Project-X/actions/runs/43055303104) passed for `44cdde6efb584c5f57bcc56cd0c9c7370e151a00`. Public deployment is awaiting the owner’s manual update in Render because native Chrome controls timed out. Earlier public results in the deployment record apply to the earlier release.
- No external API, real payment, real ticket issuance or real participant response was exercised or generated.

## Future supplier integration — separate work

The current demo requires no API key, paid supplier subscription or vendor outreach. `OneTR` remains a future adapter boundary; a non-simulation search without a connected provider returns the explicit unavailable state rather than invented real offers. Commercial launch mode remains refused.

The [official 1TR site](https://1tr.kz/), checked on 11 November 2026, advertises agency API access for bus and rail. Agency contact: `bpm@mobportal.kz`, +7 747 842 30 59. Its free connection/zero-commission statements concern bus stations; free agent API or sandbox terms are not established publicly. The short endpoint examples are not an authentication or integration contract.

A future real-ticket milestone needs supplier documentation and permitted sandbox access, verified city-to-station mapping and coverage, fare/availability revalidation, reservation/issuance/cancellation integration, payment/refund reconciliation and actual mail delivery. Existing demo cities, capacity or accessibility must never be used as a fallback claim about a real supplier. See [commercial-readiness backlog](commercial-readiness.md). No supplier was contacted by this implementation.

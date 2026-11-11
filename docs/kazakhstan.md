# Doedu Kazakhstan demonstration

The current work implements the owner's clarified scope: **a working Kazakhstan demonstration without external APIs**. The home page `/` (also `/kazakhstan`) searches generated bus/train services, reserves places and uses the existing simulated payment, refund and replacement lifecycle. Private plans and share links remain available. A saved plan alone does not reserve a place.

The 90-city increment has passed combined local verification and all five [CI jobs at `44cdde6`](https://github.com/Alizhan2/Project-X/actions/runs/43055303104); public deployment remains pending. The last observed public release remains `e2e4b5a3c649`, which predates Kazakhstan booking; consult [HANDOFF](HANDOFF.md) and the [deployment record](render-free-test.md) before describing a public release as updated.

## Geography and language

- The directory contains **all 90 city settlements in KATO NK RK 11-2025, updated 4 November 2026**, including cities that are not regional centres. It does not include every village or settlement type.
- Source: the Bureau of National Statistics [KATO classifier](https://stat.gov.kz/ru/classifiers/statistical/21/) and its [4 November workbook](https://stat.gov.kz/upload/iblock/3af/er0488xunb664axbufnw46sagt10aqsm/%D0%9A%D0%90%D0%A2%D0%9E_04.11.2026.xlsx). Source date, retrieval date and checksum are recorded in `catalog.py` and exposed as catalogue metadata.
- Russian and Kazakh source names are preserved. English labels are editorial Latin transliterations. City lookup matches the catalogue's EN/RU/KK city names, region names and recorded aliases.
- Existing first-20 `kz-*` identifiers remain stable so saved plans and shared links continue to resolve. KATO geography identifiers are separate from any future supplier station identifiers.

## Generated transport and booking

Simulation-enabled launches use the internal `kazakhstan_demo` provider. Catalogue and search responses explicitly report that they are simulated; no supplier request is made.

`GET /api/kazakhstan/catalog/` returns cities, geography provenance, KZT, `Asia/Almaty`, simulation/provider status and whether demo booking is enabled. `GET /api/kazakhstan/search/` validates different cities, a future date within one year, local time, 1–9 passengers and bus/train modes. It returns generated direct itineraries and supports departure, price and duration sorting.

Generation is limited to the selected origin/destination pair and requested dates: the pair gets a two-day example timetable, and results cover the next 24 hours from the chosen departure time. This avoids prebuilding a complete national route mesh. Repeating a search reuses existing rows and preserves current operator fares, delays, cancellations, capacity and booked places. It does not restore a cancelled service or overwrite purchase snapshots.

**Timetables, fares, durations, stops, operators and accessibility values are illustrative.** They are not calculations of road/rail distance or evidence that real transport serves a city pair. The directory represents real city names; the bus/rail stops and services used by this demo are fictional. Initial Kazakhstan search results are direct bus/train journeys. Existing transfer and multimodal acceptance scenarios remain in the legacy network.

Selecting an offer uses the existing checkout and five-minute reservation flow. Successful, failed and uncertain payments are simulated. Cancellation quotes use the policy saved at purchase; refunds have their existing requested/pending/completed/failed states. A disrupted booking can offer eligible generated alternatives or cancellation. Replacement payment and old-leg refunds remain separate. No valid ticket, real charge or actual supplier reservation is produced.

## Tenge and local time

KZT amounts remain `Decimal`; no legacy EUR price is converted. New KZ stop identifiers use `KZ-{nine-digit KATO}-B` or `-R`. Their transport market determines the `Asia/Almaty` timezone, currently UTC+5. Currency alone never determines timezone: old non-KZ KZT acceptance fixtures and historic EUR journeys keep Berlin time.

Search/booking/travel-plan/recovery/operator responses include market timezone metadata and explicit `+05:00` timestamp offsets for Kazakhstan. Naive recovery and operator inputs use the booking or selected route timezone. Payment/refund activity timestamps, departure notices and PDF times follow that market. Calendar exports retain UTC instants so calendar applications can display the correct local time. Existing stored snapshots and old Berlin journeys are preserved.

## Additive setup and operator access

After applying migrations with `manage.py safe_migrate`, run:

```bash
python manage.py prepare_kazakhstan_demo
```

The command adds missing **90 hubs, 180 fictional bus/rail stops and their transfer links, two operators and the example policy**. Services are created when a city pair/date is searched. No new migration is required by this increment. The command neither resets the database nor copies a user's local records to hosting.

New operator accounts are scoped to their own transport operator:

| Account | Operator |
| --- | --- |
| `ops.kzbus@doedu.test` | Kazakhstan synthetic buses |
| `ops.kzrail@doedu.test` | Kazakhstan synthetic trains |

Hosted setup requires a private generated `DEMO_USER_PASSWORD` of at least 16 characters. Keep its value in hosting configuration, outside Git, chat and public instructions. Existing passwords, roles, memberships and access revocations are preserved. An existing account with a conflicting role, staff/admin privileges, missing/reassigned membership is left unchanged and reported for administrator review. Re-running setup does not grant revoked access back.

The hosted launcher runs locked migrations, the explicitly enabled guarded legacy bootstrap and then this additive command before starting Gunicorn and the worker. The legacy empty-database bootstrap and the additive Kazakhstan preparation serve different purposes. Never run the destructive development `seed_demo` command to update an existing database.

## Private plans and sharing

Plans remain account-owned: create/list/edit/repeat/delete through `GET/POST /api/kazakhstan/plans/` and `PUT/DELETE /api/kazakhstan/plans/{id}/`. Up to 50 plans per account; saving requires a future date within one year. Past plans remain readable and deletable. Authentication, CSRF and ownership checks apply server-side.

Share links contain only origin, destination, date, time, passengers and modes. They contain no private note, user ID or plan ID and do not expose saved plans. Filtering preserves the selected city until a traveller selects another. Invalid shared values fall back with a warning. Public links use the deployment origin; localhost links work only on that machine.

## Verification status for this increment

- Final combined local backend suite: **353 tests passed**, including the geography/generation/setup, market-timezone, booking/export, recovery/operator and followed-line cases.
- Frontend: **29 unit tests**, **build** and **lint** passed.
- Browser verification: **54 Playwright scenarios passed**, plus **2 separately enabled PWA scenarios**. These combined results supersede earlier focused counts; do not add those focused counts to the totals.
- On 11 November, [all five CI jobs](https://github.com/Alizhan2/Project-X/actions/runs/43055303104) passed for `44cdde6efb584c5f57bcc56cd0c9c7370e151a00`. Public deployment is awaiting the owner’s manual update in Render because native Chrome controls timed out. Earlier public results in the deployment record apply to the earlier release.
- No external API, real payment, real ticket issuance or real participant response was exercised or generated.

## Future supplier integration — separate work

The current demo requires no API key, paid supplier subscription or vendor outreach. `OneTR` remains a future adapter boundary; a non-simulation search without a connected provider returns the explicit unavailable state rather than invented real offers. Commercial launch mode remains refused.

The [official 1TR site](https://1tr.kz/), checked on 11 November 2026, advertises agency API access for bus and rail. Agency contact: `bpm@mobportal.kz`, +7 747 842 30 59. Its free connection/zero-commission statements concern bus stations; free agent API or sandbox terms are not established publicly. The short endpoint examples are not an authentication or integration contract.

A future real-ticket milestone needs supplier documentation and permitted sandbox access, verified city-to-station mapping and coverage, fare/availability revalidation, reservation/issuance/cancellation integration, payment/refund reconciliation and actual mail delivery. Existing demo cities, capacity or accessibility must never be used as a fallback claim about a real supplier. See [commercial-readiness backlog](commercial-readiness.md). No supplier was contacted by this implementation.

# Doedu Kazakhstan

The `/kazakhstan` page is a separate geographic catalogue and integration preparation area. Existing simulated itineraries, EUR bookings and Europe/Berlin demo timestamps are preserved. It does not sell tickets, make supplier requests, create reservations, or take payments.

## Implemented

- 20 cities: the 17 regional capitals and Astana, Almaty, Shymkent. City and region names in Kazakh, Russian and English; stable internal `kz-*` identifiers.
- Currency KZT (₸). Provider prices use Decimal, not floating-point arithmetic or a conversion of old EUR prices.
- IANA `Asia/Almaty`, currently UTC+5. Inputs are interpreted in Kazakhstan time independently of the browser timezone. Provider timestamps must be timezone aware.
- `GET /api/kazakhstan/catalog/`: multilingual geography, market metadata and explicit provider status.
- `GET /api/kazakhstan/search/`: validates cities, future date (up to one year), local time, 1–9 passengers and bus/train modes. It returns HTTP 503 `provider_not_connected` until a real supplier adapter exists. This differs from a successful search with zero seats.
- Backend supplier boundary under `backend/apps/transport/kazakhstan/`. Offers carry supplier ID, expiry/check timestamps, full-party price, currency and passenger count. Output excludes expired offers, mismatched routes/parties/modes and journeys longer than 72 hours. This internal policy is not a claim about supplier search horizons or schedules.
- Booking remains disabled even for an adapter returning search offers. UI offer rendering and checkout require a later integration milestone.

No migration, paid subscription or API key is required for this preparation. Existing data has not been reseeded. There are no fabricated Kazakhstan schedules or fares.

## 1TR.kz access

Verified on the official site https://1tr.kz/ on 2026-10-20:

- Agency contact: Бахтияр, bpm@mobportal.kz, +7 747 842 30 59. General contact: office@mobportal.kz.
- Agency API is advertised for bus and rail tickets. Free connection and zero commission statements concern bus stations/carriers; free agent API access or a free sandbox is not established by the public page.
- The short `/v1/...` examples on the landing page are not a complete integration specification. No base URL, authentication scheme or response shape is assumed in our code.

Suggested message to send yourself:

> Здравствуйте! Разрабатываем Doedu — сервис поиска поездок по Казахстану на казахском, русском и английском языках. Хотим подключить автобусные и железнодорожные билеты через API. Есть ли бесплатная песочница и тестовые ключи? Можно ли начать с поиска и перехода на оформление у партнёра без абонентской платы? Пришлите, пожалуйста, документацию API, условия подключения, тарифы, комиссии, требования к ИП/ТОО, депозиту и минимальному обороту, а также перечень доступных перевозчиков и направлений.

Do not put production credentials in chat or Git. After receiving the official contract, configure server-side secrets through the deployment environment.

## Next integration milestones

1. Obtain documentation, sandbox credentials, commercial terms, permitted data display/cache durations and supplier station identifiers. Map internal cities to verified station IDs; a city is not a station and coverage must be confirmed.
2. Implement `OneTR.search` from the actual specification: bounded timeouts/retries, redacted logs, rate limits, provider errors, Decimal KZT values and timezone normalization. Never fall back to demo data on supplier failure. Confirm price includes the entire party and all fees; represent incomplete pricing explicitly rather than guessing.
3. Contract tests using authorized sandbox fixtures: no results, timeout, expiry, price changes, route mismatches and multi-day rail journeys. Display real offers with source and freshness only after those checks pass.
4. Add provider-backed booking separately: fare revalidation, idempotency, reservation expiry, payment/issuance reconciliation, signed callbacks, refunds and supplier ticket documents. A local database transaction cannot guarantee atomic purchases across independent providers.
5. Real-sales launch requires separate approval and verification. The existing commercial-mode guard remains in place.

Sources for geographic/time conventions:
- https://stat.gov.kz/ru/industries/social-statistics/demography/publications/476642/?sphrase_id=2098465
- https://www.president.kz/ru/republic_of_kazakhstan/kazakhstan
- https://primeminister.kz/ru/decisions/19012024-20

## Validation

2026-10-20: 230 backend tests passed on PostgreSQL; 9 frontend unit tests and all 23 existing Playwright scenarios passed against an isolated production-like stack. Build and OpenAPI validation passed. Lint has five existing warnings and no errors. Manual browser automation exercised EN/RU/KK, provider-unavailable responses, identical-city validation and desktop/mobile layout. Actual 1TR requests and real ticket issuance remain untested because partner access is unavailable.

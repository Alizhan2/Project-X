# Competitive analysis and product roadmap
Date: 2026-10-20. Sources are web search summaries (several are blogs or vendor marketing); items marked **unverified** need checking in the real apps before they drive a decision.

## Competitors and what they do well
| Competitor | Strength (as found) | Weakness / opening for Doedu |
|---|---|---|
| **Rome2Rio** (owned by Omio) | Route discovery across many operators; nearly half of results combine several modes; fare estimates; sends the user to the operator to buy ([Travolution](https://www.travolution.com/news/travel-sectors/travel-agents/omio-sets-sights-on-international-growth-as-it-acquires-rival-multi-modal-site-rome2rio)) | Discovery only, no single coordinated booking, no help when a connection breaks |
| **Omio** | Compare and book trains, buses, flights in one app; commission added to the price (3–8 EUR per one blog, **unverified**) | Booking per leg with the partner; recovery after disruption not described in the sources |
| **Citymapper / Moovit** | Real-time disruption heads-ups during the journey, line subscriptions, "modified service" flags ([Moovit](https://moovit.com/blog/service-alert-notifications/)) | Urban transit: they warn, they do not rebook and re-price the rest of a purchased trip |
| **Aviata** (Kazakhstan, Freedom) | Price calendar, filtering of lower berths, train/carriage reviews, pay by card or Kaspi, hints that catch mistakes in passenger data ([finance.kz](https://finance.kz/articles/kak-kupit-bilety-na-poezd-v-kazahstane)) | Mostly flights; no bus-to-train-to-taxi chains found |
| **Tickets.kz** | Agency selling air, rail, bus tickets and insurance | Single-mode purchases |
| **1TR.kz, Tutu, Trainline, FlixBus** | Not covered by the searches: **unverified** | Review the real apps before copying anything |

## Doedu's differentiator (already built)
Coordinated multimodal booking **plus** disruption recovery: detect a broken connection, offer replacements with exact price difference, apply atomically. The sources show competitors alert users; none was found that re-plans and settles the remainder of a purchased journey. This should be the headline of the product, not a hidden feature.

## Already in Doedu
Bus/train/taxi chains up to 3 legs · sort by price/duration/transfer buffer · arrive-by search · filters · route comparison · saved directions · upcoming-journey card · calendar and PDF export · share links · cancellation with explicit refund table · notifications · replacement offers · kk/ru/en · Kazakhstan city catalogue (provider not connected) · account recovery and optional e-mail verification · redesigned shell with simulation banner.

## Gaps and proposed additions (ordered by value for effort)
**P1: makes the demo feel finished (no external accounts needed)**
1. **Route visual**: schematic line of the journey (stops, mode icons, transfer gaps, delay highlighting) on results, details and booking. Competitors lean on maps; ours needs no map service.
2. **Day price/time strip**: cheapest and fastest per day for +/-3 days from data we already hold (Aviata-style price calendar).
3. **Saved travellers and one-tap rebooking** ("repeat this trip"): shorter checkout. Names only, consistent with data minimisation.
4. **Connection-protection messaging**: on results show per-journey "what happens if this connection breaks" and the transfer buffer in plain words; a post-booking timeline of status changes.
5. **Dark mode and visual polish pass**: typography/spacing, empty/loading/error states, motion that respects reduced-motion; verified on mobile.
6. **PWA**: installable, offline "my journey" screen (cached booking details). Frontend-only.

**P2: needs a decision or an external account (ask first)**
7. Telegram/WhatsApp-style notifications (popular channel in the region: **assumption**, not verified); needs a bot account.
8. Real e-mail delivery (SMTP provider), for verification/reset and booking e-mails.
9. Accessibility matching across the whole chain (step-free journeys) with honest "unknown" values.
10. Ratings/reviews and CO2 estimate (needs trustworthy data).

**P3: needs real partners (commercial phase, docs/commercial-readiness.md)**
Real supplier inventory (e.g. 1TR.kz API), real payments (Kaspi/cards via a provider), ticket issuance, live delay feeds.

## Principles
Keep every simulated element labelled; no fabricated schedules or prices for Kazakhstan; no external services without approval; every feature gets tests and an accessibility check.

## Status (2026-10-20)
Delivered locally, verified in the browser suite: **(1) route overview** on results, journey details, booking and replacement offers (no map service; widths scale with duration, delayed legs outlined, one summary sentence for screen readers); **(2) nearby-days strip** backed by `GET /api/search/days/` (same planner as `/search/`, so numbers match; hidden for arrive-by searches; "Lowest price" badge only when prices differ); **(5) design polish**: dark theme (system preference, saved choice, toggle in the header, contrast-checked in both themes), loading skeletons, reduced-motion respected.
Not started: saved travellers, repeat-trip shortcut, PWA/offline screen, connection-protection wording (items 3, 4, 6).

## Status update: items 3, 4, 6 (2026-10-20)
- **3. Saved travellers**: opt-in, names only, max 10, one-tap reuse on the booking form, removable in My journeys (`/api/travellers/`). "Repeat journey" already existed (a fresh search at current prices).
- **4. Connection protection**: journey details and bookings explain, per change, the spare minutes ("breaks if the earlier service is more than N min late"), that a taxi leaves when you are ready, and what happens after booking if a connection breaks (notification, replacement offers with exact price difference, no places held until accepted, full refund of unused legs). Bookings also show a **trip activity** timeline built from existing records.
- **6. PWA**: manifest, icons, offline app shell, offline copies of confirmed journeys, offline banner. Verified in the browser (dev: offline flow; production-like server: service worker control, no API data cached).

## Polish pass (2026-10-20)
Screens were reviewed visually (desktop and 390 px, light and dark). Fixed: footer sentence began with a dangling dash; unpaid bookings showed "Net paid: EUR 0.00" (and an offline copy would have shown a wrong 0.00: now hidden); cards touched without spacing; Kazakhstan planner had a card-in-card layout and unstyled (grey, disabled-looking) buttons; wide tables overflowed the card on phones (now scroll inside a focusable, labelled region); the nearby-days strip repeated a long "No journeys found." in every empty cell. Lint is now clean (providers split from their hooks; data loading in effects guarded against stale responses). Regression tests added for phone overflow, the unpaid-booking view and the footer wording.

## Deeper competitor review (2026-10-21): what to take
Evidence quality: Trainline/FlixBus/Omio items come from vendor pages, app-store listings and trade press (claims, not audited); Kaspi/KTZ items from Kaspi's own help pages and Kazakh press; 1TR.kz public page is partner-oriented. Marked **unverified** where a single source.

| Competitor | Feature found | Doedu today | Take it? |
|---|---|---|---|
| Trainline | Price alerts for the cheapest tickets; live times with a "Track" view of each stop; disruption push alerts; Delay Repay claim prefilled for the operator (**vendor claims**) | Estimated progress (not GPS), in-app disruption notices, replacement offers, full refund when a connection breaks | **Price alerts: yes.** Prefilled compensation: our equivalent is the refund/replacement flow; a delay-compensation rule is a product/legal decision |
| Trainline | "Travel Forecast": advance warning that a train is likely delayed | None (no ML, no real feeds) | No: needs real operational data; keep out of scope |
| FlixBus | Tickets usable offline, live bus tracking, manage changes in the app | Offline copy (PWA), estimated progress, cancel/replace | Done; tracking depends on real feeds |
| Omio | Price-drop alerts (one German blog, **unverified**), Omio Flex (cancel shortly before departure for a fee, 2024 press release), 24/7 support advertised; a user complaint reports a missed multi-leg connection with no support channel | Policies per leg, recovery flow | **Support/help page: yes** (the complaint is exactly the gap Doedu fills, but only if help is easy to find). Paid flex = commercial phase |
| Rome2Rio | Door-to-door options across modes with estimated prices; booking on partner sites, so one trip may be several purchases | One coordinated booking for the chain | Our edge. Door-to-door from addresses needs geocoding (out of MVP scope) |
| Moovit / Citymapper | Subscribe to lines for alerts; severity colours; "modified service" flag | Per-booking alerts only | **Follow a route/service: yes** (alerts without a booking) |
| Kaspi Travel (KZ) | Subscribe to notifications when sales open or **seats free up** on a train; refund from My trips; exchange; 45-day sale horizon ([Kaspi guide](https://guide.kaspi.kz/client/ru/travel/train), [digitalbusiness.kz](https://digitalbusiness.kz/2024-12-26/uznali-kak-kupit-zhd-bileti-na-kaspi-travel-za-45-dney-do-otpravleniya/)) | Sold-out services simply disappear from results | **Seat-release alert / waitlist: yes: strongest regional signal** |
| KTZ portal/app (KZ) | **Waiting list** when no seats; e-ticket refund; cabinet to download tickets ([Kapital.kz](https://kapital.kz/gosudarstvo/65341/ktzh-zapustila-mobilnoe-prilozhenie.html)) | None | **Waitlist: yes** (same feature as above) |
| Aviata (KZ) | Price calendar, hints that catch passenger-data mistakes | Day strip done; basic validation | Add inline validation hints (small) |
| 1TR.kz | Partner-oriented REST API, agencies set their own commission; passenger UI appears Russian-only | kk/ru/en | Keep trilingual as a differentiator; API access is a commercial step |

### Proposed next build (all implementable with no external account)
1. **Watches**: "notify me when this journey gets cheaper" and "notify me when a place frees up on this sold-out service". Stored per account, evaluated by the existing worker when departures, fares or capacity change; delivered as in-app notifications. Covers Trainline/Omio price alerts and Kaspi/KTZ seat alerts in one feature. Honest limits: simulated data; no promise of a seat; notification only.
2. **Follow a route**: alerts about delays/cancellations on a service without owning a booking.
3. **Help centre page**: what happens when a connection breaks, how refunds work, what "simulated" means, who to contact (contact owner to be defined: today there is none).
4. **Inline passenger-data hints** (Aviata-style).
Decisions needed from the product owner: any delay-compensation rule (amount, threshold); a paid "flex" option; who answers support.

## Status update: Alerts (watches) built (2026-10-21)
Price-drop and availability alerts (Trainline/Omio price alerts; Kaspi/KTZ seat-release/waitlist idea). `Watch` model, `/api/watches/`, Alerts page, "Notify me" under the results (not for arrive-by searches), notification links back to the search. Evaluated by the worker every 5 minutes, promptly after anything that can change results (fare/capacity/service edits, cancellations or expiries that free places; bursts collapse into one job) and lazily when the owner lists their alerts (correct even without a worker). Alerts only notify: no seat or price is held. Race found and fixed: two simultaneous listings could read a stale price (now waits for the evaluation; test fails without the fix). Next from the plan: follow-a-route alerts, help page, inline passenger hints.

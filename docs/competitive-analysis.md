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

# Next journey and portable travel plans

Implemented 2026-10-20. All services, bookings and payments remain simulated.

## Passenger experience
- The signed-in search page shows the next confirmed journey, or an explicit empty state. An already-started journey stays visible until its current arrival time passes. Unpaid, expired and cancelled bookings are excluded.
- The card uses current timetable estimates, shows the next/current leg and links to the booking. Disruptions remain visible with a link to review replacement/cancellation. This is not GPS or proof of boarding.
- The card and open booking refresh every 15 seconds. The card reports refresh failures rather than silently presenting an old timetable as current.
- The booking timeline now shows current times, preserving the original purchase snapshots separately. All displayed times use Europe/Berlin.
- Confirmed bookings have **Add to calendar (.ics)** and **Download journey PDF** buttons. Download errors stay in the page. Downloading never changes a booking, payment or capacity.

## Backend and data rules
- `GET /api/bookings/upcoming/` returns `journey: null` or a current travel plan, scoped to the signed-in user.
- Booking payloads add `travel_plan` for confirmed bookings. The shared projection uses the existing disruption assessment, including retimed taxis, and excludes replaced legs.
- Upcoming selection orders by first current departure, not purchase time; in-progress journeys take precedence over future departures. Candidates include recent past snapshots to account for the operator delay limit.
- `GET /api/bookings/<reference>/calendar/` and `/pdf/` require ownership and confirmed status. Unknown/other users' references return 404. Unconfirmed/cancelled/expired bookings return 409.
- Binary downloads are attachments, `private, no-store`, `nosniff`, and rate limited using the existing booking scope. No public sharing tokens or third-party PDF service are used.
- No schema migration or demo reseed is required.

## Calendar
Each current leg becomes a private VEVENT with a stable booking/sequence UID, UTC timestamps and a DEMO label. Text is escaped and physical lines fold at 75 UTF-8 bytes using CRLF. No passenger names/contact email are included.

The file is a snapshot, not a subscribed calendar. Timetable changes/cancellation do not update an imported copy automatically. Calendar clients may handle repeated imports differently; users may need to remove an older event. A disrupted journey cannot be exported to calendar until resolved. The PDF remains available with a prominent disruption warning.

## PDF
ReportLab 5.0.1 and its dependencies are hash-locked. The bundled DejaVu Sans font is accompanied by its upstream licence. The A4 document includes booking reference, passenger count, current times and stops, connections, changed departure times, net simulated payment and a timestamp. It omits traveller names and contact details.

PDFs are generated in memory. Layout supports page breaks and repeated page footers. They are demonstrative journey plans, never valid tickets. The PDF is not tagged for screen readers; the accessible web itinerary remains available.

## Verification
- Full backend suite: 205 tests passed; eight cover upcoming selection, ownership/authentication, confirmation state, delays, disrupted routes, replacements, download headers and UTF-8 calendar escaping/folding.
- After fixing the new projection to serialize Europe/Berlin offsets, the targeted export/travel tests were rerun.
- Frontend build and five comparison tests passed; lint has the same five existing warnings.
- Existing 23 Playwright regression scenarios passed against a disposable PostgreSQL database and built SPA/gunicorn stack.
- Browser walkthrough downloaded both files from a recovered three-leg booking. The PDF was rendered and visually checked; extracted text matched current delayed/replacement times. Desktop and mobile screenshots were checked.
- Additional axe checks on the new card and booking/download screen reported zero WCAG A/AA violations in an isolated browser context. CSP was bypassed only in that test context to inject axe; application CSP was unchanged.
- Python dependency audit found no known vulnerabilities.
- Hosted deployment, calendar-provider subscriptions, reminders and offline app caching are outside this feature.

# Personal data inventory and handling
This is an engineering inventory, **not legal advice and not evidence of compliance**. The controller (you/your organisation) must decide the legal basis, privacy notice,
retention periods and data-subject procedures with qualified advisers before any public launch. Nothing here should be copied into a published policy as-is.

## What is collected and why (hosted demo)
| Data | Where | Purpose | Notes |
|---|---|---|---|
| E-mail address | `accounts_user`, `bookings_booking.contact_email` | sign-in; booking contact | unverified (no e-mail flow yet) |
| Full name (account) | `accounts_user.first_name` | display, traveller default | |
| Traveller names | `bookings_traveller` | who travels (one name per passenger) | no documents, birth dates, phone numbers |
| Password hash | `accounts_user.password` | authentication | PBKDF2; never exposed |
| Bookings, legs, payments, refunds | bookings/payments tables | the service itself; purchase history | **simulated** payments: no card data is ever collected or stored |
| Saved travellers (optional) | `accounts_savedtraveller` | one-tap checkout | **Names only**, created only when the passenger ticks the opt-in box; max 10 per account; removable in My journeys; deleted with the account |
| Offline copies (optional, on the device) | browser `localStorage` | view a confirmed, upcoming journey without a connection | Booking plan and traveller names; **no** e-mail, payment attempts, refunds or activity log; max 5; kept until 24 h after arrival; cleared on sign-out and replaced when another account signs in; never sent anywhere |
| Notifications | `notifications_notification` | tell passengers about disruptions | contain booking references |
| Audit records | `core_auditrecord` | accountability (who changed what) | actor id + object ids, no free-text personal data |
| Session cookie | browser | login | `HttpOnly` |
| Operational logs | stdout | operations | user id and request id only; no e-mail, IP, bodies (tested) |
The frontend stores no tokens in the browser. The only personal data kept in the browser is the optional offline copy above (traveller names and journey plan). The service worker caches only static files, never `/api/` responses. No analytics, trackers, or third-party scripts are included (CSP forbids them).

## Minimisation already applied
Names + one contact e-mail only · no card/bank data · operators see booking reference, passenger count and effect, **never** e-mail or traveller names · other passengers' data is not retrievable (404) ·
logs and metrics carry no personal data · demo accounts are synthetic and exist only in dev/staging data.

## Retention and deletion: requirements to define (NOT implemented)
* No deletion/anonymisation feature exists. Decide: how long bookings (and their travellers/e-mails) are kept; what happens on an account-deletion request.
* Tension to resolve explicitly: purchase, payment, refund and audit history must stay intact (integrity, accounting, disputes) while personal fields can be minimised. The data model supports a
  future **anonymise-in-place** job (blank traveller names/contact e-mail, keep snapshots, amounts, references, audit rows); it has not been built or tested.
* Backups contain personal data: deletion requests also require a backup-expiry policy (retention is 14 days by default).
* Define who can access production data, and log that access.
## Demo vs real users
Synthetic demo accounts (`*@doedu.test`) are created only by the dev/staging seed command and are never created in production. Do not share privileged credentials for public access: give each administrator/operator a named account.

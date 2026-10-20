# Kazakh, Russian and English

The passenger and operator SPA supports English (`en`), Russian (`ru`) and Kazakh (`kk`). The header selector uses native language names, works before sign-in, updates the document language/title, and does not remount the search or checkout form. Selection is stored in this browser (`doedu.language`), not in the account; another device has its own preference. Initial precedence: supported `?lang=` from a mail link, saved preference, browser languages, English fallback. A manual change updates an existing `lang` query parameter so reload cannot undo it.

Coverage includes search/filter/arrival controls, comparisons, saved directions, upcoming trips, booking/payment/cancellation/recovery, notifications, account/reset/verification screens, operator tools, validation, accessibility labels, PDFs and calendar downloads. Seed stop/route names have translations; operator brands, arbitrary operator-authored names, passenger names, reference numbers, route codes, ISO currency codes and API enum values retain their identity. The UI uses explicit Russian/Kazakh month/day labels because some Chromium ICU builds have incomplete Kazakh data. All trip clocks still use Europe/Berlin; language selection does not convert the travel timezone or currency.

## API, mail and files

- The browser sends `Accept-Language` on API requests and private downloads. The backend accepts regional variants and quality values, falls back to English, and returns `Content-Language` plus `Vary: Accept-Language`.
- Language is scoped to each request with a context variable and reset after the response. Only presentation fields and validation errors are translated; persisted purchase snapshots and machine-readable codes are not rewritten. Existing English notification templates are translated on read.
- Password reset and email verification jobs capture their language when queued. Worker retries retain it; old jobs without it default to English. Links preserve the language in a non-secret query parameter; UID/token remain in the URL fragment. Token expiry, one-use checks, anti-enumeration responses and rate limits are unchanged.
- Restart the worker when deploying this change, alongside the web process: the account-email handler now accepts the optional `lang` payload field. Real SMTP is still not configured locally; tests use the in-memory mail backend and the local private preview backend.
- PDF/ICS use the language selected at download time. PDF embeds the existing DejaVuSans font for Cyrillic/Kazakh. Calendar escaping, 75-octet UTF-8 folding, UTC timestamps and stable event UIDs are preserved across languages. Owner checks, no-store headers and disruption restrictions still apply.

## Maintaining translations

`frontend/src/messages.json` is the authored source catalog. English source messages are keys with Russian and Kazakh values. Positional placeholders are interpolated as text, never HTML. `place:` keys are reserved for the known synthetic location/route names. Use `t()` for presentation text and `placeName()` only for transport names; never translate IDs, CSS classes, request values, status comparisons or arbitrary user names.

Run `python3 scripts/sync-translations.py` after editing the catalog. This copies it to `backend/apps/core/locales/messages.json` so the backend/worker build is independent of frontend files. `npm test` checks catalog parity, placeholders, dynamic comparisons, switching and deterministic dates. Add whole-message templates for new dynamic text; prefer complete sentences to translated fragments. More-specific legacy templates match before broad ones.

No dependency installation or database migration is needed. Operational logs and developer documentation remain in English. Native browser chrome and third-party calendar applications use their own language settings.

## Verification (2026-10-20)

- PostgreSQL suite: 224 tests, including request-language isolation, queue language persistence, translated validation, and identical calendar identity/times across languages.
- Frontend: production build and lint; nine unit checks including existing comparison coverage.
- Existing browser regression suite: 23 scenarios against a separate production-like database, not the user's data.
- Additional browser walkthrough: language switch/reload without losing search input, comparison, Kazakh booking and simulated payment, all three PDF/ICS downloads. Russian/Kazakh PDF text extraction and rendered pages checked for glyphs and layout. Both locales also passed mobile (390px) search and operator-impact axe checks with no WCAG A/AA violations found; search had no horizontal overflow. Mail-link language persistence and native form-validation text were checked in the browser.

These checks do not establish real mail delivery, real transport integration or commercial payment readiness. The app remains a simulation.

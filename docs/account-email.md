# Account email: verification and password recovery

Implemented locally on 2026-10-20. These are real account-security flows; transport and payments remain simulated.

## Passenger flows
- Sign in → **Forgot your password?** → enter email → open the emailed link → enter and confirm a new password → sign in again.
- Signed-in users with unverified email see **Verify your email** → **Send verification link** → open the email → **Confirm email**.
- Existing and newly registered accounts start unverified. Verification is optional for the synthetic demo; it does not gate bookings. No accounts are silently grandfathered as verified.
- Resetting a password proves mailbox ownership, marks email verified and invalidates existing authenticated sessions. The login failure counter is cleared.
- Links expire after one hour, are purpose-bound and become unusable after successful use. A changed email/password invalidates old links. GET does not consume a link, so email scanners cannot verify an account accidentally.

## Local development without a mail provider
The default development backend writes mail previews to `.local-mail/` at the repository root. This directory is gitignored and mode 0700; files are mode 0600. Open the newest file locally and use its link. Never publish these files or paste tokens into chat. These files are **not actual email delivery**; delete them when no longer needed.

Run `python manage.py run_worker` alongside Django and Vite. Mail is queued in PostgreSQL and sent by the worker, with up to five attempts using the existing retry/backoff mechanism. A request can be accepted before delivery succeeds; inspect failed `account_email` jobs and worker logs if an email is missing. Retry after fixing SMTP by requesting another link (60-second account cooldown). Queue payloads contain user ID, purpose and a credential fingerprint, not raw addresses, passwords or tokens. Changed credentials invalidate pending jobs. Delivery is at-least-once: a worker crash after SMTP accepts a message can cause a duplicate email.

## Hosted SMTP setup
Set these in the secret environment, never commit credentials:

```dotenv
PUBLIC_APP_URL=https://your-host.example
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.example
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Doedu <accounts@your-domain.example>
```

`PUBLIC_APP_URL` is a trusted HTTPS origin, not derived from request headers. Without an explicit origin, SMTP host and sender, deployed request endpoints return 503 for everyone rather than generating localhost links. Provider sender/domain authentication and actual inbox delivery remain deployment tasks; no SMTP provider was connected in this change.

Rate limits: `THROTTLE_ACCOUNT_EMAIL=5/hour` and `THROTTLE_ACCOUNT_TOKEN=20/min`, both by IP, plus a 60-second mailbox cooldown. CSRF is required on every POST, including anonymous requests. Password reset requests have the same status/body for known and unknown accounts; delivery runs outside the request to avoid SMTP timing differences. Links use URL fragments so tokens are not sent in server access logs. Do not add third-party scripts to these pages.

## Remaining policy work
MFA, mandatory verification before booking, verified-contact policy for booking passenger emails, account deletion and a real email-delivery monitoring service are outside this change. Public registration may remain closed with `REGISTRATION_ENABLED=false`.

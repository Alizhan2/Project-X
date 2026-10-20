# Local improvements — 2026-10-20

## Delivered
- Password recovery and optional email verification, with one-hour one-use purpose-bound tokens, CSRF, IP throttling, mailbox cooldown and background delivery/retries. Existing sessions are invalidated after password reset. See [account-email.md](account-email.md).
- Private development mail previews and environment-driven SMTP configuration. No SMTP provider connected; no claim of real inbox delivery.
- Refreshed transport identity, search layout, result cards and account forms; responsive desktop/mobile layouts and visible focus. Simulated transport/payment/ticket notices remain visible.
- Portable backup checksums on Linux/macOS, unique backup names, interrupted-dump cleanup, explicit restore target, rejection of nonempty databases and transactional restore.
- Updated backlog, security, configuration, limitations, production-readiness and handoff; regenerated validated OpenAPI.

## Evidence from this change
- PostgreSQL migration `accounts.0002_user_email_verified_at` applied locally using `safe_migrate`; no demo reseed of the user's database.
- Full backend suite: **187 passed** after queued delivery was introduced. One additional focused test for private mail-file permissions subsequently passed (188 tests now present; full 188-test suite not rerun).
- Existing **23 Playwright tests passed**, using a fresh, isolated staging-style database, gunicorn and the built SPA. Includes axe accessibility checks at desktop/mobile sizes and keyboard navigation. The disposable database/role was removed afterward.
- Secret scan passed across tracked files and new source files; synthetic test passwords are explicitly annotated. Local mail, browser artifacts and dumps are excluded from the Docker build context.
- Frontend build and lint passed; six pre-existing lint warnings remain. A later small auth refresh change was built; the 23-test run preceded that final refresh change.
- Browser: desktop and 390px mobile screenshots inspected; password-reset request UI reaches the generic accepted state. Backend tests cover successful verification/reset, expiry, wrong purpose, repeat use, invalid/inactive users, weak passwords, CSRF, changed credentials, asynchronous delivery failure and private mail-file permissions.
- `ops/backup.sh` → `ops/verify-restore.sh` succeeded with PostgreSQL **17.11** clients, with a real custom-format dump restored into a scratch database; application integrity passed. Existing database was never overwritten. Corrupted checksum and nonempty-target refusal both tested. Native macOS fallback (`shasum`) exercised. These are logical backups, not the earlier physical-copy rehearsal.
- Client tools retained outside the repository at `~/.doedu-tools/postgres-client-17/bin`. Source: [official Postgres.app 2.9.6 release](https://github.com/PostgresApp/PostgresApp/releases/tag/v2.9.6). Existing server was not replaced.
- Local worker started; readiness reports database/migrations/worker OK.

## Still outstanding
Full Docker Compose/read-only container runtime is intentionally deferred: user chose to continue without Docker. Previous CI at `ac46440` verified image build/non-root liveness; the current commit needs its own green GitHub Actions run before deployment. Hosted server/domain/HTTPS, release-image publishing, off-host scheduled backups, real SMTP delivery, mandatory verification policy and commercial integrations remain separate work. No real payment provider, dispatch or valid travel ticket was introduced.

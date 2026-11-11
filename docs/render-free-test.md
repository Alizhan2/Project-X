# Free Render usability-test deployment

Prepared for **12 November 2026, ten participants**. This is a temporary hosted demonstration with synthetic transport, payments, refunds and confirmations. Kazakhstan cities and private plans do not represent live supplier availability or valid tickets. See [Kazakhstan scope](kazakhstan.md) and [business rules](business-rules.md).

## Current status and evidence

The dedicated study deployment is **live**: [Kazakhstan planning](https://doedu-kazakhstan-test-x3wv.onrender.com/) and [fictional booking](https://doedu-kazakhstan-test-x3wv.onrender.com/demo). Render built and deployed revision `7c2d4bc6cd5ef25ab03f1fba6738f336b68b1b5d`. Initial deployment became live on 11 November at 15:01 UTC; a repeat deployment became live at 15:08 UTC. Both resources are free in the confirmed My Workspace. The unrelated `sanapath-ai` service was not changed.

Public checks passed: HTTPS 200, HTTP-to-HTTPS 301, staged HSTS and CSP, ready JSON with database/migrations/worker all `ok`, EN/RU/KK home pages, a 390px mobile viewport without horizontal overflow, independent registration, search, five-minute reservation, simulated payment, valid PDF/calendar downloads, Kazakhstan plan saving and parameter-only sharing. Anonymous booking access returned 403. After repeat deployment, the same authenticated session could read its confirmed booking, the saved Kazakhstan plan survived reload, and the worker was fresh. Logs confirmed the bootstrap was a no-op. The single synthetic smoke account/booking/plan are verification records, not participant observations.

After the persistence check, only the synthetic smoke booking was cancelled. Its snapshotted policy quoted EUR 3.50; repeating cancellation retained one refund, and the hosted worker completed it. This released the smoke booking's place before the participant session.

These are browser-emulation checks, not a physical-phone/mobile-data study. Hosted ten-user performance and moderated recovery scenarios remain to check before the session. The [release CI run](https://github.com/Alizhan2/Project-X/actions/runs/43043422451) records checks for the deployed revision; later documentation-only commits do not change that release.

The deployment files are prepared: root `render.yaml`, `backend/render_start.py` and the guarded `bootstrap_hosted_demo` command. All 326 backend tests passed, including eleven focused runtime/bootstrap tests. A disposable native rehearsal using production settings completed ten simultaneous register/search/reserve/pay flows (10/10), passed the integrity check, and preserved all 18 account password hashes and 14 bookings after a full launcher restart. Only the documented staged-HSTS warnings W005/W021 remained. The temporary database and role were removed. These results establish local behaviour, not free-instance latency or public HTTPS/phone behaviour.

## Resources and startup

The Blueprint explicitly selects **`plan: free` for both resources**, in Frankfurt:

| Resource | Blueprint name | Purpose |
| --- | --- | --- |
| Docker web service | `doedu-kazakhstan-test` | Built React app, Django API and one cohosted background worker |
| PostgreSQL 17 | `doedu-usability-db` | Dedicated synthetic study data; external database connections disabled |

Do not copy the local database, accounts, personal information or local environment files into this database. Do not reuse another application's database. If this workspace already has a free PostgreSQL database, resolve that constraint before deployment; never delete or upgrade an unrelated resource to make room.

The startup launcher derives the exact public hostname, HTTPS origin and listening port from Render's environment. A stable Django signing key is derived from the generated `DOEDU_SECRET_SEED`; secrets are not printed. It runs locked migrations and, when explicitly enabled, the hosted-demo bootstrap before supervising Gunicorn and `run_worker`. If either process exits, its sibling is stopped so Render can restart the pair.

Bootstrap requires a deployed demo launch, explicit `DOEDU_BOOTSTRAP_DEMO=true`, an empty application database and distinct generated passenger/operator and administrator passwords. It seeds fictional schedules and demonstration bookings once, then records a durable completion marker. Later starts preserve accounts, passwords and bookings. An unmarked database containing application data is refused. Do not clear the marker, run destructive `seed_demo`, or enable production demo-reset tools to bypass a refusal.

This short study uses Render's database-owner credential for migrations and runtime. It does **not** establish the separate migration/runtime roles or database-level least privilege described in the general [deployment guide](deployment.md). Do not describe this as a complete production deployment or enable commercial mode.

## Deploy after reviewing the plan

1. Review `render.yaml` and confirm that the plan contains only the two Doedu resources above, both free, with no paid worker, disk, cron service or database upgrade.
2. In Render, create a Blueprint from [Alizhan2/Project-X](https://github.com/Alizhan2/Project-X), branch `main`. Check the proposed resource changes before approving their creation. Stop if Render proposes billing or a change to an existing unrelated service.
3. Keep automatic application deployment disabled: `autoDeployTrigger: "off"`. During the study, deploy a reviewed revision manually; review and approve Blueprint changes separately. A new commit alone should not become a surprise study release.
4. Allow the initial image build, database provisioning, migrations and bootstrap to finish. Inspect diagnostics privately if startup fails; do not paste credentials, environment dumps or database URLs into chat or GitHub.
5. Open the service's assigned HTTPS `onrender.com` URL. Use `/` for Kazakhstan planning and `/demo` for fictional booking. A custom domain is not needed for the test.
6. Record the actual URL, deployed commit, date and successful checks below only after observing them. A prepared Blueprint or green local suite is not a deployment result.

Render manages HTTPS for the assigned hostname. Consult the official [Blueprint reference](https://render.com/docs/blueprint-spec) and [free-service limits](https://render.com/docs/free) if the platform's validation differs from this plan.

## Private accounts and ten-user tasks

Retrieve `DEMO_USER_PASSWORD` **only from the web service's Environment page in Render Dashboard** when the moderator needs a seeded account. Never put its value in chat, committed documentation or a public test link. This password covers seeded passengers and operators; operators can modify shared schedules, so moderators retain those credentials.

The administrator `admin@doedu.test` has the separate generated `DEMO_ADMIN_PASSWORD`. Never give participants the administrator password or use an administrator account as a shared passenger login. See [seeded scenario accounts](demo-data.md) for the individual passenger/operator identities.

Each of the ten participants should register a separate account for normal planning and booking tasks. The study Blueprint raises bounded registration/login limits to accommodate people sharing Wi-Fi; it does not disable abuse controls. Avoid unnecessary real personal data, and do not ask for real payment details.

For the ordinary booking task, use `/demo`, **NG-BUS → RV-BUS, tomorrow at 16:00 in the demo's Europe/Berlin time**, one passenger per account. The standard VC1 bus has 40 seats. Check that this departure is available immediately before the session. The intentionally scarce GL1 07:30, sold-out GL2 11:30 and cancelled VC1 10:00 departures are unsuitable for ten independent successful bookings.

Recovery, payment and refund fixtures are shared, stateful and effectively single-use. Operator delays/cancellations affect every participant booked on that departure. Run those tasks one at a time under moderator control, with separate prepared departures or an explicitly planned reset of a disposable study database between sessions. Never reset while participants are active. Follow the [demo script](demo-script.md); do not report generated accounts or rehearsals as actual participant responses.

## Before admitting participants

- Open the HTTPS site at least several minutes beforehand and allow a minute or more for a cold start. Confirm `/api/health/ready/` returns the expected database/migration result and that the worker heartbeat is fresh; also check `/api/health/live/`.
- On a phone using mobile data, check the home page, all three languages, Kazakhstan city search/plans/sharing, `/demo` search, sign-up, booking and a simulated payment. Verify PDF and calendar downloads where included in the tasks. Check that simulation labels remain visible.
- Run a ten-user purchase rehearsal against a **fresh disposable local/staging database**, not the user's database or the live participant dataset: `python3 ops/loadtest.py http://127.0.0.1:<isolated-port> flow --users 10`. Confirm `complete purchases: 10/10`; the script's exit code alone does not establish success. This local check does not prove Render Free response times.
- Verify the deployed commit, public secure session/CSRF flow, fresh worker heartbeat, restart persistence and the normal booking departure on Render itself. Keep moderated recovery checks separate from participant records.
- Record results and limitations in [verification evidence](verification-report.md). Actual participant observations belong in the usability-study records.

## Free-tier boundaries

The web service sleeps after about **15 minutes without inbound traffic**. Its cohosted worker sleeps with it, delaying proactive notices, watches and scheduled work until the service wakes. Lazy expiry checks still protect reservation/payment flows, but this is not an always-running worker. Cold starts can take about a minute or longer. Warm the service before each test session.

Free PostgreSQL expires after **30 days** and has **no automatic backups**. Treat this as temporary hosting, record its actual expiry date after creation, and arrange a private export of needed study records before expiry. External database access is disabled by this Blueprint; plan an approved, restricted export rather than opening access to everyone. See [backup/restore](backup-restore.md) for the general procedure.

Render Free blocks outbound SMTP ports 25, 465 and 587. This deployment does not configure a working mail-delivery provider, so **email verification and password-reset inbox delivery are excluded from this study**. Their presence in the application does not imply delivery works on this host. See [account email](account-email.md) for separate setup requirements.

Capacity and response time on the free instance remain to be measured. Do not promise ten simultaneous users a particular latency before the hosted checks. No real supplier API, charge, refund or valid ticket is enabled by this deployment.

## Deployment record — 11 November 2026

| Check | Observed result |
| --- | --- |
| Public HTTPS URL / deployed commit | https://doedu-kazakhstan-test-x3wv.onrender.com/ · `7c2d4bc6cd5e` |
| Ready response / worker freshness | HTTP 200 JSON; database, migrations and worker all `ok` |
| Ten-user disposable rehearsal | 10/10 concurrent purchases; integrity passed; scratch database removed |
| Mobile browser walkthrough | 390px emulation passed; physical phone/mobile-data check remains for moderator |
| Restart persistence | Authenticated session, confirmed smoke booking and saved Kazakhstan plan preserved after repeat deployment |
| PostgreSQL creation / expiry date | Created 11 November 2026 14:57 UTC; expires 11 December 2026 14:57 UTC |
| Moderator and participant data preparation | Private moderator credentials stay in Render; participants register independently; shared recovery tasks require preparation |

Render identifiers for operations: Blueprint `exs-dbq848afngtc73cv80p0`, web service `srv-dbq85cgu01pc73a3leq0`, PostgreSQL `dpg-dbq84ngu01pc73a3im00-a`. Both Blueprint Auto Sync and web auto-deployment are off. [Service dashboard](https://dashboard.render.com/web/srv-dbq85cgu01pc73a3leq0). No custom domain or paid service was added.

# Free Render usability-test deployment

Prepared for **12 November 2026, ten participants**. This is a temporary hosted demonstration with synthetic transport, payments, refunds and confirmations. Kazakhstan cities and private plans do not represent live supplier availability or valid tickets. See [Kazakhstan scope](kazakhstan.md) and [business rules](business-rules.md).

## Latest search and passenger-label increment

The current source includes Kazakhstan arrive-by search, strict accessibility, whole-party KZT budget filters, saved/search-link restoration and readable generated route labels. Local checks passed: 373 backend tests, 35 frontend unit tests, build/lint and 57 browser scenarios including PWA. Both plan migrations (`0006` and the `0007` database-default repair) were applied locally after private backups, with existing records preserved. All five [CI jobs at `88122e0`](https://github.com/Alizhan2/Project-X/actions/runs/43061797052) passed. The public site still awaits the owner’s manual deployment; the records below describe the earlier observed public release, not this increment.

## New Kazakhstan booking increment — pending deployment

The owner clarified that the next product remains a **demo without external APIs**. Local source now supports all 90 cities in the official KATO release of 4 November 2026, multilingual lookup/aliases and generated direct bus/train search, booking, payment/refund and recovery in KZT and Kazakhstan time. See the [source and generation rules](kazakhstan.md). Prices, durations, schedules, fictional stops and accessibility are invented examples; real city geography is not evidence of a real service.

The updated launcher adds missing Kazakhstan geography and scoped operator accounts through `prepare_kazakhstan_demo` after locked migrations and the enabled guarded legacy bootstrap. It generates dated services only for selected pairs and dates. This additive preparation preserves existing study accounts, passwords, memberships, bookings and legacy EUR/Berlin records; it requires no new migration. It is not a reset of the current hosted database.

Final combined local checks passed: **353 backend tests**, **29 frontend unit tests**, frontend **build/lint**, **54 Playwright browser scenarios** and **2 separately enabled PWA scenarios**. These supersede the earlier focused-run counts. On 11 November, [all five CI jobs](https://github.com/Alizhan2/Project-X/actions/runs/43055303104) passed for `44cdde6efb584c5f57bcc56cd0c9c7370e151a00`. Public deployment is awaiting the owner’s manual update in Render after native Chrome controls timed out. **The public records below still describe `e2e4b5a3c649`, before the 90-city booking work.** Do not report the new Kazakhstan scenario as publicly tested until its deployed commit and walkthrough are recorded.

## Current status and evidence

The dedicated study deployment is **live**: [Kazakhstan planning](https://doedu-kazakhstan-test-x3wv.onrender.com/) and [fictional booking](https://doedu-kazakhstan-test-x3wv.onrender.com/demo). The current revision is `e2e4b5a3c6493ed9dd516a28f71b86f0b52d00ed`, with all five CI jobs green, deployed at 15:30 UTC on 11 November. Initial deployment became live at 15:01 UTC; a persistence-check deployment became live at 15:08 UTC. Both resources are free in the confirmed My Workspace. The unrelated `sanapath-ai` service was not changed.

Public checks passed: HTTPS 200, HTTP-to-HTTPS 301, staged HSTS and CSP, ready JSON with database/migrations/worker all `ok`, EN/RU/KK home pages, a 390px mobile viewport without horizontal overflow, independent registration, search, five-minute reservation, simulated payment, valid PDF/calendar downloads, Kazakhstan plan saving and parameter-only sharing. Anonymous booking access returned 403. After repeat deployment, the same authenticated session could read its confirmed booking, the saved Kazakhstan plan survived reload, and the worker was fresh. Logs confirmed the bootstrap was a no-op. The single synthetic smoke account/booking/plan are verification records, not participant observations.

After the persistence check, only the synthetic smoke booking was cancelled. Its snapshotted policy quoted EUR 3.50; repeating cancellation retained one refund, and the hosted worker completed it. This released the smoke booking's place before the participant session.

These are browser-emulation checks, not a physical-phone/mobile-data study. Moderated recovery scenarios still require preparation. The [validated CI run](https://github.com/Alizhan2/Project-X/actions/runs/43047350403) passed all five jobs for `e2e4b5a3c6493ed9dd516a28f71b86f0b52d00ed`: backend, frontend, security, container and e2e. The browser job installs the package-pinned Chromium, verifies it launches, and runs the unchanged application suite. This uses the hosted runner's existing system libraries and avoids the Ubuntu apt DNS failures observed in the earlier runs. Later documentation-only commits do not change the validated release.

### Bounded public capacity check

A single ten-account batch completed **10/10 registrations**, with p95 **47.9 seconds** under simultaneous registration on the free CPU. **Three purchase/payment flows were verified**, cancelled, and refunded successfully. Seven Python urllib search responses were incomplete; matching search entries were absent from the application logs. Their origin remains unresolved, so the public ten-user purchase test is **not a pass**. Subsequent individual searches returned valid JSON in about 1.2–1.4 seconds. A separate real Chromium check completed **10/10 simultaneous search fetches**, all with 14 routes, in 0.34–2.41 seconds. No application restart, error event or memory exhaustion was observed during the batch.

Create accounts ahead of the session or stagger registration; a simultaneous sign-up task measures this free-tier CPU limit as well as the interface. The earlier disposable native ten-user purchase rehearsal passed, but it does not establish public purchase concurrency. All three created capacity-test bookings were cancelled; original seeded recovery fixtures were untouched. Exclude accounts prefixed `hosted-smoke-` and `hosted-capacity-`, and their bookings/plans, from actual participant observations.

For the earlier `e2e4b5a3c649` deployment preparation, all 326 backend tests passed, including eleven focused runtime/bootstrap tests. A disposable native rehearsal using production settings completed ten simultaneous register/search/reserve/pay flows (10/10), passed the integrity check, and preserved all 18 account password hashes and 14 bookings after a full launcher restart. Only the documented staged-HSTS warnings W005/W021 remained. The temporary database and role were removed. These historical results establish local behaviour for that earlier revision, not current Kazakhstan-increment latency or public HTTPS/phone behaviour.

## Resources and startup

The Blueprint explicitly selects **`plan: free` for both resources**, in Frankfurt:

| Resource | Blueprint name | Purpose |
| --- | --- | --- |
| Docker web service | `doedu-kazakhstan-test` | Built React app, Django API and one cohosted background worker |
| PostgreSQL 17 | `doedu-usability-db` | Dedicated synthetic study data; external database connections disabled |

Do not copy the local database, accounts, personal information or local environment files into this database. Do not reuse another application's database. If this workspace already has a free PostgreSQL database, resolve that constraint before deployment; never delete or upgrade an unrelated resource to make room.

The startup launcher derives the exact public hostname, HTTPS origin and listening port from Render's environment. A stable Django signing key is derived from the generated `DOEDU_SECRET_SEED`; secrets are not printed. The updated sequence runs locked migrations, the explicitly enabled hosted legacy bootstrap, then `prepare_kazakhstan_demo` before supervising Gunicorn and `run_worker`. If either process exits, its sibling is stopped so Render can restart the pair. The Kazakhstan preparation step takes effect when the new revision is actually deployed.

Bootstrap requires a deployed demo launch, explicit `DOEDU_BOOTSTRAP_DEMO=true`, an empty application database and distinct generated passenger/operator and administrator passwords. It seeds fictional schedules and demonstration bookings once, then records a durable completion marker. Later starts preserve accounts, passwords and bookings. An unmarked database containing application data is refused. Do not clear the marker, run destructive `seed_demo`, or enable production demo-reset tools to bypass a refusal.

Kazakhstan preparation is a separate additive command: it can add missing 90 hubs, 180 fictional bus/rail stops, transfers, operators and a policy to the existing marked study database. It creates `ops.kzbus@doedu.test` and `ops.kzrail@doedu.test` with operator roles scoped to the corresponding bus/rail operator. Hosted `DEMO_USER_PASSWORD` must be private and at least 16 characters. Existing passwords, roles and memberships remain unchanged, including revoked access; conflicting or missing memberships are reported for administrator review. No public well-known password is installed by this hosted path.

This short study uses Render's database-owner credential for migrations and runtime. It does **not** establish the separate migration/runtime roles or database-level least privilege described in the general [deployment guide](deployment.md). Do not describe this as a complete production deployment or enable commercial mode.

## Deploy after reviewing the plan

1. Review `render.yaml` and confirm that the plan contains only the two Doedu resources above, both free, with no paid worker, disk, cron service or database upgrade.
2. In Render, create a Blueprint from [Alizhan2/Project-X](https://github.com/Alizhan2/Project-X), branch `main`. Check the proposed resource changes before approving their creation. Stop if Render proposes billing or a change to an existing unrelated service.
3. Keep automatic application deployment disabled: `autoDeployTrigger: "off"`. During the study, deploy a reviewed revision manually; review and approve Blueprint changes separately. A new commit alone should not become a surprise study release.
4. Allow the initial image build, database provisioning, migrations and bootstrap to finish. Inspect diagnostics privately if startup fails; do not paste credentials, environment dumps or database URLs into chat or GitHub.
5. Open the service's assigned HTTPS `onrender.com` URL. After the new revision is verified, use `/` for Kazakhstan demo booking/planning and `/demo` for legacy acceptance fixtures. The currently recorded earlier release still offers Kazakhstan planning only. A custom domain is not needed for the test.
6. Record the actual URL, deployed commit, date and successful checks below only after observing them. A prepared Blueprint or green local suite is not a deployment result.

Render manages HTTPS for the assigned hostname. Consult the official [Blueprint reference](https://render.com/docs/blueprint-spec) and [free-service limits](https://render.com/docs/free) if the platform's validation differs from this plan.

## Private accounts and ten-user tasks

Retrieve `DEMO_USER_PASSWORD` **only from the web service's Environment page in Render Dashboard** when the moderator needs a seeded account. Never put its value in chat, committed documentation or a public test link. This password covers seeded passengers and operators; operators can modify shared schedules, so moderators retain those credentials.

The administrator `admin@doedu.test` has the separate generated `DEMO_ADMIN_PASSWORD`. Never give participants the administrator password or use an administrator account as a shared passenger login. See [seeded scenario accounts](demo-data.md) for the individual passenger/operator identities.

The updated Kazakhstan setup adds `ops.kzbus@doedu.test` and `ops.kzrail@doedu.test` for moderators. The last observed public release predates these accounts. Use them after the additive setup and deployed revision are verified, and confirm each account can see only its own operator's services.

Each participant should use a separate account. Create accounts ahead of the session or stagger registration: the earlier ten-account burst reached p95 47.9 seconds on the free CPU. The study Blueprint raises bounded registration/login limits for shared Wi-Fi without disabling abuse controls. Avoid unnecessary real personal data, and do not ask for real payment details.

After the new release is verified, the primary booking task is **Almaty → Astana**, one passenger per account, with a future date in Kazakhstan time; for the 12 November session, an example is **14 November 2026, depart after 06:00 (UTC+5)**. Compare the generated bus/train offers, reserve one, exercise the payment simulator and download PDF/calendar copies. A generated bus starts with 40 seats and a train with 100; check current availability before admitting the group. Include a non-capital pair such as **Arys → Shu** to exercise the expanded directory. The displayed fare and duration are generated examples, so use the current quote rather than assuming a real price or journey time.

Legacy scenarios remain under `/demo`: **NG-BUS → RV-BUS, tomorrow at 16:00 in Europe/Berlin**, for ordinary legacy bookings; GL1 07:30, GL2 11:30 and VC1 10:00 are intentional scarce/sold-out/cancelled fixtures. Retain these separately for old special tasks, including the existing multimodal missed-connection scenario. A direct Kazakhstan service delay alone is informational; cancelling its departure can exercise replacement/cancellation. Operator changes affect every booking on the same departure, so use a dedicated departure/account for moderated disruption tasks.

Recovery, payment and refund fixtures are shared, stateful and effectively single-use. Operator delays/cancellations affect every participant booked on that departure. Run those tasks one at a time under moderator control, with separate prepared departures or an explicitly planned reset of a disposable study database between sessions. Never reset while participants are active. Follow the [demo script](demo-script.md); do not report generated accounts or rehearsals as actual participant responses.

## Before admitting participants

- Open the HTTPS site at least several minutes beforehand and allow a minute or more for a cold start. Confirm `/api/health/ready/` returns the expected database/migration result and that the worker heartbeat is fresh; also check `/api/health/live/`.
- On a phone using mobile data, verify the deployed revision, all three languages, searches for a regional capital and a non-capital city, Kazakhstan booking/payment/refund, operator changes, plan/sharing and PDF/calendar downloads. Verify KZT and UTC+5 on these Kazakhstan flows and retain simulation labels. Check legacy `/demo` only for tasks that require its preserved fixtures.
- Run a ten-user purchase rehearsal against a **fresh disposable local/staging database**, not the user's database or the live participant dataset: `python3 ops/loadtest.py http://127.0.0.1:<isolated-port> flow --users 10`. Confirm `complete purchases: 10/10`; the script's exit code alone does not establish success. This local check does not prove Render Free response times.
- Verify the deployed commit, public secure session/CSRF flow, fresh worker heartbeat, restart persistence and the normal booking departure on Render itself. Keep moderated recovery checks separate from participant records.
- Record results and limitations in [verification evidence](verification-report.md). Actual participant observations belong in the usability-study records.

## Free-tier boundaries

The web service sleeps after about **15 minutes without inbound traffic**. Its cohosted worker sleeps with it, delaying proactive notices, watches and scheduled work until the service wakes. Lazy expiry checks still protect reservation/payment flows, but this is not an always-running worker. Cold starts can take about a minute or longer. Warm the service before each test session.

Free PostgreSQL expires after **30 days** and has **no automatic backups**. Treat this as temporary hosting, record its actual expiry date after creation, and arrange a private export of needed study records before expiry. External database access is disabled by this Blueprint; plan an approved, restricted export rather than opening access to everyone. See [backup/restore](backup-restore.md) for the general procedure.

Render Free blocks outbound SMTP ports 25, 465 and 587. This deployment does not configure a working mail-delivery provider, so **email verification and password-reset inbox delivery are excluded from this study**. Their presence in the application does not imply delivery works on this host. See [account email](account-email.md) for separate setup requirements.

The earlier public capacity results above apply to the previous release and network; they do not establish latency or ten-user purchase concurrency for the new Kazakhstan increment. Measure the new deployment before promising a response time. No real supplier API, charge, refund or valid ticket is enabled by this deployment.

## Deployment record — 11 November 2026

| Check | Observed result |
| --- | --- |
| New 90-city local checks | Passed: 353 backend, 29 frontend unit, build/lint, 54 browser + 2 separate PWA scenarios |
| New 90-city CI / public release | All five CI jobs passed at `44cdde6`; public deployment/walkthrough awaiting the owner’s manual update |
| Public HTTPS URL / deployed commit | https://doedu-kazakhstan-test-x3wv.onrender.com/ · `e2e4b5a3c649` |
| Ready response / worker freshness | HTTP 200 JSON; database, migrations and worker all `ok` |
| Ten-user disposable rehearsal | 10/10 concurrent purchases; integrity passed; scratch database removed |
| Public capacity rehearsal | 10/10 registrations, p95 47.9s; 10/10 concurrent browser searches, max 2.41s; full ten-user purchases not established (3 verified, 7 interrupted search responses) |
| Mobile browser walkthrough | 390px emulation passed; physical phone/mobile-data check remains for moderator |
| Restart persistence | Authenticated session, confirmed smoke booking and saved Kazakhstan plan preserved after repeat deployment |
| PostgreSQL creation / expiry date | Created 11 November 2026 14:57 UTC; expires 11 December 2026 14:57 UTC |
| Moderator and participant data preparation | Private moderator credentials stay in Render; participants register independently; shared recovery tasks require preparation |

Render identifiers for operations: Blueprint `exs-dbq848afngtc73cv80p0`, web service `srv-dbq85cgu01pc73a3leq0`, PostgreSQL `dpg-dbq84ngu01pc73a3im00-a`. Both Blueprint Auto Sync and web auto-deployment are off. [Service dashboard](https://dashboard.render.com/web/srv-dbq85cgu01pc73a3leq0). No custom domain or paid service was added.

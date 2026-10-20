# Production readiness: assessment and checklist
**Status (see bottom): ready for a hosted demonstration once the listed decisions are made and the remaining host checks are run; not commercially ready.**

## Confirmed working (evidence in docs/verification-report.md)
Search/compare multimodal journeys · reservation, simulated payment, cancellation and refund rules · operator tools · notifications · disruption recovery with replacement offers · idempotency and
oversell-proofing under real concurrency · durable background jobs that survive crashes, restarts and DB outages · least-privilege DB with append-only audit/payment history · structured redacted logs, request
ids, health/readiness/metrics, integrity tooling · hash-locked dependencies · reproducible bring-up from an empty database · automated accessibility and keyboard checks.

## Release blockers for the *hosted demonstration*
| # | Blocker | Owner | Status |
|---|---|---|---|
| 1 | Hosting provider/region, domain + TLS ingress not chosen | you | **open decision** (docs/deployment.md options) |
| 2 | Container image build: **done in CI** (builds, non-root, liveness OK). The full compose stack as containers has not been run | needs Docker host | partly done; remaining: first `docker compose up` on the target host |
| 3 | Logical backup and restore rehearsal | local PostgreSQL 17.11 | **RUN locally 2026-10-20**; repeat on target storage |
| 4 | Public registration policy: optional verification/reset implemented; hosted SMTP not connected | you | **open decision** (docs/security.md): keep closed (`REGISTRATION_ENABLED=false`) or accept for a synthetic demo |
| 5 | Alert recipient / on-call and backup owner named | you | open |
Full container runtime remains unverified; local PostgreSQL client tools were used for backup verification.

## Operational gaps (not blocking a demo, needed soon after)
Independent pen test · monitoring/alerting connected (needs your approval of a service) · off-host backup storage configured · Django 6.1 → LTS migration plan (support ends 2027-04-30) ·
real hardware load test · manual assistive-technology testing · retention/anonymisation job · MFA for admins · e-mail notifications.

## Product decisions still needed
Who is the first real audience of the demo? Registration open or invite-only? Hosting budget and region (data residency)? Who administers accounts and answers support? Whether the demo may show
operator views to the public (admin accounts must never be shared). Commercial path: docs/commercial-readiness.md.

## Proposed deployment architecture
docs/deployment.md (single image: web + worker + one-shot db-roles/migrate jobs; PostgreSQL 17; TLS ingress; off-host backups).

## Checklist
| Area | Item | State |
|---|---|---|
| Config | env-driven; startup validation refuses unsafe production config; launch mode `commercial` refuses to start | done, tested |
| Config | DEBUG off, explicit hosts/origins, secure cookies, no CORS | done, tested |
| Config | HSTS with rollout plan (1 h start; preload off) | done (plan), needs real HTTPS to exercise |
| Runtime | gunicorn (not dev server), non-root image, read-only FS, graceful shutdown, timeouts, restart policies | configured; container **not run**; gunicorn/graceful/timeouts **run** locally |
| Runtime | liveness/readiness without sensitive data; release id visible | done, run |
| Data | constraints, locking, idempotency, snapshots preserved; integrity checker | done, run |
| Data | migrations: advisory-locked single run, additive policy, concurrent index | done, run |
| Data | DB roles least privilege; history append-only | done, run |
| Jobs | durable, multi-worker safe, bounded retries, visible failures, restart/outage safe | done, run |
| Security | rate limits, lockout, headers/CSP, error sanitisation, secrets scan | done, run; ingress limits still required |
| Privacy | inventory, minimisation; retention/deletion defined as requirements | documented; deletion **not built** |
| Observability | JSON logs, request ids, metrics, audit, runbook | done; external monitoring **not connected** |
| Backups | scripts + restore procedure + measured rehearsal | physical and logical backup/restore rehearsals run locally |
| CI/CD | pipeline (tests, deploy gate, e2e on prod-like stack, scans, container) + release procedure | **executed on a GitHub runner: all 5 jobs green at `ac46440`** (release.yml never triggered) |
| Commercial | backlog separate; commercial mode blocked | documented |

## Verdict
* **Hosted demonstration**: **ready to proceed to deployment approval** (blockers 1–5 are decisions/verification steps, not defects).
* **Staging**: ready now (the production-like stack runs from an empty database in minutes).
* **Commercial operation**: **blocked**: no authorised transport integration, no real payment processing, SMTP delivery not commissioned; verification optional, no independent security review, no legal/support set-up (docs/commercial-readiness.md).

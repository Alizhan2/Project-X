# Handoff (state when work stopped)
Updated at the end of the autonomous session. Nothing here contains secrets.

## State
* Code: committed locally as `1fbe044` (+ this note), branch `main`. **Not pushed.** Tree clean.
* Application: MVP stages 0–7 + production preparation. Final local evidence (docs/verification-report.md): 174 backend tests, 23 browser tests (dev and production-like stack), clean-checkout rehearsal with hash-locked install, load/contention/restart/outage/restore rehearsals.
* Local processes left running (development only, safe to leave or stop): PostgreSQL dev cluster on 127.0.0.1:5432 (`~/.doedu-tools/pg`, database `doedu`, seeded synthetic data), Vite on :5173, Django `runserver` on :8000. No worker is running. Throwaway staging clusters/databases were deleted.
* No deployment operation was started: no server, domain or DNS was provided, so nothing was changed anywhere remote.

## Blockers (need you; not retried)
1. **Push to https://github.com/Alizhan2/Project-X.git**: this Mac has no GitHub credential (no `gh`, no SSH key loaded, keychain empty for github.com). Run `! git push -u origin main` yourself and authenticate. Check first whether the repo is public (the docs include the synthetic demo password).
2. **Deployment target**: needed: server IP/hosting project + OS; SSH username (key via your agent: `ssh-add` first, the agent currently holds none); hostname (e.g. app.example.com) + DNS provider; whether the server already runs other apps / uses ports 80/443; whether Docker may be installed.

## Next actions (in order, once unblocked)
1. Push. 2. Inspect the server read-only (OS, disk, ports, existing proxy/apps) before any change. 3. Follow docs/deployment.md + docs/release-procedure.md: build image, `db-roles` → `migrate` → `web` + `worker`, `sync_demo_schedule`, create the first admin with `createsuperuser`. 4. DNS record for the agreed hostname only; HTTPS via the proxy's automatic certificates; HSTS at 1 hour. 5. Public verification in a real browser (checklist in the deployment request), first backup + `ops/verify-restore.sh`, then update docs/runbook.md with verified steps.

## Still unexecuted anywhere (do not assume they work)
Docker image build and compose stack, GitHub Actions workflows, `pg_dump` backup/restore scripts, real TLS/HSTS behind a proxy, independent security test, manual screen-reader test.

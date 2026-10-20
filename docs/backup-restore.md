# Backups and tested restore
A backup counts as verified only after a restore succeeded and the restored data passed the checks below.

## What is backed up, where, by whom
* **Scope**: the whole PostgreSQL database (bookings and their snapshots, payments, refunds, audit, jobs, users, demo/operational data). There are no files to back up (no uploads); secrets live in the secret store, **not** in backups.
* **Mechanism (container deployment)**: `ops/backup.sh` = `pg_dump --format=custom` daily (`backup` service, `BACKUP_INTERVAL_HOURS`), checksum file next to each dump, retention `BACKUP_RETENTION_DAYS` (14). Managed PostgreSQL: enable the provider's automated backups + point-in-time recovery and *also* keep a periodic logical dump.
* **Location**: a volume that is **not** on the database host's only disk; copy dumps off-host (object storage with write-only credentials for the uploader, encryption at rest, access limited to named administrators). Backups contain personal data (names, contact e-mails): treat them like the database.
* **Responsibility** (to be assigned by the product owner): who checks the daily result, who performs restores, who holds storage credentials.

## Restore procedure
1. Provision an **empty** PostgreSQL 17 database (never restore over a live one).
2. `ops/restore.sh <dump>`: verifies the checksum, refuses a non-empty target, runs `pg_restore`.
3. Create roles/privileges: `manage.py setup_db_roles`, then `manage.py safe_migrate` (idempotent; applies any newer migrations; re-applies history protection).
4. Verify: `manage.py check_integrity` (capacity vs reservations, payments vs bookings, refunds ≤ paid), `manage.py state_fingerprint` (compare with the value recorded at backup time if available), `manage.py ops_status`.
5. Point the application at it; check `/api/health/ready/`; run the smoke test (docs/release-procedure.md §5).
`ops/verify-restore.sh <backup dir>` automates 1–4 into a scratch database; schedule it (weekly) and alert on failure.

## Measured restore rehearsal (this repository, local)
**Historical rehearsal (superseded for logical tooling on 2026-10-20; see local-improvements.md):** At that time pg_dump tools were unavailable. What was executed is a
*cold physical* backup and restore of a separate PostgreSQL 17.10 staging cluster (stopped, data directory archived), which verifies the *data-level* restore property
(identical state, consistent invariants, application reconnects) but not the `pg_dump` tooling. That earlier result did not verify logical tooling; the later rehearsal below does.

| Step | Result |
|---|---|
| State before backup | 8 bookings, 11 legs, 10 reservations, 4 payments, 434 departures, 14 audit records; fingerprint `b1ee88d4…`; `check_integrity` OK |
| Backup | stopped cluster, tar.gz 14 MB, SHA-256 verified; ~1 s |
| Disaster | one more booking cancelled **after** the backup, then `DROP DATABASE`; readiness 503 |
| Restore | fresh data directory from the archive, cluster started on the same port; application **recovered without restart** |
| Restore time | 1 s (tiny dataset: not representative of a real database) |
| Verification | state fingerprint **identical** to the pre-backup fingerprint (so the post-backup change is correctly absent); `check_integrity` OK; 0 capacity inconsistencies; 0 failed jobs |

## Targets proposed for discussion (not achieved guarantees)
| Objective | Proposal for the hosted demo | Note |
|---|---|---|
| RPO (data you can lose) | ≤ 24 h with daily dumps; ≤ 5 min with managed PITR | rehearsal shows a post-backup change is lost, as expected |
| RTO (time to recover) | ≤ 2 h including provisioning | restore time grows with data size: re-measure with real volume |
| Restore drill | monthly full drill, weekly automated `verify-restore.sh` | record date and result in the release checklist |

## Local logical rehearsal, 2026-10-20
`ops/backup.sh`, `restore.sh`, and `verify-restore.sh` ran using PostgreSQL 17.11 clients from the official Postgres.app release, against the existing PostgreSQL server without Docker. Restoration used a separate scratch database which was dropped afterward. Integrity passed. Production database storage was not overwritten.

Scripts now support both `sha256sum` (Linux) and `shasum -a 256` (macOS), unique backup filenames, failure cleanup, transactional restoration and rejection of a target with existing user relations. Use `PYTHON=/absolute/path/to/backend/.venv/bin/python` for the rehearsal if `python` is not on PATH. Keep libpq connection variables set and run verify-restore from `backend/`. Repeat the rehearsal on actual hosted storage; off-host copies, schedules and recovery objectives remain operational work.

On this Mac, the checked client binaries are retained at `~/.doedu-tools/postgres-client-17/bin` (outside Git). Use `export PATH="$HOME/.doedu-tools/postgres-client-17/bin:$PATH"`. This does not replace or restart the existing database server. Export `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, and `PGDATABASE` from the corresponding `POSTGRES_*` environment variables without printing them. Choose a private `BACKUP_DIR` before running backup.sh; credentials and dump files must stay out of Git.

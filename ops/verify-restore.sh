#!/bin/sh
# Restore rehearsal: restore the newest backup into a scratch database and run the application's integrity check.
# Needs createdb/dropdb rights and the app image's `manage.py`. Usage: ops/verify-restore.sh /backups
set -eu
dir="${1:?usage: verify-restore.sh <backup dir>}"
latest=$(ls -1t "$dir"/doedu-*.dump | head -1)
scratch="doedu_verify_$(date -u +%Y%m%d%H%M%S)_$$"
createdb "$scratch"
trap 'dropdb --if-exists "$scratch"' EXIT
PGDATABASE="$scratch" "$(dirname "$0")/restore.sh" "$latest"
POSTGRES_HOST="${PGHOST:-localhost}" POSTGRES_PORT="${PGPORT:-5432}" POSTGRES_USER="$PGUSER" POSTGRES_PASSWORD="${PGPASSWORD:-}" POSTGRES_DB="$scratch" "${PYTHON:-python}" manage.py check_integrity
echo "restore verified from $latest"

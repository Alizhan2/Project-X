#!/bin/sh
# Restore rehearsal: restore the newest backup into a scratch database and run the application's integrity check.
# Needs createdb/dropdb rights and the app image's `manage.py`. Usage: ops/verify-restore.sh /backups
set -eu
dir="${1:?usage: verify-restore.sh <backup dir>}"
latest=$(ls -1t "$dir"/doedu-*.dump | head -1)
scratch="doedu_verify_$(date -u +%Y%m%d%H%M%S)"
createdb "$scratch"
trap 'dropdb --if-exists "$scratch"' EXIT
PGDATABASE="$scratch" "$(dirname "$0")/restore.sh" "$latest"
POSTGRES_DB="$scratch" python manage.py check_integrity
echo "restore verified from $latest"

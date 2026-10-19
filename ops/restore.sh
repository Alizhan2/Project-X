#!/bin/sh
# Restore a backup made by backup.sh into an EMPTY database. Refuses to touch a database that already has tables.
# Usage: PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=target ops/restore.sh /backups/doedu-<stamp>.dump
set -eu
file="${1:?usage: restore.sh <backup.dump>}"
( cd "$(dirname "$file")" && sha256sum -c "$(basename "$file").sha256" )      # integrity of the backup file itself
tables=$(psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$tables" = "0" ] || { echo "refusing: target database is not empty ($tables tables)"; exit 1; }
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$PGDATABASE" "$file"
echo "restore finished; now run: python manage.py check_integrity"

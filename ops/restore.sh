#!/bin/sh
# Restore a backup made by backup.sh into an EMPTY database. Refuses to touch a database that already has tables.
# Usage: PGHOST=... PGUSER=... PGPASSWORD=... PGDATABASE=target ops/restore.sh /backups/doedu-<stamp>.dump
set -eu
. "$(dirname "$0")/checksum.sh"
: "${PGDATABASE:?set PGDATABASE explicitly to the empty target database}"
file="${1:?usage: restore.sh <backup.dump>}"
( cd "$(dirname "$file")" && checksum -c "$(basename "$file").sha256" )      # integrity of the backup file itself
tables=$(psql -X -v ON_ERROR_STOP=1 -tAc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'")
[ "$tables" = "0" ] || { echo "refusing: target database is not empty ($tables tables)"; exit 1; }
pg_restore --single-transaction --no-owner --no-privileges --exit-on-error --dbname="$PGDATABASE" "$file"
echo "restore finished; now run: python manage.py check_integrity"

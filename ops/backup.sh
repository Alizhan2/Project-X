#!/bin/sh
# Logical backup of the Doedu database (custom format, compressed) with a checksum and retention pruning.
# Uses pg_dump, so it needs the PostgreSQL client tools (present in the postgres:17 image used by the backup service).
# Credentials come from the standard libpq variables (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE): never from arguments.
# NOTE: authored without pg_dump available locally; its first real run MUST be followed by ops/verify-restore.sh.
set -eu
: "${BACKUP_DIR:=/backups}" "${BACKUP_RETENTION_DAYS:=14}"
umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$BACKUP_DIR/doedu-$stamp.dump"
tmp="$out.partial"
pg_dump --format=custom --compress=6 --no-owner --no-privileges --file="$tmp"
mv "$tmp" "$out"                                   # a file without .partial is complete
( cd "$BACKUP_DIR" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256" )
find "$BACKUP_DIR" -name 'doedu-*.dump*' -mtime +"$BACKUP_RETENTION_DAYS" -delete
echo "backup written: $out ($(wc -c < "$out") bytes)"

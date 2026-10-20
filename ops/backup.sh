#!/bin/sh
# Logical backup of the Doedu database (custom format, compressed) with a checksum and retention pruning.
# Uses pg_dump, so it needs the PostgreSQL client tools (present in the postgres:17 image used by the backup service).
# Credentials come from the standard libpq variables (PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE): never from arguments.
# Rehearse recovery with ops/verify-restore.sh; a successful dump alone is not recovery evidence.
set -eu
. "$(dirname "$0")/checksum.sh"
: "${BACKUP_DIR:=/backups}" "${BACKUP_RETENTION_DAYS:=14}"
case "$BACKUP_RETENTION_DAYS" in ''|*[!0-9]*) echo "BACKUP_RETENTION_DAYS must be a nonnegative integer" >&2; exit 1;; esac
umask 077
mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
tmp=$(mktemp "$BACKUP_DIR/.doedu-$stamp-XXXXXX")
name=${tmp##*/}
out="$BACKUP_DIR/${name#.}.dump"
trap 'rm -f "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
pg_dump --format=custom --compress=6 --no-owner --no-privileges --file="$tmp"
mv "$tmp" "$out"                                   # only files with .dump are complete
( cd "$BACKUP_DIR" && checksum "$(basename "$out")" > "$(basename "$out").sha256" )
find "$BACKUP_DIR" -name 'doedu-*.dump*' -mtime +"$BACKUP_RETENTION_DAYS" -delete
echo "backup written: $out ($(wc -c < "$out") bytes)"

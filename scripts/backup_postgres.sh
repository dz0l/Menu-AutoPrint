#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_DAYS="${BACKUP_INTERVAL_DAYS:-10}"
BACKUP_KEEP="${BACKUP_KEEP:-3}"

mkdir -p "$BACKUP_DIR"

backup_once() {
  stamp="$(date +%Y%m%d-%H%M%S)"
  file="$BACKUP_DIR/menu_autoprint-$stamp.sql.gz"
  echo "Creating PostgreSQL backup: $file"
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$file"

  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'menu_autoprint-*.sql.gz' \
    | sort -r \
    | awk "NR>${BACKUP_KEEP}" \
    | xargs -r rm -f
}

while true; do
  backup_once
  sleep "$((BACKUP_INTERVAL_DAYS * 24 * 60 * 60))"
done

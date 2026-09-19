#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_DAYS="${BACKUP_INTERVAL_DAYS:-10}"
BACKUP_KEEP="${BACKUP_KEEP:-3}"
BACKUP_START_DELAY_SECONDS="${BACKUP_START_DELAY_SECONDS:-300}"
MODE="${1:-once}"

mkdir -p "$BACKUP_DIR"

backup_once() {
  stamp="$(date +%Y%m%d-%H%M%S)"
  tmp_file="$BACKUP_DIR/menu_autoprint-$stamp.sql.gz.partial"
  file="$BACKUP_DIR/menu_autoprint-$stamp.sql.gz"
  echo "Creating PostgreSQL backup: $file"
  # Fail if pg_dump fails even when gzip succeeds.
  set +e
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$tmp_file"
  status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    rm -f "$tmp_file"
    echo "PostgreSQL backup failed (pg_dump/gzip status=$status)" >&2
    return "$status"
  fi
  if [ ! -s "$tmp_file" ]; then
    rm -f "$tmp_file"
    echo "PostgreSQL backup failed: empty dump" >&2
    return 1
  fi
  mv "$tmp_file" "$file"

  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'menu_autoprint-*.sql.gz' \
    | sort -r \
    | awk "NR>${BACKUP_KEEP}" \
    | xargs -r rm -f
}

if [ "$MODE" = "once" ]; then
  backup_once
  exit 0
fi

if [ "$MODE" != "loop" ]; then
  echo "Usage: $0 [once|loop]" >&2
  exit 2
fi

if [ "$BACKUP_START_DELAY_SECONDS" -gt 0 ]; then
  echo "Waiting ${BACKUP_START_DELAY_SECONDS}s before first scheduled PostgreSQL backup"
  sleep "$BACKUP_START_DELAY_SECONDS"
fi

while true; do
  backup_once || echo "Scheduled backup failed; keeping previous copies" >&2
  sleep "$((BACKUP_INTERVAL_DAYS * 24 * 60 * 60))"
done

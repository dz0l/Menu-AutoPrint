#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_INTERVAL_DAYS="${BACKUP_INTERVAL_DAYS:-10}"
BACKUP_KEEP="${BACKUP_KEEP:-3}"
BACKUP_START_DELAY_SECONDS="${BACKUP_START_DELAY_SECONDS:-300}"
MODE="${1:-once}"

mkdir -p "$BACKUP_DIR"

backup_once() {
  local stamp tmp_sql tmp_gz file
  stamp="$(date +%Y%m%d-%H%M%S)"
  tmp_sql="$BACKUP_DIR/menu_autoprint-$stamp.sql.partial"
  tmp_gz="$BACKUP_DIR/menu_autoprint-$stamp.sql.gz.partial"
  file="$BACKUP_DIR/menu_autoprint-$stamp.sql.gz"
  echo "Creating PostgreSQL backup: $file"

  # Sequential stages so a failed pg_dump never publishes or rotates.
  if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=plain \
    --no-owner \
    --no-privileges \
    > "$tmp_sql"; then
    rm -f "$tmp_sql" "$tmp_gz"
    echo "PostgreSQL backup failed: pg_dump error" >&2
    return 1
  fi
  if [[ ! -s "$tmp_sql" ]]; then
    rm -f "$tmp_sql" "$tmp_gz"
    echo "PostgreSQL backup failed: empty dump" >&2
    return 1
  fi
  if ! gzip -c "$tmp_sql" > "$tmp_gz"; then
    rm -f "$tmp_sql" "$tmp_gz"
    echo "PostgreSQL backup failed: gzip error" >&2
    return 1
  fi
  rm -f "$tmp_sql"
  if [[ ! -s "$tmp_gz" ]]; then
    rm -f "$tmp_gz"
    echo "PostgreSQL backup failed: empty archive" >&2
    return 1
  fi
  # Explicit check: with `backup_once || …` bash disables errexit inside the function.
  if ! mv "$tmp_gz" "$file"; then
    rm -f "$tmp_gz"
    echo "PostgreSQL backup failed: publish (mv) error" >&2
    return 1
  fi
  if [[ ! -f "$file" || ! -s "$file" ]]; then
    echo "PostgreSQL backup failed: published file missing" >&2
    return 1
  fi

  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'menu_autoprint-*.sql.gz' \
    | sort -r \
    | awk "NR>${BACKUP_KEEP}" \
    | xargs -r rm -f
  return 0
}

if [[ "$MODE" == "once" ]]; then
  backup_once
  exit 0
fi

if [[ "$MODE" != "loop" ]]; then
  echo "Usage: $0 [once|loop]" >&2
  exit 2
fi

if [[ "$BACKUP_START_DELAY_SECONDS" -gt 0 ]]; then
  echo "Waiting ${BACKUP_START_DELAY_SECONDS}s before first scheduled PostgreSQL backup"
  sleep "$BACKUP_START_DELAY_SECONDS"
fi

while true; do
  backup_once || echo "Scheduled backup failed; keeping previous copies" >&2
  sleep "$((BACKUP_INTERVAL_DAYS * 24 * 60 * 60))"
done

#!/usr/bin/env bash
# Copy SQLite DB with timestamp. Run on the Pi (cron) from project root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="${SMSPI_DB_PATH:-$ROOT/data/smspi.db}"
DEST="${SMSPI_BACKUP_DIR:-$ROOT/data/backups}"

if [ ! -f "$DB" ]; then
  echo "Database not found: $DB" >&2
  exit 1
fi

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
cp "$DB" "$DEST/smspi-${STAMP}.db"
echo "Backup written: $DEST/smspi-${STAMP}.db"

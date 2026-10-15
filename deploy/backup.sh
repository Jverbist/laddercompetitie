#!/usr/bin/env bash
# Dagelijkse back-up van de SQLite-database. Bewaart de laatste 14 dagen.
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/laddercompetitie}"
DB_FILE="${DB_FILE:-$APP_DIR/laddercompetitie.db}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
TARGET="$BACKUP_DIR/laddercompetitie-$(date +%Y%m%d-%H%M).db"

# De sqlite3-backup-API geeft een consistente kopie, ook terwijl de app draait.
"$APP_DIR/.venv/bin/python" - "$DB_FILE" "$TARGET" <<'PY'
import sqlite3
import sys

source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)
target.close()
source.close()
PY

chmod 600 "$TARGET"
find "$BACKUP_DIR" -name 'laddercompetitie-*.db' -mtime +"$KEEP_DAYS" -delete
echo "Back-up opgeslagen: $TARGET"

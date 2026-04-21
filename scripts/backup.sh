#!/bin/bash
# =============================================
# ButterClaw v0.6.3 — Backup Script
# =============================================
# Creates a timestamped backup of:
#   - butterclaw.db (SQLite database)
#   - .env (configuration)
#   - policy/alert/auth state
#
# Usage:
#   ./scripts/backup.sh                    # manual
#   0 3 * * * /opt/butterclaw/scripts/backup.sh  # cron (daily 3 AM)
#
# Output: ./backups/butterclaw-YYYYMMDD-HHMMSS.tar.gz

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_DIR}/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_NAME="butterclaw-${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

# Create backup directory
mkdir -p "$BACKUP_PATH"

# Determine DB path
DB_PATH="${BUTTERCLAW_DB_PATH:-${PROJECT_DIR}/butterclaw.db}"

echo "🦞 ButterClaw Backup — ${TIMESTAMP}"
echo "   Database: ${DB_PATH}"

# 1. SQLite safe backup (using .backup command to avoid corruption)
if [ -f "$DB_PATH" ]; then
    sqlite3 "$DB_PATH" ".backup '${BACKUP_PATH}/butterclaw.db'"
    echo "   ✅ Database backed up"
else
    echo "   ⚠️  Database not found at ${DB_PATH}"
fi

# 2. Configuration
if [ -f "${PROJECT_DIR}/.env" ]; then
    cp "${PROJECT_DIR}/.env" "${BACKUP_PATH}/.env"
    echo "   ✅ .env backed up"
fi

# 3. Version marker
echo "$TIMESTAMP" > "${BACKUP_PATH}/backup_version.txt"
python3 -c "from config import cfg; print(f'ButterClaw v0.6.3 | Instance: {cfg.INSTANCE_ID}')" \
    >> "${BACKUP_PATH}/backup_version.txt" 2>/dev/null || true

# 4. Compress
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

echo "   📦 Archive: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"

# 5. Prune old backups (keep last 7)
ls -1t "${BACKUP_DIR}"/butterclaw-*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
echo "   🧹 Old backups pruned (keeping last 7)"

echo "🦞 Backup complete."

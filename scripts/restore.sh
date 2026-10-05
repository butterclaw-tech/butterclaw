#!/bin/bash
# =============================================
# ButterClaw v0.6.3 — Restore Script
# =============================================
# Restores from a backup archive created by backup.sh
#
# Usage:
#   ./scripts/restore.sh backups/butterclaw-20260420-030000.tar.gz
#
# ⚠️  This OVERWRITES the current database and .env!
#     Stop ButterClaw before restoring.

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup-archive.tar.gz>"
    echo ""
    echo "Available backups:"
    ls -1t backups/butterclaw-*.tar.gz 2>/dev/null || echo "  (none found)"
    exit 1
fi

ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
    echo "❌ Archive not found: $ARCHIVE"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TEMP_DIR=$(mktemp -d)
DB_PATH="${BUTTERCLAW_DB_PATH:-${PROJECT_DIR}/butterclaw.db}"

echo "🦞 ButterClaw Restore"
echo "   Archive: ${ARCHIVE}"
echo "   Target DB: ${DB_PATH}"
echo ""
echo "⚠️  This will OVERWRITE your current database and .env."
read -p "   Continue? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "   Aborted."
    exit 0
fi

# Extract to temp
tar -xzf "$ARCHIVE" -C "$TEMP_DIR"
EXTRACTED=$(ls "$TEMP_DIR")

# Restore database
if [ -f "${TEMP_DIR}/${EXTRACTED}/butterclaw.db" ]; then
    cp "${TEMP_DIR}/${EXTRACTED}/butterclaw.db" "$DB_PATH"
    echo "   ✅ Database restored"
fi

# Restore .env
if [ -f "${TEMP_DIR}/${EXTRACTED}/.env" ]; then
    cp "${TEMP_DIR}/${EXTRACTED}/.env" "${PROJECT_DIR}/.env"
    echo "   ✅ .env restored"
fi

# Cleanup
rm -rf "$TEMP_DIR"

echo "🦞 Restore complete. Restart ButterClaw to apply."

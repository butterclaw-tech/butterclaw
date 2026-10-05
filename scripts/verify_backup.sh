#!/usr/bin/env bash
# =============================================================================
# scripts/verify_backup.sh — Butterclaw v0.9.0
# Verify integrity of all Butterclaw SQLite databases in the backup volume.
#
# Usage:
#   ./scripts/verify_backup.sh [/path/to/data/dir]
#
# Default data dir: /data (Docker volume mount)
# Exit codes:
#   0  — all checks passed
#   1  — one or more checks failed
#
# Changelog:
#   [v0.8.0] Initial: butterclaw.db integrity check
#   [v0.9.0] Added fleet.db integrity check (I-01-fleet: fleet.db in backup)
#             Added I-07-fleet inode isolation assertion
# =============================================================================

set -euo pipefail

DATA_DIR="${1:-/data}"
FAILURES=0

# ── Helper ──────────────────────────────────────────────────────────────────

check_db() {
    local label="$1"
    local db_path="$2"
    local required="${3:-true}"

    echo ""
    echo "=== Checking ${label} ==="
    echo "    Path: ${db_path}"

    if [[ ! -f "${db_path}" ]]; then
        if [[ "${required}" == "true" ]]; then
            echo "  FAIL: ${label} not found at ${db_path}"
            FAILURES=$((FAILURES + 1))
        else
            echo "  WARN: ${label} not found (optional check)"
        fi
        return
    fi

    local result
    result=$(sqlite3 "${db_path}" "PRAGMA integrity_check;" 2>&1) || {
        echo "  FAIL: sqlite3 error running integrity_check on ${label}"
        echo "    Output: ${result}"
        FAILURES=$((FAILURES + 1))
        return
    }

    if [[ "${result}" == "ok" ]]; then
        echo "  PASS: ${label} integrity_check -> ok"
    else
        echo "  FAIL: ${label} integrity_check returned errors:"
        echo "${result}" | sed 's/^/    /'
        FAILURES=$((FAILURES + 1))
    fi

    # WAL size warning
    local wal_path="${db_path}-wal"
    if [[ -f "${wal_path}" ]]; then
        local wal_bytes
        wal_bytes=$(stat -c%s "${wal_path}" 2>/dev/null || stat -f%z "${wal_path}" 2>/dev/null || echo 0)
        if (( wal_bytes > 104857600 )); then
            local wal_mb=$(( wal_bytes / 1048576 ))
            echo "  WARN: ${label} WAL file is ${wal_mb} MB -- consider PRAGMA wal_checkpoint(TRUNCATE);"
        else
            echo "  INFO: WAL ${wal_bytes} bytes (normal)"
        fi
    fi

    local page_count page_size
    page_count=$(sqlite3 "${db_path}" "PRAGMA page_count;" 2>/dev/null || echo "?")
    page_size=$(sqlite3 "${db_path}" "PRAGMA page_size;" 2>/dev/null || echo "?")
    echo "  INFO: ${page_count} pages x ${page_size} bytes/page"
}

# ── I-07-fleet: verify the two DBs are different inodes ─────────────────────

check_db_isolation() {
    local bc_path="${DATA_DIR}/butterclaw.db"
    local fl_path="${DATA_DIR}/fleet.db"

    echo ""
    echo "=== I-07-fleet: DB isolation check ==="
    if [[ ! -f "${bc_path}" || ! -f "${fl_path}" ]]; then
        echo "  SKIP: one or both DBs not present"
        return
    fi

    local bc_inode fl_inode
    bc_inode=$(stat -c%i "${bc_path}" 2>/dev/null || stat -f%i "${bc_path}" 2>/dev/null)
    fl_inode=$(stat -c%i "${fl_path}" 2>/dev/null || stat -f%i "${fl_path}" 2>/dev/null)

    if [[ "${bc_inode}" == "${fl_inode}" ]]; then
        echo "  FAIL: butterclaw.db and fleet.db share the same inode -- I-07-fleet VIOLATED"
        FAILURES=$((FAILURES + 1))
    else
        echo "  PASS: butterclaw.db inode=${bc_inode}, fleet.db inode=${fl_inode} -- distinct files"
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

echo "============================================="
echo " Butterclaw v0.9.0 -- Backup Integrity Check"
echo " Data dir: ${DATA_DIR}"
echo " $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================="

# v0.8: main application DB (required)
check_db "butterclaw.db" "${DATA_DIR}/butterclaw.db" "true"

# v0.9: fleet awareness DB (required per I-01-fleet)
check_db "fleet.db (v0.9 fleet layer)" "${DATA_DIR}/fleet.db" "true"

# I-07-fleet isolation check
check_db_isolation

echo ""
echo "============================================="
if (( FAILURES == 0 )); then
    echo " ALL CHECKS PASSED"
    exit 0
else
    echo " ${FAILURES} CHECK(S) FAILED"
    exit 1
fi

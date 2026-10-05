"""
fleet_db_init.py — Butterclaw v0.9.0
Fleet database schema bootstrap. Runs before server.py binds any routes.

Startup sequence (server.py):
    (1) butterclaw_db_init → (2) fleet_db_init → (3) register routes → (4) bind

Failure mode: Any error here is FATAL — the server does NOT start in a
degraded state with fleet awareness silently disabled.

Invariant: I-07-fleet — fleet.db and butterclaw.db are NEVER co-transacted.
"""

from __future__ import annotations

import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

_FLEET_DB_PATH: str = os.environ.get("BUTTERCLAW_FLEET_DB_PATH", "./fleet.db")
_connection: sqlite3.Connection | None = None

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA wal_autocheckpoint=1000;
PRAGMA busy_timeout=5000;

-- ----------------------------------------------------------------
-- Core fleet tables
-- ----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fleet_agents (
    agent_id          TEXT    PRIMARY KEY,
    display_name      TEXT,
    first_seen_unix   INTEGER NOT NULL,
    last_seen_unix    INTEGER NOT NULL,
    session_count     INTEGER NOT NULL DEFAULT 0,
    taint_count       INTEGER NOT NULL DEFAULT 0,
    reputation_score  REAL    NOT NULL DEFAULT 1.0,
    role              TEXT    NOT NULL DEFAULT 'unknown'
                                CHECK(role IN ('orchestrator','worker','peer',
                                               'unknown','quarantined')),
    parent_agent_id   TEXT    REFERENCES fleet_agents(agent_id),
    deleted_at        INTEGER
);

CREATE TABLE IF NOT EXISTS trust_edges (
    src_agent_id     TEXT    NOT NULL,
    dst_agent_id     TEXT    NOT NULL,
    weight           REAL    NOT NULL DEFAULT 1.0,
    edge_type        TEXT    NOT NULL CHECK(edge_type IN ('spawn','comm','peer')),
    created_unix     INTEGER NOT NULL,
    last_updated_unix INTEGER NOT NULL,
    PRIMARY KEY (src_agent_id, dst_agent_id, edge_type)
);

CREATE TABLE IF NOT EXISTS trust_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    src_agent_id    TEXT    NOT NULL,
    dst_agent_id    TEXT    NOT NULL,
    event_type      TEXT    NOT NULL CHECK(event_type IN (
                                'taint_propagation','comm_observed','spawn_observed')),
    delta           REAL    NOT NULL,
    timestamp_unix  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fleet_baselines (
    agent_id                TEXT    PRIMARY KEY,
    tool_call_distribution  TEXT,   -- JSON blob
    avg_session_duration_s  REAL,
    avg_action_count        REAL,
    last_computed_unix      INTEGER
);

CREATE TABLE IF NOT EXISTS fleet_sentinel_log (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_by            TEXT    NOT NULL CHECK(triggered_by IN (
                                'correlation_event','collusion_event',
                                'scheduled','manual')),
    verdict                 TEXT    NOT NULL CHECK(verdict IN (
                                'ISOLATED','CORRELATED','COLLUDING',
                                'INSUFFICIENT_DATA')),
    confidence              REAL,
    implicated_agent_ids    TEXT,   -- JSON list
    insufficient_reason     TEXT,
    operator_feedback       TEXT    CHECK(operator_feedback IN (
                                'confirmed_true_positive',
                                'confirmed_false_positive',
                                'no_feedback')) DEFAULT 'no_feedback',
    feedback_operator_id    TEXT,
    feedback_timestamp_unix INTEGER,
    follow_up_required      INTEGER NOT NULL DEFAULT 0,
    dry_run                 INTEGER NOT NULL DEFAULT 1,
    escalated_to_guardian   INTEGER NOT NULL DEFAULT 0,
    timestamp_unix          INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    raw_prompt              TEXT,
    raw_response            TEXT
);

CREATE TABLE IF NOT EXISTS correlation_journal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_hash    TEXT    NOT NULL,
    agent_id        TEXT    NOT NULL,
    event_type      TEXT    NOT NULL CHECK(event_type IN ('spatial','temporal')),
    trajectory_hash TEXT,
    tool_name       TEXT,
    tool_args_hash  TEXT,
    timestamp_unix  INTEGER NOT NULL,
    session_id      TEXT    NOT NULL,
    UNIQUE(pattern_hash, agent_id, trajectory_hash, timestamp_unix)
);

CREATE TABLE IF NOT EXISTS quarantine_audit_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id            TEXT    NOT NULL,
    action              TEXT    NOT NULL CHECK(action IN (
                            'flagged','confirmed','token_expired',
                            'conflict','released')),
    operator_id         TEXT    NOT NULL,
    ip_address          TEXT    NOT NULL,
    confirmation_token  TEXT,
    timestamp_unix      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    notes               TEXT
);

-- ----------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_cj_pattern_time
    ON correlation_journal(pattern_hash, timestamp_unix);

CREATE INDEX IF NOT EXISTS idx_fa_reputation
    ON fleet_agents(reputation_score);

CREATE INDEX IF NOT EXISTS idx_te_src
    ON trust_edges(src_agent_id);
"""

# Schema additions to memory tables that live in fleet.db scope.
# Applied as no-op if column already exists (SQLite does not support
# IF NOT EXISTS on ALTER TABLE — caught by exception handling below).
#_MEMORY_SCHEMA_ADDITIONS = [
#    "ALTER TABLE memory_semantic ADD COLUMN scope TEXT NOT NULL DEFAULT 'session' "
#    "CHECK(scope IN ('session','fleet'))",
#    "ALTER TABLE memory_signatures ADD COLUMN source_scope TEXT NOT NULL DEFAULT 'session' "
#    "CHECK(source_scope IN ('session','fleet'))",
#]


def init_fleet_db(path: str = _FLEET_DB_PATH) -> sqlite3.Connection:
    """
    Bootstrap fleet.db schema. Called exactly once by server.py before route binding.
    Raises on any failure — the server must not start without fleet awareness.
    """
    global _connection  # noqa: PLW0603
    logger.info("fleet_db_init: opening fleet.db at %s", path)
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        #for stmt in _MEMORY_SCHEMA_ADDITIONS:
        #    try:
        #        conn.execute(stmt)
        #        conn.commit()
        #    except sqlite3.OperationalError as exc:
        #        if "duplicate column" in str(exc).lower():
        #            logger.debug("fleet_db_init: column already exists (%s)", exc)
        #        else:
        #            raise
        conn.commit()
        _connection = conn
        logger.info("fleet_db_init: schema bootstrap complete")
        return conn
    except Exception:
        logger.critical("fleet_db_init: FATAL — could not initialise fleet.db", exc_info=True)
        raise


def get_fleet_db() -> sqlite3.Connection:
    """Return the module-level connection. Raises if init_fleet_db() was not called."""
    if _connection is None:
        raise RuntimeError(
            "fleet.db has not been initialised. "
            "Ensure fleet_db_init.init_fleet_db() is called before route binding."
        )
    return _connection

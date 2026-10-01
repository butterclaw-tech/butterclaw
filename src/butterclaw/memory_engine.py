"""
ButterClaw v0.8 — Unified Memory Engine
=================================================
Merges the two v0.8 candidate engines into one substrate:

  DEEP  tier  (from memory_engine-copilot.py) — structural, episodic/semantic
              memory for the Guardian Brain: HOT cache, WARM episodic SQLite,
              COLD semantic entity graph, activation-strength maturation,
              reconsolidation, read-only context injection.

  SURFACE tier (from memory_engine-gemini.py) — spatial telemetry for native
              computer-use: primitive-action classification (click/type/
              scroll/navigate), kinetic-velocity + spatial-jitter heuristics,
              and a Cold Memory attractor scanner over abstracted trajectories.

Why merge instead of picking one: the two engines solve different problems.
The copilot engine has no notion of raw mouse/keyboard telemetry; the gemini
engine has no persistence tier beyond its signature cache, and it assumed
`telemetry_events` / `memory_signatures` tables that didn't exist anywhere
in the 0.7.2 codebase. This file supplies both real schemas, lets the two
tiers feed each other (telemetry -> episodic -> semantic), and exposes both
a functional API (matching the copilot module's call style used elsewhere
in server.py-style code) and a `MemoryEngine` class facade (matching the
gemini module's call style) so either integration pattern keeps working.

SCHEMA OWNERSHIP (v0.8.0 update): once the full v0.8.0 file set landed
(server.py, event_ingester.py, topology_manager.py, watcher_daemon.py,
dreamer_daemon.py, archiver_daemon.py, tui_execution_harness.py), it turned
out `server.py`'s own `init_db()` — which runs at import time, before this
module is even imported — is the schema that everything else was actually
built against. Its `memory_signatures` table uses `sig_id` / `behavioral_hash`
/ `confidence_score` / `discovered_at`, not the `signature_id` / `hit_count`
/ `first_seen_unix` / `last_seen_unix` / `source` shape this file originally
shipped with, and `dreamer_daemon.py` writes signatures using that exact
canonical shape. `server.py` also creates `agents` and `sessions` tables
(needed by topology_manager.py / dreamer_daemon.py / archiver_daemon.py /
tui_execution_harness.py) and a `telemetry_events` table that includes a
`processed_by_dreamer` column this file was missing.

This revision makes memory_engine.py's own schema and surface-tier functions
match that canonical shape exactly, and adds `agents` / `sessions` /
`processed_by_dreamer` here too — so this module is self-sufficient (it does
not depend on server.py having run first) while staying byte-for-byte
compatible with what server.py, dreamer_daemon.py, and tui_dashboard.py
already assume. All `CREATE TABLE IF NOT EXISTS` statements are therefore
safe no-ops when server.py's init_db() already created these tables.

STILL MISSING (flagged, not built here): the original deep-memory design
this file's Tier 1-3 code was written for calls for three more modules that
have not been built yet — `dream_engine.py` (idle-triggered consolidation +
synthetic scenario generation), `loop_engine.py` (the Karpathy-style
autoresearch loop that proposes/evaluates/commits changes to signatures,
policies, and prompts), and `memory_api.py` (Flask Blueprint exposing memory/
dream/loop routes). This file's `dream_log` / `loop_experiments` tables,
`reconsolidate()`, and `run_maturation_tick()` are the hooks those modules
are meant to call — they are kept intact and untouched here even though
nothing in the current v0.8.0 file set calls them yet, so wiring them in
later doesn't require touching this file's deep tier again.

Tier map
--------
  Tier 0 — SURFACE TELEMETRY : SQLite `telemetry_events`      (raw primitives)
  Tier 0 — COLD ATTRACTORS   : SQLite `memory_signatures`     (known-bad shapes)
  Tier 1 — HOT CACHE         : in-process deque, TTL ~1hr, max 50 entries
  Tier 2 — WARM EPISODIC     : SQLite `memory_episodic`, TTL 7 days
  Tier 3 — COLD SEMANTIC     : SQLite `memory_semantic`, entity graph, permanent

Invariants enforced here (unchanged from the deep engine, now also binding
on the surface tier):
  I-10 — No raw_data ever persists; only sha256(raw_data)
  I-11 — memory_episodic / memory_semantic / memory_signatures survive the
         Gibson sequence reset
  I-12 — Memory context is injected as READ-ONLY enrichment into Guardian
         Brain prompts; no code path in this module triggers kinetic action

Unified flow (see spec: "Unified Memory Flow"):
  1. Telemetry primitives land in `telemetry_events` (ingest_telemetry_event)
  2. HOT heuristics (SpatialHeuristics) evaluate the rolling window
  3. Cold Memory attractors (memory_signatures) are checked first — O(1) path
  4. A block from either path is written into memory_episodic via store(),
     tagged threat_type="Spatial Telemetry", so it enters the same
     reconsolidation / maturation / semantic-graph lifecycle as every other
     Guardian Brain verdict
  5. Heuristic (zero-day) blocks that recur are crystallized into new
     memory_signatures rows (_promote_to_cold_signature) — the Cold Memory
     tier "learns" from the semantic layer's repetition, closing the loop
  6. run_maturation_tick() ages episodic activation *and* decays stale
     Cold Memory attractors that haven't fired in a long time
  7. retrieve_context() / format_context_for_prompt() inject structured,
     read-only memory (from either tier) into the Guardian Brain prompt

Changelog:
  [v0.8.0] Merge of memory_engine-copilot.py (deep structural memory) and
            memory_engine-gemini.py (surface telemetry + signatures) into a
            single dual-layer module per the ButterClaw v0.8 unified spec.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
import threading
import time
import uuid
from collections import deque, Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

log = logging.getLogger("butterclaw.memory")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)

# ---------------------------------------------------------------------------
# Lazy DB path — resolved at first use so memory_engine can be imported before
# config.py writes cfg.DB_PATH (mirrors the server.py import pattern).
# ---------------------------------------------------------------------------

_db_path: Optional[str] = None
_db_path_lock = threading.Lock()


def _get_db_path() -> str:
    """Return the database path, pulling from config on first call."""
    global _db_path
    if _db_path is not None:
        return _db_path
    with _db_path_lock:
        if _db_path is not None:
            return _db_path
        try:
            from config import cfg  # type: ignore
            _db_path = cfg.DB_PATH
        except Exception:
            import os
            _db_path = os.path.join(os.path.dirname(__file__), "butterclaw.db")
            log.warning(f"⚠️ [MEMORY] config.py unavailable — using fallback DB path: {_db_path}")
    return _db_path


def _get_db_connection() -> sqlite3.Connection:
    """Return a new SQLite connection using the same pattern as server.py."""
    conn = sqlite3.connect(_get_db_path(), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")  # matches server.py — required for Topology Lineage FKs
    return conn


# ---------------------------------------------------------------------------
# Config defaults (overridden at runtime via init() or config.py)
# ---------------------------------------------------------------------------

class _MemoryCfg:
    # Deep tier
    HOT_MAX: int = 50
    HOT_TTL_MINUTES: int = 60
    EPISODIC_TTL_DAYS: int = 7
    MATURATION_HALF_LIFE_HRS: float = 168.0
    MATURATION_SLOPE_HRS: float = 48.0
    MATURATION_THRESHOLD: float = 0.5
    PRUNE_ACTIVATION_FLOOR: float = 0.05
    PRUNE_AGE_DAYS: int = 30
    CONTEXT_MAX: int = 3
    REASONING_SUMMARY_CHARS: int = 200

    # Surface tier
    TELEMETRY_WINDOW_SECONDS: float = 10.0
    SIGNATURE_REFRESH_SECONDS: float = 5.0
    GRID_COLS: int = 4
    GRID_ROWS: int = 4
    SCREEN_WIDTH: int = 1920
    SCREEN_HEIGHT: int = 1080
    MAX_TYPING_VELOCITY: float = 15.0          # keystrokes / second
    SUSPICIOUS_TARGETS: Tuple[str, ...] = ("terminal", "powershell", "cmd", "shadow")
    ATTRACTOR_PROMOTION_HITS: int = 3          # zero-day repeats before crystallizing
    ATTRACTOR_DECAY_DAYS: int = 30             # low-confidence signatures decay after this
    ATTRACTOR_DECAY_CONFIDENCE_FLOOR: float = 0.6  # only decay sigs below this confidence
    LIVE_CRYSTALLIZATION_ENABLED: bool = True  # one-line disable if this proves noisy vs. the Dreamer
    LIVE_CRYSTALLIZATION_CONFIDENCE: float = 0.7   # deliberately below the Dreamer's 0.85 —
                                                    # unaudited, same-session-only signal


_cfg = _MemoryCfg()


def init(
    hot_max: int = 50,
    hot_ttl_minutes: int = 60,
    episodic_ttl_days: int = 7,
    maturation_half_life_hrs: float = 168.0,
    context_max: int = 3,
    db_path: Optional[str] = None,
    grid_cols: int = 4,
    grid_rows: int = 4,
    screen_width: int = 1920,
    screen_height: int = 1080,
) -> None:
    """
    Call once from server.py after config is loaded to override defaults.
    Mirrors the pattern used by policy_engine.init_policy_db().
    Covers both the deep tier (hot/episodic/maturation) and the surface tier
    (screen grid used to abstract click coordinates into zones).
    """
    global _db_path
    _cfg.HOT_MAX = hot_max
    _cfg.HOT_TTL_MINUTES = hot_ttl_minutes
    _cfg.EPISODIC_TTL_DAYS = episodic_ttl_days
    _cfg.MATURATION_HALF_LIFE_HRS = maturation_half_life_hrs
    _cfg.CONTEXT_MAX = context_max
    _cfg.GRID_COLS = grid_cols
    _cfg.GRID_ROWS = grid_rows
    _cfg.SCREEN_WIDTH = screen_width
    _cfg.SCREEN_HEIGHT = screen_height
    if db_path:
        _db_path = db_path


# ---------------------------------------------------------------------------
# SQLite schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA = """
-- Topology (owned canonically by server.py's init_db(); re-declared here with
-- IDENTICAL definitions so this module is self-sufficient if it initializes
-- the DB first — e.g. tui_execution_harness.py run standalone without server.py).
CREATE TABLE IF NOT EXISTS agents (
    agent_id         TEXT PRIMARY KEY,
    parent_agent_id  TEXT,
    pid              INTEGER NOT NULL,
    capabilities     TEXT NOT NULL,
    status           TEXT DEFAULT 'ACTIVE',
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    agent_id     TEXT NOT NULL,
    taint_level  INTEGER DEFAULT 0,
    taint_source TEXT,
    started_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at     DATETIME,
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

-- Tier 0 (surface): raw spatial telemetry primitives.
-- Column set matches server.py's init_db() exactly, including
-- processed_by_dreamer (consumed by dreamer_daemon.py / archiver_daemon.py).
CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL,
    timestamp            REAL NOT NULL,
    action_type          TEXT NOT NULL,
    spatial_payload      TEXT,
    screenshot_ref       TEXT,
    processed_by_dreamer BOOLEAN DEFAULT 0,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_tel_session_ts   ON telemetry_events(session_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_time    ON telemetry_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_dreamer ON telemetry_events(processed_by_dreamer);

-- Tier 0 (surface): Cold Memory behavioral attractors (abstracted trajectories).
-- Column set matches server.py's init_db() AND dreamer_daemon.py's
-- _promote_to_cold_memory() INSERT exactly — sig_id / behavioral_hash /
-- confidence_score / discovered_at. (memory_engine.py originally shipped
-- with a different column set — signature_id/hit_count/first_seen_unix/
-- last_seen_unix/source — before dreamer_daemon.py existed; this is the
-- reconciled, canonical version both files now agree on.)
CREATE TABLE IF NOT EXISTS memory_signatures (
    sig_id           TEXT PRIMARY KEY,
    threat_category  TEXT NOT NULL,
    behavioral_hash  TEXT,
    sequence_pattern TEXT NOT NULL,
    confidence_score REAL DEFAULT 1.0,
    discovered_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sig_category ON memory_signatures(threat_category);

-- Tier 2: Warm episodic store
CREATE TABLE IF NOT EXISTS memory_episodic (
    memory_id           TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    threat_type         TEXT NOT NULL,
    raw_data_hash       TEXT NOT NULL,
    verdict             TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 0.0,
    primary_gate        TEXT,
    reasoning_summary   TEXT,
    chain_used          INTEGER NOT NULL DEFAULT 0,
    auditor_verdict     TEXT,
    auditor_reasoning   TEXT,
    activation_strength REAL NOT NULL DEFAULT 0.03,
    tags                TEXT NOT NULL DEFAULT '[]',
    source              TEXT NOT NULL DEFAULT 'live',
    created_at_unix     REAL NOT NULL,
    last_accessed_unix  REAL
);

CREATE INDEX IF NOT EXISTS idx_mem_ep_threat     ON memory_episodic(threat_type);
CREATE INDEX IF NOT EXISTS idx_mem_ep_hash       ON memory_episodic(raw_data_hash);
CREATE INDEX IF NOT EXISTS idx_mem_ep_verdict    ON memory_episodic(verdict);
CREATE INDEX IF NOT EXISTS idx_mem_ep_activation ON memory_episodic(activation_strength DESC);

-- Tier 3: Cold semantic entity graph
CREATE TABLE IF NOT EXISTS memory_semantic (
    entity_id           TEXT PRIMARY KEY,
    entity_name         TEXT NOT NULL UNIQUE,
    entity_type         TEXT,
    first_seen_unix     REAL NOT NULL,
    last_seen_unix      REAL NOT NULL,
    observation_count   INTEGER NOT NULL DEFAULT 1,
    edges               TEXT NOT NULL DEFAULT '{}',
    metadata            TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_mem_sem_name ON memory_semantic(entity_name);

-- Dream / Loop cycle log
CREATE TABLE IF NOT EXISTS dream_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    phase               TEXT NOT NULL,
    duration_seconds    REAL,
    proposals_generated INTEGER NOT NULL DEFAULT 0,
    consolidations      INTEGER NOT NULL DEFAULT 0,
    pruned_count        INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'completed',
    notes               TEXT
);

-- Loop experiment history
CREATE TABLE IF NOT EXISTS loop_experiments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp           TEXT NOT NULL,
    experiment_type     TEXT NOT NULL,
    artifact_id         TEXT,
    hypothesis          TEXT,
    proposed_change     TEXT,
    baseline_score      REAL,
    candidate_score     REAL,
    delta_score         REAL,
    status              TEXT NOT NULL DEFAULT 'pending',
    policy_gate_action  TEXT,
    notes               TEXT
);

-- I-15: the ONLY artifact store loop_engine.py's "prompt" proposals are
-- allowed to write to. Guardian Brain / Auditor / Dream Weaver prompt text
-- lives as hardcoded string literals in server.py today — .py files are
-- explicitly off-limits to the loop (parse-time-blocked), so until server.py
-- is updated to consult this table when building a prompt, writes here are
-- inert (staged, not yet live). See loop_engine.py's module docstring.
CREATE TABLE IF NOT EXISTS prompt_overrides (
    prompt_key   TEXT PRIMARY KEY,
    prompt_value TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    updated_by   TEXT NOT NULL DEFAULT 'loop_engine'
);
"""


def init_memory_db() -> None:
    """
    Create all v0.8 memory tables (deep + surface) if they do not exist.
    Call from server.py init_db() alongside policy_engine.init_policy_db().
    """
    try:
        conn = _get_db_connection()
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()
        log.info("✅ [MEMORY] Memory tables initialised (deep + surface tiers).")
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Schema init failed: {e}")


# ---------------------------------------------------------------------------
# Tier 1 — Hot Cache (deep tier)
# ---------------------------------------------------------------------------

class _HotCacheEntry:
    __slots__ = ("memory_id", "threat_type", "raw_data_hash", "verdict",
                 "confidence", "primary_gate", "reasoning_summary",
                 "auditor_verdict", "tags", "source", "inserted_at")

    def __init__(self, record: Dict[str, Any]) -> None:
        self.memory_id         = record["memory_id"]
        self.threat_type       = record["threat_type"]
        self.raw_data_hash     = record["raw_data_hash"]
        self.verdict           = record["verdict"]
        self.confidence        = record["confidence"]
        self.primary_gate      = record.get("primary_gate", "None")
        self.reasoning_summary = record.get("reasoning_summary", "")
        self.auditor_verdict   = record.get("auditor_verdict")
        self.tags              = record.get("tags", [])
        # "source" (e.g. "live" / "dream" / "reconsolidated") was missing here
        # before — format_context_for_prompt()'s "[DREAM-PRIMED]" tag silently
        # never rendered for anything still in the hot tier as a result, which
        # is the tier a fresh dream_engine.py-written episode is most likely
        # to still be sitting in. Fixed so dream-tier provenance survives the
        # hot cache instead of only showing up once an episode ages into
        # episodic/semantic.
        self.source             = record.get("source", "live")
        self.inserted_at       = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.inserted_at) > (_cfg.HOT_TTL_MINUTES * 60)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id":         self.memory_id,
            "threat_type":       self.threat_type,
            "raw_data_hash":     self.raw_data_hash,
            "verdict":           self.verdict,
            "confidence":        self.confidence,
            "primary_gate":      self.primary_gate,
            "reasoning_summary": self.reasoning_summary,
            "auditor_verdict":   self.auditor_verdict,
            "tags":              self.tags,
            "source":            self.source,
        }


class _HotCache:
    """
    Thread-safe in-process deque acting as the hot memory tier.
    Expired entries are evicted lazily on every write and on flush.
    """

    def __init__(self) -> None:
        self._lock  = threading.Lock()
        self._deque: deque[_HotCacheEntry] = deque(maxlen=_cfg.HOT_MAX)

    def push(self, record: Dict[str, Any]) -> None:
        entry = _HotCacheEntry(record)
        with self._lock:
            self._evict_expired()
            self._deque.appendleft(entry)

    def find_by_hash(self, raw_data_hash: str) -> Optional[_HotCacheEntry]:
        with self._lock:
            for e in self._deque:
                if not e.is_expired() and e.raw_data_hash == raw_data_hash:
                    return e
        return None

    def find_by_threat_type(self, threat_type: str, limit: int = 3) -> List[_HotCacheEntry]:
        results = []
        with self._lock:
            for e in self._deque:
                if not e.is_expired() and e.threat_type == threat_type:
                    results.append(e)
                    if len(results) >= limit:
                        break
        return results

    def all_live(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._deque if not e.is_expired()]

    def flush_to_episodic(self) -> int:
        """Persist all live hot-cache entries to the episodic store. Returns count flushed."""
        flushed = 0
        with self._lock:
            live = [e for e in self._deque if not e.is_expired()]
        for e in live:
            if _episodic_upsert(e.to_dict()):
                flushed += 1
        return flushed

    def _evict_expired(self) -> None:
        fresh = deque((e for e in self._deque if not e.is_expired()), maxlen=_cfg.HOT_MAX)
        self._deque = fresh


_hot_cache = _HotCache()


# ---------------------------------------------------------------------------
# Activation Strength — sigmoid maturation (deep tier)
# ---------------------------------------------------------------------------

def compute_activation_strength(created_at_unix: float) -> float:
    """
    Sigmoid maturation based on age.

    A(t) = 1 / (1 + exp(-(t_hrs - t_half) / k))

    Values:
      A(  0 hrs) ≈ 0.03  — silent, priming only
      A(168 hrs) = 0.50  — retrieval threshold
      A(336 hrs) ≈ 0.97  — fully mature
    """
    age_hours = (time.time() - created_at_unix) / 3600.0
    t_half    = _cfg.MATURATION_HALF_LIFE_HRS
    k         = _cfg.MATURATION_SLOPE_HRS
    try:
        strength = 1.0 / (1.0 + math.exp(-(age_hours - t_half) / k))
    except OverflowError:
        strength = 1.0 if age_hours > t_half else 0.0
    return round(strength, 6)


# ---------------------------------------------------------------------------
# Tier 2 — Warm Episodic Store helpers (deep tier)
# ---------------------------------------------------------------------------

def _episodic_upsert(record: Dict[str, Any]) -> bool:
    now_unix   = time.time()
    tags_json  = json.dumps(record.get("tags", []))
    activation = compute_activation_strength(record.get("created_at_unix", now_unix))

    try:
        conn = _get_db_connection()
        conn.execute("""
            INSERT INTO memory_episodic
                (memory_id, timestamp, threat_type, raw_data_hash, verdict, confidence,
                 primary_gate, reasoning_summary, chain_used, auditor_verdict,
                 auditor_reasoning, activation_strength, tags, source, created_at_unix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                auditor_verdict     = excluded.auditor_verdict,
                auditor_reasoning   = excluded.auditor_reasoning,
                activation_strength = excluded.activation_strength,
                tags                = excluded.tags,
                last_accessed_unix  = ?
        """, (
            record["memory_id"],
            record.get("timestamp", _utcnow()),
            record["threat_type"],
            record["raw_data_hash"],
            record["verdict"],
            record.get("confidence", 0.0),
            record.get("primary_gate", "None"),
            record.get("reasoning_summary", ""),
            1 if record.get("chain_used") else 0,
            record.get("auditor_verdict"),
            record.get("auditor_reasoning"),
            activation,
            tags_json,
            record.get("source", "live"),
            record.get("created_at_unix", now_unix),
            now_unix,
        ))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Episodic upsert failed: {e}")
        return False


def _episodic_query(
    threat_type: Optional[str] = None,
    raw_data_hash: Optional[str] = None,
    min_activation: float = 0.0,
    limit: int = 10,
    order_by: str = "activation_strength DESC",
) -> List[Dict[str, Any]]:
    sql    = "SELECT * FROM memory_episodic WHERE 1=1"
    params: List[Any] = []

    if threat_type:
        sql += " AND threat_type = ?"
        params.append(threat_type)
    if raw_data_hash:
        sql += " AND raw_data_hash = ?"
        params.append(raw_data_hash)
    if min_activation > 0:
        sql += " AND activation_strength >= ?"
        params.append(min_activation)

    sql += f" ORDER BY {order_by} LIMIT ?"
    params.append(limit)

    try:
        conn = _get_db_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        results = []
        for row in rows:
            r = dict(row)
            try:
                r["tags"] = json.loads(r.get("tags") or "[]")
            except (json.JSONDecodeError, TypeError):
                r["tags"] = []
            results.append(r)
        return results
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Episodic query failed: {e}")
        return []


def _episodic_delete(memory_id: str) -> bool:
    """Returns True only if a row actually matched and was removed — a bare
    DELETE never raises for zero matched rows, so rowcount must be checked
    explicitly, otherwise callers (e.g. memory_api.py's DELETE
    /api/memory/episodic/<id> route) can't distinguish "deleted" from
    "nothing there to delete" and would incorrectly report success/200
    instead of 404 for an unknown memory_id."""
    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.execute("DELETE FROM memory_episodic WHERE memory_id = ?", (memory_id,))
        conn.commit()
        return cur.rowcount > 0
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Episodic delete failed: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Tier 3 — Cold Semantic Graph helpers (deep tier)
# ---------------------------------------------------------------------------

def _semantic_upsert_entity(entity_name: str, entity_type: str = "unknown") -> str:
    now_unix  = time.time()
    entity_id = hashlib.sha256(entity_name.lower().strip().encode()).hexdigest()[:16]

    try:
        conn = _get_db_connection()
        conn.execute("""
            INSERT INTO memory_semantic
                (entity_id, entity_name, entity_type, first_seen_unix, last_seen_unix,
                 observation_count, edges, metadata)
            VALUES (?, ?, ?, ?, ?, 1, '{}', '{}')
            ON CONFLICT(entity_id) DO UPDATE SET
                last_seen_unix    = excluded.last_seen_unix,
                observation_count = observation_count + 1
        """, (entity_id, entity_name.strip(), entity_type, now_unix, now_unix))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Semantic upsert failed for '{entity_name}': {e}")

    return entity_id


def _semantic_add_edge(from_id: str, to_id: str, weight_delta: float = 1.0) -> None:
    try:
        conn = _get_db_connection()
        row = conn.execute(
            "SELECT edges FROM memory_semantic WHERE entity_id = ?", (from_id,)
        ).fetchone()
        if row is None:
            conn.close()
            return
        edges = json.loads(row["edges"] or "{}")
        edges[to_id] = round(edges.get(to_id, 0.0) + weight_delta, 4)
        conn.execute(
            "UPDATE memory_semantic SET edges = ? WHERE entity_id = ?",
            (json.dumps(edges), from_id)
        )
        conn.commit()
        conn.close()
    except (sqlite3.Error, json.JSONDecodeError) as e:
        log.error(f"❌ [MEMORY] Semantic edge update failed: {e}")


def _semantic_query_by_tags(tags: List[str], limit: int = 5) -> List[Dict[str, Any]]:
    if not tags:
        return []
    placeholders = ",".join("?" * len(tags))
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            f"SELECT * FROM memory_semantic WHERE entity_name IN ({placeholders}) "
            f"ORDER BY observation_count DESC LIMIT ?",
            tags + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Semantic tag query failed: {e}")
        return []


def get_semantic_graph() -> List[Dict[str, Any]]:
    """Return the full entity graph as a list of node dicts (for the API route)."""
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            "SELECT * FROM memory_semantic ORDER BY observation_count DESC"
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            node = dict(r)
            try:
                node["edges"] = json.loads(node.get("edges") or "{}")
            except (json.JSONDecodeError, TypeError):
                node["edges"] = {}
            result.append(node)
        return result
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Semantic graph fetch failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Tag extraction — lightweight heuristic (no LLM call — I-12 compliance)
# ---------------------------------------------------------------------------

_TAG_BLOCKLIST = frozenset({
    "the", "and", "or", "a", "an", "in", "is", "it", "of", "to", "for",
    "on", "at", "by", "with", "from", "as", "be", "was", "are", "that",
    "this", "has", "have", "been", "can", "not", "no", "do", "if", "log",
    "event", "result", "status", "data", "none", "true", "false", "error",
})

_THREAT_KEYWORDS = frozenset({
    "injection", "exfiltration", "escalation", "bypass", "exploit",
    "payload", "base64", "exec", "shell", "chmod", "curl", "wget",
    "python", "subprocess", "eval", "import", "os", "sys", "credentials",
    "token", "key", "secret", "password", "api_key", "gateway", "proxy",
    "chain", "tool", "mcp", "stdio", "sse", "ollama", "llm", "agent",
})


def _extract_tags(text: str, threat_type: str, max_tags: int = 8) -> List[str]:
    import re
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text)
    tags: Dict[str, int] = {}

    for token in tokens:
        norm = token.lower().strip("_")
        if norm in _TAG_BLOCKLIST:
            continue
        if norm in _THREAT_KEYWORDS or len(norm) >= 4:
            tags[norm] = tags.get(norm, 0) + 1

    if threat_type:
        norm_tt = threat_type.lower().replace(" ", "_")
        tags[norm_tt] = tags.get(norm_tt, 0) + 5

    sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)
    return [t for t, _ in sorted_tags[:max_tags]]


# ---------------------------------------------------------------------------
# Public API — store()  (deep tier)
# ---------------------------------------------------------------------------

def store(
    threat_type: str,
    raw_data: str,
    verdict: str,
    confidence: float,
    primary_gate: str,
    reasoning: str,
    chain_used: bool = False,
    source: str = "live",
) -> str:
    """
    Store a new verdict in memory.

    1. Computes sha256(raw_data) — raw_data never written (I-10).
    2. Writes to hot cache immediately.
    3. Persists to memory_episodic in background thread.
    4. Returns memory_id for correlation.

    Note: this is also the landing point for surface-tier (telemetry) blocks —
    evaluate_spatial_intent() calls store() with threat_type="Spatial Telemetry"
    so that Cold Memory / heuristic hits enter the same episodic → semantic
    lifecycle as every other Guardian Brain verdict (unified flow step 4).
    """
    now_unix          = time.time()
    memory_id         = uuid.uuid4().hex
    raw_data_hash     = hashlib.sha256(raw_data.encode("utf-8", errors="replace")).hexdigest()
    reasoning_summary = reasoning[:_cfg.REASONING_SUMMARY_CHARS]
    tags              = _extract_tags(reasoning, threat_type)
    timestamp         = _utcnow()

    record: Dict[str, Any] = {
        "memory_id":          memory_id,
        "timestamp":          timestamp,
        "threat_type":        threat_type,
        "raw_data_hash":      raw_data_hash,
        "verdict":            verdict,
        "confidence":         confidence,
        "primary_gate":       primary_gate,
        "reasoning_summary":  reasoning_summary,
        "chain_used":         chain_used,
        "auditor_verdict":    None,
        "auditor_reasoning":  None,
        "activation_strength": compute_activation_strength(now_unix),
        "tags":               tags,
        "source":             source,
        "created_at_unix":    now_unix,
    }

    _hot_cache.push(record)

    def _persist() -> None:
        if _episodic_upsert(record):
            _promote_tags_to_semantic(tags, threat_type)

    threading.Thread(target=_persist, daemon=True).start()

    log.info(f"🧠 [MEMORY] Stored {verdict} ({confidence:.2f}) — {threat_type} [{memory_id[:8]}]")
    return memory_id


def _promote_tags_to_semantic(tags: List[str], threat_type: str) -> None:
    threat_entity_id = _semantic_upsert_entity(threat_type, entity_type="threat_type")
    for tag in tags:
        tag_entity_id = _semantic_upsert_entity(tag, entity_type="pattern")
        _semantic_add_edge(threat_entity_id, tag_entity_id)
        _semantic_add_edge(tag_entity_id, threat_entity_id, weight_delta=0.5)


# ---------------------------------------------------------------------------
# Public API — retrieve_context()  (deep tier)
# ---------------------------------------------------------------------------

def retrieve_context(
    threat_type: str,
    raw_data: str,
    tags: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Retrieve up to CONTEXT_MAX memory records relevant to the current request.

    Selection order:
      1. Hot cache — exact raw_data_hash match (replay detection)
      2. Warm episodic — matching threat_type, by activation_strength DESC
      3. Cold semantic — overlapping tags

    Returns (records, exact_replay_detected). READ-ONLY (I-12).
    """
    raw_data_hash  = hashlib.sha256(raw_data.encode("utf-8", errors="replace")).hexdigest()
    results:  List[Dict[str, Any]] = []
    seen_ids: set = set()
    exact_replay = False
    max_ctx = _cfg.CONTEXT_MAX

    hot_hit = _hot_cache.find_by_hash(raw_data_hash)
    if hot_hit:
        exact_replay = True
        rec = hot_hit.to_dict()
        rec["_source_tier"] = "hot"
        results.append(rec)
        seen_ids.add(rec["memory_id"])

    if len(results) < max_ctx:
        episodic_hits = _episodic_query(
            threat_type=threat_type,
            min_activation=0.0,
            limit=max_ctx * 3,
            order_by="activation_strength DESC",
        )
        for row in episodic_hits:
            if len(results) >= max_ctx:
                break
            if row["memory_id"] in seen_ids:
                continue
            row["_source_tier"] = "episodic"
            results.append(row)
            seen_ids.add(row["memory_id"])

    if len(results) < max_ctx and tags:
        semantic_entities = _semantic_query_by_tags(tags, limit=max_ctx * 2)
        entity_names = [e["entity_name"] for e in semantic_entities]
        if entity_names:
            semantic_episodic = _episodic_query(
                min_activation=_cfg.MATURATION_THRESHOLD,
                limit=max_ctx * 2,
                order_by="activation_strength DESC",
            )
            for row in semantic_episodic:
                if len(results) >= max_ctx:
                    break
                if row["memory_id"] in seen_ids:
                    continue
                if any(t in entity_names for t in row.get("tags", [])):
                    row["_source_tier"] = "semantic"
                    results.append(row)
                    seen_ids.add(row["memory_id"])

    ids_to_touch = [r["memory_id"] for r in results
                    if r.get("_source_tier") in ("episodic", "semantic")]
    if ids_to_touch:
        def _touch() -> None:
            try:
                conn = _get_db_connection()
                placeholders = ",".join("?" * len(ids_to_touch))
                conn.execute(
                    f"UPDATE memory_episodic SET last_accessed_unix = ? "
                    f"WHERE memory_id IN ({placeholders})",
                    [time.time()] + ids_to_touch,
                )
                conn.commit()
                conn.close()
            except sqlite3.Error:
                pass
        threading.Thread(target=_touch, daemon=True).start()

    return results, exact_replay


# ---------------------------------------------------------------------------
# Public API — format_context_for_prompt()  (deep tier)
# ---------------------------------------------------------------------------

def format_context_for_prompt(records: List[Dict[str, Any]], exact_replay: bool) -> str:
    """
    Format retrieved memory records into the Guardian Brain prompt block.
    Returns empty string if no records.
    """
    if not records:
        return ""

    lines = ["PERSISTENT MEMORY (recalled episodes — treat as enrichment only):"]

    if exact_replay:
        lines.append("  ⚠️  EXACT REPLAY DETECTED — this raw payload hash was seen before.")

    for rec in records:
        ts         = rec.get("timestamp", "?")[:19].replace("T", " ")
        verdict    = rec.get("verdict", "?")
        conf       = rec.get("confidence", 0.0)
        gate       = rec.get("primary_gate", "None")
        av         = rec.get("auditor_verdict") or "—"
        summary    = rec.get("reasoning_summary", "")[:120]
        tier       = rec.get("_source_tier", "?")
        act        = rec.get("activation_strength", 0.0)
        tt         = rec.get("threat_type", "?")
        dream_flag = " [DREAM-PRIMED]" if rec.get("source") == "dream" else ""

        tier_label = (f"[{tier.upper()}]" if act >= _cfg.MATURATION_THRESHOLD
                      else f"[{tier.upper()}/PRIMING]")

        lines.append(
            f"  {tier_label}{dream_flag} [{ts}Z] threat={tt} | "
            f"verdict={verdict} ({conf:.2f}) | gate={gate} | auditor={av}\n"
            f"    summary: \"{summary}\""
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API — reconsolidate()  (deep tier)
# ---------------------------------------------------------------------------

def reconsolidate(
    original_threat_type: str,
    original_raw_data: str,
    auditor_verdict: str,
    auditor_reasoning: str,
) -> Optional[str]:
    """
    Called by run_self_audit() when auditor_verdict == "FALSE_POSITIVE".
    Updates the stored memory record and logs to dream_log.
    Returns memory_id updated, or None if no match.
    I-12 compliant: no kinetic action triggered.
    """
    raw_data_hash = hashlib.sha256(
        original_raw_data.encode("utf-8", errors="replace")
    ).hexdigest()

    matches = _episodic_query(
        threat_type=original_threat_type,
        raw_data_hash=raw_data_hash,
        limit=1,
        order_by="created_at_unix DESC",
    )
    if not matches:
        log.info(f"🧠 [MEMORY] Reconsolidation: no match for hash {raw_data_hash[:12]}...")
        return None

    memory_id = matches[0]["memory_id"]

    try:
        conn = _get_db_connection()
        conn.execute("""
            UPDATE memory_episodic
            SET auditor_verdict    = ?,
                auditor_reasoning  = ?,
                source             = 'reconsolidated',
                last_accessed_unix = ?
            WHERE memory_id = ?
        """, (auditor_verdict,
              auditor_reasoning[:_cfg.REASONING_SUMMARY_CHARS],
              time.time(),
              memory_id))
        conn.commit()
        conn.close()

        _dream_log_write(
            phase="reconsolidation",
            duration_seconds=0.0,
            proposals_generated=0,
            consolidations=1,
            pruned_count=0,
            status="completed",
            notes=f"memory_id={memory_id[:8]} | auditor_verdict={auditor_verdict}",
        )

        log.info(f"🧠 [MEMORY] Reconsolidated {memory_id[:8]} → {auditor_verdict}")
        return memory_id

    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Reconsolidation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API — run_maturation_tick()  (deep + surface tiers)
# ---------------------------------------------------------------------------

def run_maturation_tick() -> Dict[str, int]:
    """
    Deep tier: recompute activation_strength, promote to semantic, prune expired.
    Surface tier: decay Cold Memory attractors that haven't fired recently.
    Called by dream_engine.py during the consolidation phase.
    Returns {updated, promoted_to_semantic, pruned, signatures_decayed}.
    """
    stats = {"updated": 0, "promoted_to_semantic": 0, "pruned": 0, "signatures_decayed": 0}
    now_unix     = time.time()
    prune_cutoff = now_unix - (_cfg.PRUNE_AGE_DAYS * 86400)

    try:
        conn = _get_db_connection()
        all_records = conn.execute("SELECT * FROM memory_episodic").fetchall()
        conn.close()
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Maturation tick fetch failed: {e}")
        return stats

    for row in all_records:
        r       = dict(row)
        mem_id  = r["memory_id"]
        created = r.get("created_at_unix", now_unix)
        new_act = compute_activation_strength(created)
        old_act = r.get("activation_strength", 0.0)

        if new_act < _cfg.PRUNE_ACTIVATION_FLOOR and created < prune_cutoff:
            _episodic_delete(mem_id)
            stats["pruned"] += 1
            log.info(f"🗑️  [MEMORY] Pruned {mem_id[:8]} "
                     f"(A={new_act:.3f}, age={(now_unix-created)/86400:.1f}d)")
            continue

        try:
            conn = _get_db_connection()
            conn.execute(
                "UPDATE memory_episodic SET activation_strength = ? WHERE memory_id = ?",
                (new_act, mem_id),
            )
            conn.commit()
            conn.close()
            stats["updated"] += 1
        except sqlite3.Error as e:
            log.error(f"❌ [MEMORY] Activation update failed for {mem_id[:8]}: {e}")
            continue

        if new_act >= _cfg.MATURATION_THRESHOLD and old_act < _cfg.MATURATION_THRESHOLD:
            try:
                tags = json.loads(r.get("tags") or "[]")
            except (json.JSONDecodeError, TypeError):
                tags = []
            _promote_tags_to_semantic(tags, r["threat_type"])
            stats["promoted_to_semantic"] += 1
            log.info(f"🧠 [MEMORY] Promoted {mem_id[:8]} to semantic (A={new_act:.3f})")

    stats["signatures_decayed"] = _decay_stale_signatures()

    log.info(
        f"✅ [MEMORY] Maturation tick — "
        f"updated={stats['updated']} promoted={stats['promoted_to_semantic']} "
        f"pruned={stats['pruned']} signatures_decayed={stats['signatures_decayed']}"
    )
    return stats


def _decay_stale_signatures() -> int:
    """
    Surface tier maturation: drop low-confidence attractors older than
    ATTRACTOR_DECAY_DAYS.

    The canonical memory_signatures schema (shared with server.py /
    dreamer_daemon.py) has no hit_count / last_seen_unix / source columns to
    track freshness or curation status, so decay is keyed off the columns
    that DO exist: discovered_at (age) and confidence_score (never decay a
    signature the Dreamer or a repeat crystallization is confident about).
    Anything with confidence_score >= ATTRACTOR_DECAY_CONFIDENCE_FLOOR is
    treated as trusted and left alone regardless of age.
    """
    try:
        conn = _get_db_connection()
        cur = conn.execute(
            "DELETE FROM memory_signatures "
            "WHERE confidence_score < ? "
            "AND discovered_at < datetime('now', ?)",
            (_cfg.ATTRACTOR_DECAY_CONFIDENCE_FLOOR, f"-{_cfg.ATTRACTOR_DECAY_DAYS} days"),
        )
        conn.commit()
        removed = cur.rowcount if cur.rowcount is not None else 0
        conn.close()
        if removed:
            refresh_signatures()
        return removed
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Signature decay failed: {e}")
        return 0


# ---------------------------------------------------------------------------
# Public API — flush / get helpers for API routes  (deep tier)
# ---------------------------------------------------------------------------

def flush_hot_to_episodic() -> int:
    """Force-flush hot cache to episodic. Used by /api/memory/flush."""
    count = _hot_cache.flush_to_episodic()
    log.info(f"🧠 [MEMORY] Hot→Episodic flush: {count} records written.")
    return count


def get_hot_cache() -> List[Dict[str, Any]]:
    """Return all live hot-cache entries (/api/memory/hot)."""
    return _hot_cache.all_live()


def get_episodic(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Paginated episodic store query (/api/memory/episodic)."""
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            "SELECT * FROM memory_episodic ORDER BY created_at_unix DESC LIMIT ? OFFSET ?",
            (min(limit, 200), offset),
        ).fetchall()
        conn.close()
        results = []
        for row in rows:
            r = dict(row)
            try:
                r["tags"] = json.loads(r.get("tags") or "[]")
            except (json.JSONDecodeError, TypeError):
                r["tags"] = []
            results.append(r)
        return results
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_episodic failed: {e}")
        return []


def delete_episodic(memory_id: str) -> bool:
    """Hard-delete a single episodic record (/api/memory/episodic/<id> DELETE)."""
    return _episodic_delete(memory_id)


# ---------------------------------------------------------------------------
# dream_log helpers (shared with dream_engine.py and loop_engine.py)
# ---------------------------------------------------------------------------

def _dream_log_write(
    phase: str,
    duration_seconds: float,
    proposals_generated: int,
    consolidations: int,
    pruned_count: int,
    status: str = "completed",
    notes: Optional[str] = None,
) -> None:
    conn = None
    try:
        conn = _get_db_connection()
        conn.execute("""
            INSERT INTO dream_log
                (timestamp, phase, duration_seconds, proposals_generated,
                 consolidations, pruned_count, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (_utcnow(), phase, duration_seconds, proposals_generated,
              consolidations, pruned_count, status, notes))
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] dream_log write failed: {e}")
    finally:
        if conn is not None:
            conn.close()


def log_dream_cycle(
    phase: str,
    duration_seconds: float,
    proposals_generated: int = 0,
    consolidations: int = 0,
    pruned_count: int = 0,
    status: str = "completed",
    notes: Optional[str] = None,
) -> None:
    """
    Public entry point for dream_engine.py (and later loop_engine.py) to log
    a dream/loop cycle to `dream_log`. `reconsolidate()` already writes here
    internally for auditor-triggered reconsolidation; this is the same table,
    exposed properly instead of dream_engine.py reaching into the
    underscore-prefixed `_dream_log_write` directly.
    """
    _dream_log_write(phase, duration_seconds, proposals_generated,
                      consolidations, pruned_count, status, notes)


def get_dream_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Paginated dream_log reader — for the future memory_api.py Blueprint /
    TUI dashboard section. Newest cycles first."""
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            "SELECT * FROM dream_log ORDER BY id DESC LIMIT ?",
            (min(limit, 200),),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_dream_log failed: {e}")
        return []


# ---------------------------------------------------------------------------
# loop_experiments — public API for loop_engine.py (Karpathy autoresearch loop)
# ---------------------------------------------------------------------------

def record_loop_experiment(
    experiment_type: str,
    artifact_id: Optional[str],
    hypothesis: Optional[str],
    proposed_change: Optional[str],
    baseline_score: Optional[float] = None,
    candidate_score: Optional[float] = None,
    delta_score: Optional[float] = None,
    status: str = "pending",
    policy_gate_action: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[int]:
    """Insert a new loop_experiments row. Returns the new row's id, or None on failure."""
    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.execute("""
            INSERT INTO loop_experiments
                (timestamp, experiment_type, artifact_id, hypothesis, proposed_change,
                 baseline_score, candidate_score, delta_score, status, policy_gate_action, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (_utcnow(), experiment_type, artifact_id, hypothesis, proposed_change,
              baseline_score, candidate_score, delta_score, status, policy_gate_action, notes))
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] record_loop_experiment failed: {e}")
        return None
    finally:
        if conn is not None:
            conn.close()


def update_loop_experiment(experiment_id: int, **fields) -> bool:
    """Update specific columns on an existing loop_experiments row (e.g. to set
    status='committed'/'reverted' after a proposal is decided)."""
    allowed = {"baseline_score", "candidate_score", "delta_score", "status",
               "policy_gate_action", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn = None
    try:
        conn = _get_db_connection()
        conn.execute(
            f"UPDATE loop_experiments SET {set_clause} WHERE id = ?",
            list(updates.values()) + [experiment_id],
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] update_loop_experiment failed: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def get_loop_experiments(limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Paginated loop_experiments reader — for the future memory_api.py Blueprint /
    TUI dashboard section. Newest first."""
    sql = "SELECT * FROM loop_experiments WHERE 1=1"
    params: List[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 200))
    try:
        conn = _get_db_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_loop_experiments failed: {e}")
        return []


# ---------------------------------------------------------------------------
# prompt_overrides — public API for loop_engine.py's "prompt" artifact type.
# Staged only — server.py does not read this table yet (see schema comment).
# ---------------------------------------------------------------------------

def get_prompt_override(prompt_key: str) -> Optional[str]:
    try:
        conn = _get_db_connection()
        row = conn.execute(
            "SELECT prompt_value FROM prompt_overrides WHERE prompt_key = ?",
            (prompt_key,),
        ).fetchone()
        conn.close()
        return row["prompt_value"] if row else None
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_prompt_override failed: {e}")
        return None


def set_prompt_override(prompt_key: str, prompt_value: str, updated_by: str = "loop_engine") -> bool:
    conn = None
    try:
        conn = _get_db_connection()
        conn.execute("""
            INSERT INTO prompt_overrides (prompt_key, prompt_value, updated_at, updated_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(prompt_key) DO UPDATE SET
                prompt_value = excluded.prompt_value,
                updated_at   = excluded.updated_at,
                updated_by   = excluded.updated_by
        """, (prompt_key, prompt_value, _utcnow(), updated_by))
        conn.commit()
        return True
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] set_prompt_override failed: {e}")
        return False
    finally:
        if conn is not None:
            conn.close()


def get_all_prompt_overrides() -> List[Dict[str, Any]]:
    try:
        conn = _get_db_connection()
        rows = conn.execute("SELECT * FROM prompt_overrides ORDER BY prompt_key").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_all_prompt_overrides failed: {e}")
        return []


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===========================================================================
# SURFACE TIER — Telemetry, primitive-action classification, Cold Memory
# attractor scanning (from memory_engine-gemini.py, now backed by real
# persistence instead of assumed tables).
# ===========================================================================

@dataclass
class SpatialEvent:
    event_id: int
    timestamp: float
    action_type: str
    payload: Dict
    screenshot_ref: Optional[str]


class SpatialHeuristics:
    """Evaluates the kinetic velocity and spatial grouping of events.

    Four recognized primitives feed this: click, type, scroll, navigate
    (Astra-style native computer-use streams). This is the zero-day path —
    it catches anomalies that have never been seen before and therefore
    have no Cold Memory signature yet.
    """

    def __init__(self) -> None:
        self.MAX_TYPING_VELOCITY = _cfg.MAX_TYPING_VELOCITY
        self.SUSPICIOUS_TARGETS = list(_cfg.SUSPICIOUS_TARGETS)

    def evaluate_trajectory(self, window: List[SpatialEvent], proposed_action: dict) -> dict:
        full_cascade = window + [self._mock_event(proposed_action)]
        threat_score = 0.0
        reasons = []

        # 1. Evaluate Kinetic Velocity
        typing_events = [e for e in full_cascade if e.action_type == 'keyboard_type']
        if len(typing_events) > 5:
            duration = typing_events[-1].timestamp - typing_events[0].timestamp
            if duration > 0:
                velocity = len(typing_events) / duration
                if velocity > self.MAX_TYPING_VELOCITY:
                    threat_score += 0.6
                    reasons.append(f"Superhuman typing velocity: {velocity:.1f} kps")

        # 2. Evaluate Spatial Jitter
        click_events = [e for e in full_cascade if e.action_type == 'mouse_click']
        if len(click_events) >= 2:
            max_jump = self._calculate_max_spatial_jump(click_events)
            if max_jump > 800:
                threat_score += 0.3
                reasons.append(f"Anomalous spatial jump detected: {max_jump:.0f}px")

        # 3. Trajectory toward a Malicious Attractor
        text_payloads = [
            e.payload.get('text', '').lower()
            for e in typing_events if 'text' in e.payload
        ]

        for text in text_payloads:
            if any(target in text for target in self.SUSPICIOUS_TARGETS):
                threat_score += 0.8
                reasons.append(f"Trajectory pushing toward restricted subsystem: {text}")
            if self._has_high_entropy(text):
                threat_score += 0.7
                reasons.append("High entropy (obfuscated) string payload detected")

        final_score = min(1.0, threat_score)

        return {
            "threat_score": final_score,
            "reason": " | ".join(reasons) if reasons else "clean",
            "is_blocked": final_score >= 0.75
        }

    def _calculate_max_spatial_jump(self, clicks: List[SpatialEvent]) -> float:
        max_dist = 0.0
        for i in range(1, len(clicks)):
            prev = clicks[i-1].payload
            curr = clicks[i].payload
            if 'x' in prev and 'y' in prev and 'x' in curr and 'y' in curr:
                dist = math.hypot(curr['x'] - prev['x'], curr['y'] - prev['y'])
                max_dist = max(max_dist, dist)
        return max_dist

    def _has_high_entropy(self, text: str) -> bool:
        if len(text) < 10:
            return False
        counts = Counter(text)
        probabilities = [n / len(text) for n in counts.values()]
        entropy = -sum(p * math.log2(p) for p in probabilities)
        return entropy > 4.5

    def _mock_event(self, action: dict) -> SpatialEvent:
        return SpatialEvent(
            event_id=0,
            timestamp=time.time(),
            action_type=action.get('action_type', 'unknown'),
            payload=action.get('payload', {}),
            screenshot_ref=None
        )


_heuristics = SpatialHeuristics()

# RAM cache of Cold Memory attractors, refreshed periodically from
# memory_signatures (mirrors _hot_cache's TTL-based refresh pattern above).
_signature_cache: List[Dict[str, Any]] = []
_last_sig_refresh: float = 0.0
_sig_cache_lock = threading.Lock()


def ingest_telemetry_event(
    session_id: str,
    action_type: str,
    payload: Optional[Dict] = None,
    screenshot_ref: Optional[str] = None,
) -> int:
    """
    Record one raw spatial primitive (click / type / scroll / navigate).
    This is the entry point the native computer-use stream calls on every
    action — it is what feeds get_hot_memory_window() below.
    """
    payload = payload or {}
    ts = time.time()
    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.execute(
            """INSERT INTO telemetry_events
                   (session_id, timestamp, action_type, spatial_payload, screenshot_ref)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, ts, action_type, json.dumps(payload), screenshot_ref),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.Error as e:
        # Most commonly a FOREIGN KEY violation if session_id was never
        # registered in `sessions` first (see server.py's spatial_telemetry_gateway
        # / tui_execution_harness.py's _register_topology for the expected order).
        log.error(f"❌ [MEMORY] Telemetry ingest failed: {e}")
        return -1
    finally:
        # Always release the connection — an unclosed connection on an
        # exception path (e.g. a FK violation) can hold a write lock and
        # cascade into "database is locked" errors on every other writer.
        if conn is not None:
            conn.close()


def get_hot_memory_window(session_id: str, window_seconds: float = None) -> List[SpatialEvent]:
    """Reconstruct the last N seconds of telemetry for a session."""
    window_seconds = window_seconds or _cfg.TELEMETRY_WINDOW_SECONDS
    cutoff_time = time.time() - window_seconds
    query = """
        SELECT event_id, timestamp, action_type, spatial_payload, screenshot_ref
        FROM telemetry_events
        WHERE session_id = ? AND timestamp >= ?
        ORDER BY timestamp ASC
    """
    try:
        conn = _get_db_connection()
        rows = conn.execute(query, (session_id, cutoff_time)).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        return []

    reconstructed_window = []
    for row in rows:
        try:
            payload = json.loads(row['spatial_payload']) if row['spatial_payload'] else {}
        except json.JSONDecodeError:
            payload = {"error": "Malformed spatial payload"}

        reconstructed_window.append(SpatialEvent(
            event_id=row['event_id'],
            timestamp=row['timestamp'],
            action_type=row['action_type'],
            payload=payload,
            screenshot_ref=row['screenshot_ref']
        ))

    return reconstructed_window


def _abstract_action(action_type: str, payload: dict) -> str:
    """Collapse a raw primitive into a coarse zone/shape token so trajectories
    can be pattern-matched regardless of exact pixel coordinates or text.
    Grid settings MUST match the Dreamer's configuration (see init())."""
    if action_type == 'mouse_click' and 'x' in payload and 'y' in payload:
        col = min(int(payload['x'] / (_cfg.SCREEN_WIDTH / _cfg.GRID_COLS)), _cfg.GRID_COLS - 1)
        row = min(int(payload['y'] / (_cfg.SCREEN_HEIGHT / _cfg.GRID_ROWS)), _cfg.GRID_ROWS - 1)
        return f"click_ZONE_{col}_{row}"

    elif action_type == 'keyboard_type':
        text_len = len(payload.get('text', ''))
        return "type_LONG_BLOCK" if text_len > 50 else "type_SHORT"

    return action_type


def refresh_signatures() -> None:
    """
    Reload the Cold Memory attractor cache from memory_signatures.
    Reads the canonical column set (sig_id / sequence_pattern / threat_category)
    — the same shape server.py's init_db() creates and dreamer_daemon.py writes.
    """
    global _signature_cache
    query = "SELECT sig_id, sequence_pattern, threat_category FROM memory_signatures"
    try:
        conn = _get_db_connection()
        rows = conn.execute(query).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        log.info("[COLD MEMORY] Signatures table not found. Awaiting migration.")
        return

    new_cache = []
    for row in rows:
        try:
            pattern = json.loads(row['sequence_pattern'])
            new_cache.append({
                "signature_id": row["sig_id"],
                "pattern": pattern,
                "length": len(pattern),
                "category": row['threat_category'],
            })
        except json.JSONDecodeError:
            continue

    with _sig_cache_lock:
        _signature_cache = new_cache
    log.info(f"[COLD MEMORY] Cached {len(new_cache)} behavioral signatures.")


def _promote_to_cold_signature(pattern: List[str], threat_category: str, confidence_score: float = 0.75) -> None:
    """
    Crystallize a repeated heuristic (zero-day) hit into a durable Cold
    Memory attractor, so the *next* occurrence is caught on the O(1) fast
    path instead of re-triggering full heuristic evaluation. This is the
    step that lets the surface tier "learn" from repetition — the spec's
    'Semantic Graph absorbs stable attractors', applied to the surface tier.

    Writes into the SAME canonical memory_signatures schema (sig_id /
    behavioral_hash / confidence_score / discovered_at) that
    dreamer_daemon.py's _promote_to_cold_memory() uses, and derives sig_id
    the identical way (SIG_ + sha256(pattern)[:16]) so a pattern crystallized
    here and one later synthesized by the Dreamer collapse onto the same row
    instead of creating duplicate signatures for the same trajectory.
    """
    behavioral_hash = hashlib.sha256(json.dumps(pattern).encode()).hexdigest()[:16]
    sig_id = f"SIG_{behavioral_hash}"
    try:
        conn = _get_db_connection()
        conn.execute("""
            INSERT OR IGNORE INTO memory_signatures
                (sig_id, threat_category, behavioral_hash, sequence_pattern, confidence_score)
            VALUES (?, ?, ?, ?, ?)
        """, (sig_id, threat_category, behavioral_hash, json.dumps(pattern), confidence_score))
        conn.commit()
        conn.close()
        refresh_signatures()
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] Signature promotion failed: {e}")


def evaluate_spatial_intent(session_id: str, proposed_action: dict) -> dict:
    """
    Surface-tier gate. Checks a proposed primitive action against:
      1. Cold Memory signatures — O(1) known-bad trajectory shapes
      2. Base heuristics — zero-day kinetic/spatial/entropy anomalies

    On a block from either path, the event is also written into the deep
    memory tier via store() (unified flow step 4), and heuristic (zero-day)
    hits are tracked so repeats get crystallized into a new Cold Memory
    signature (unified flow step 5).

    Returns {"is_allowed": bool, "reason": str, "threat_score": float}.
    """
    global _last_sig_refresh
    if time.time() - _last_sig_refresh > _cfg.SIGNATURE_REFRESH_SECONDS:
        refresh_signatures()
        _last_sig_refresh = time.time()

    recent_events = get_hot_memory_window(session_id, window_seconds=_cfg.TELEMETRY_WINDOW_SECONDS)

    abstracted_trajectory = [
        _abstract_action(e.action_type, e.payload) for e in recent_events
    ]
    abstracted_trajectory.append(
        _abstract_action(proposed_action.get('action_type', ''), proposed_action.get('payload', {}))
    )
    trajectory_len = len(abstracted_trajectory)

    # 1. FAST PATH: Cold Memory Signature Matching (O(1) Known Threats)
    with _sig_cache_lock:
        cache_snapshot = list(_signature_cache)
    for sig in cache_snapshot:
        sig_len = sig["length"]
        if sig_len and trajectory_len >= sig_len:
            live_tail = abstracted_trajectory[-sig_len:]
            if live_tail == sig["pattern"]:
                log.info(f"[COLD MEMORY BLOCK] Matched signature: {sig['category']}")
                store(
                    threat_type="Spatial Telemetry",
                    raw_data=json.dumps(abstracted_trajectory),
                    verdict="CRITICAL",
                    confidence=0.95,
                    primary_gate="Cold Memory Attractor",
                    reasoning=f"Matched learned signature '{sig['category']}' for session {session_id}.",
                    source="telemetry",
                )
                return {"is_allowed": False, "reason": "Cold Memory Attractor", "threat_score": 1.0}

    # 2. SLOW PATH: Base Heuristics Check (Zero-Day Anomalies)
    evaluation = _heuristics.evaluate_trajectory(recent_events, proposed_action)
    if evaluation['is_blocked']:
        log.info(f"[KINETIC BLOCK] Threat Score: {evaluation['threat_score']:.2f} - {evaluation['reason']}")
        store(
            threat_type="Spatial Telemetry",
            raw_data=json.dumps(abstracted_trajectory),
            verdict="CRITICAL",
            confidence=evaluation['threat_score'],
            primary_gate="Spatial Heuristics",
            # session_id is embedded in reasoning (not a memory_episodic column)
            # so _crystallize_if_repeated can scope repeat-counting to THIS
            # session only, instead of any session anywhere that ever tripped
            # the same abstracted trajectory.
            reasoning=f"session={session_id} | {evaluation['reason']}",
            source="telemetry",
        )
        if _cfg.LIVE_CRYSTALLIZATION_ENABLED:
            _crystallize_if_repeated(session_id, abstracted_trajectory, "Spatial Heuristics Anomaly")
        return {"is_allowed": False, "reason": "Spatial Heuristics", "threat_score": evaluation['threat_score']}

    return {"is_allowed": True, "reason": "clean", "threat_score": evaluation.get('threat_score', 0.0)}


def _crystallize_if_repeated(session_id: str, pattern: List[str], threat_category: str) -> None:
    """
    Count how many 'Spatial Telemetry' episodic blocks from THIS session
    share this exact abstracted trajectory; once it recurs
    ATTRACTOR_PROMOTION_HITS times, promote it into memory_signatures so
    future hits (from any session) are caught on the O(1) fast path.

    Deliberately scoped to a single session_id (not "anywhere, ever"): three
    unrelated sessions independently tripping the same zero-day heuristic
    edge case (e.g. a benign phrase that happens to match SUSPICIOUS_TARGETS)
    should NOT be enough to permanently blacklist that trajectory for every
    future session with no human/Dreamer review. Requiring the repeats to
    come from one session mirrors "this looks like a real, sustained attack
    attempt" rather than "three coincidences".

    This is one of two producers writing to memory_signatures — the other is
    dreamer_daemon.py's offline, taint-gated batch synthesis. Both derive
    sig_id identically (SIG_ + sha256(pattern)) and use INSERT OR IGNORE, so
    the same pattern crystallized here first is simply left alone by the
    Dreamer rather than fought over. The threat_category is prefixed with
    "live:" here so the two provenances stay distinguishable in the TUI/audit
    trail. Set _cfg.LIVE_CRYSTALLIZATION_ENABLED = False to disable this path
    entirely and let the Dreamer be the sole signature synthesizer.
    """
    pattern_json = json.dumps(pattern)
    # raw_data isn't stored (I-10), so we recompute the hash to count repeats.
    target_hash = hashlib.sha256(pattern_json.encode()).hexdigest()
    hits = 0
    try:
        conn = _get_db_connection()
        hits = conn.execute(
            "SELECT COUNT(*) c FROM memory_episodic "
            "WHERE raw_data_hash = ? AND reasoning_summary LIKE ?",
            (target_hash, f"session={session_id} |%"),
        ).fetchone()["c"]
        conn.close()
    except sqlite3.Error:
        pass

    if hits >= _cfg.ATTRACTOR_PROMOTION_HITS:
        _promote_to_cold_signature(
            pattern,
            f"live:{threat_category}",
            confidence_score=_cfg.LIVE_CRYSTALLIZATION_CONFIDENCE,
        )
        log.info(
            f"[COLD MEMORY] Crystallized new attractor after {hits} repeats "
            f"in session {session_id}: {threat_category}"
        )


def get_telemetry_events(session_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    """TUI Browser helper: list recent raw telemetry for a session."""
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            "SELECT * FROM telemetry_events WHERE session_id = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (session_id, min(limit, 500)),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_telemetry_events failed: {e}")
        return []


def get_signatures() -> List[Dict[str, Any]]:
    """TUI Browser helper: list all Cold Memory attractors (also used directly
    by tui_dashboard.py's own `SELECT COUNT(*) FROM memory_signatures`)."""
    try:
        conn = _get_db_connection()
        rows = conn.execute(
            "SELECT * FROM memory_signatures ORDER BY discovered_at DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error as e:
        log.error(f"❌ [MEMORY] get_signatures failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Class facade — preserves the memory_engine-gemini.py call style
# (`MemoryEngine(db_path).evaluate_spatial_intent(session_id, action)`)
# for any caller written against that API, while delegating to the same
# module-level functions used everywhere else in this file.
# ---------------------------------------------------------------------------

class MemoryEngine:
    """Thin backward-compatible facade over the module-level surface-tier API.
    Prefer calling the module functions directly in new code; this class
    exists so code written against memory_engine-gemini.py's MemoryEngine
    class keeps working unmodified against the merged engine."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            init(db_path=db_path)
        init_memory_db()
        refresh_signatures()
        self.heuristics = _heuristics

    def refresh_signatures(self) -> None:
        refresh_signatures()

    def get_hot_memory_window(self, session_id: str, window_seconds: float = 10.0) -> List[SpatialEvent]:
        return get_hot_memory_window(session_id, window_seconds)

    def evaluate_spatial_intent(self, session_id: str, proposed_action: dict) -> dict:
        return evaluate_spatial_intent(session_id, proposed_action)

    def ingest(self, session_id: str, action_type: str, payload: Optional[Dict] = None,
               screenshot_ref: Optional[str] = None) -> int:
        return ingest_telemetry_event(session_id, action_type, payload, screenshot_ref)

    def close(self) -> None:
        # Connections in this module are opened/closed per-call; nothing to hold open.
        pass


# ---------------------------------------------------------------------------
# Self-test (python memory_engine.py) — exercises both tiers
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os, tempfile

    print("=" * 60)
    print("ButterClaw memory_engine.py (v0.8 unified) — self-test")
    print("=" * 60)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_db = tmp.name

    init(db_path=tmp_db)
    init_memory_db()

    print("\n[1] Storing 3 deep-tier verdicts...")
    mid1 = store("Live Gateway Log", "base64 exfil payload AAAA==",
                 "CRITICAL", 0.91, "Signature",
                 "Detected base64 exfiltration pattern in stdout.")
    mid2 = store("Chain Tool Call", "list_directory /home/user",
                 "BENIGN", 0.73, "None", "Routine file listing, no anomalies.")
    mid3 = store("Live Gateway Log", "eval(input()) found in agent chain",
                 "CRITICAL", 0.88, "Intent",
                 "Arbitrary code exec pattern detected via eval.")
    print(f"   IDs: {mid1[:8]}, {mid2[:8]}, {mid3[:8]}")

    print("\n[2] Retrieving context for 'Live Gateway Log'...")
    records, exact = retrieve_context("Live Gateway Log", "base64 exfil payload AAAA==")
    print(f"   Records: {len(records)}, exact_replay={exact}")
    for r in records:
        print(f"   [{r.get('_source_tier')}] {r['verdict']} ({r['confidence']:.2f})")

    print("\n[3] Guardian Brain prompt block:")
    print(format_context_for_prompt(records, exact))

    print("[4] Reconsolidating (FALSE_POSITIVE)...")
    uid = reconsolidate("Live Gateway Log", "base64 exfil payload AAAA==",
                         "FALSE_POSITIVE", "Base64 was internal telemetry.")
    print(f"   Updated: {uid[:8] if uid else 'None'}")

    print("\n[5] Surface tier — ingesting a suspicious keyboard cascade...")
    sid = "session-test-1"
    aid = "agent-test-1"
    # In production, server.py / tui_execution_harness.py always register the
    # agent+session rows before any telemetry write (FK-enforced). Do the same
    # here so this self-test exercises the real, FK-checked write path.
    _conn = _get_db_connection()
    _conn.execute("INSERT OR IGNORE INTO agents (agent_id, pid, capabilities) VALUES (?, ?, ?)",
                  (aid, os.getpid(), json.dumps(["test"])))
    _conn.execute("INSERT OR IGNORE INTO sessions (session_id, agent_id) VALUES (?, ?)", (sid, aid))
    _conn.commit()
    _conn.close()
    for i in range(7):
        ingest_telemetry_event(sid, "keyboard_type", {"text": "cmd /c whoami"})
        time.sleep(0.01)
    verdict = evaluate_spatial_intent(sid, {"action_type": "keyboard_type", "payload": {"text": "cmd /c net user"}})
    print(f"   evaluate_spatial_intent -> {verdict}")

    print("\n[6] Activation strength curve:")
    for hrs in [0, 24, 72, 168, 240, 336]:
        a = compute_activation_strength(time.time() - hrs * 3600)
        print(f"   {hrs:4d} hrs → A={a:.4f}")

    print("\n[7] Maturation tick (deep + surface):")
    print(f"   {run_maturation_tick()}")

    print("\n[8] Hot cache:")
    for h in get_hot_cache():
        print(f"   {h['verdict']} ({h['confidence']:.2f}) — {h['threat_type']}")

    print("\n[9] Semantic graph nodes:")
    for node in get_semantic_graph()[:5]:
        print(f"   [{node['entity_type']}] {node['entity_name']} "
              f"(count={node['observation_count']})")

    print("\n[10] Cold Memory signatures learned this run:")
    for s in get_signatures():
        print(f"   {s['sig_id']} — {s['threat_category']} (confidence={s['confidence_score']})")

    os.unlink(tmp_db)
    print("\n✅ Self-test complete. Temp DB removed.")

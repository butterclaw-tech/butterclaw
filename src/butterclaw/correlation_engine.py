"""
correlation_engine.py — Butterclaw v0.9.0 - src layout
Cross-agent spatial + temporal behavioral pattern correlation.

Role: Detect coordinated patterns across agents that individually stay below
    the single-agent detection threshold.
NOT Responsible For: Kinetic action. CorrelationEvents feed the Fleet Sentinel
    hemisphere and Fleet Memory Corpus only. No direct kill path.
Failure Mode: Window state is backed by the correlation_journal table in
    fleet.db (append-only, deduplicated). On restart, _replay_journal()
    rebuilds in-memory window state. Pod eviction without a mounted volume
    still loses in-progress windows — accepted residual risk per D-26.

Design decisions: D-26 (journal replaces ephemeral windows from D-20).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from butterclaw.fleet_db_init import get_fleet_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config defaults (overridden by server.py from env)
# ---------------------------------------------------------------------------
CORRELATION_WINDOW_MINUTES: int = 30
CORRELATION_FLEET_THRESHOLD: int = 3
TEMPORAL_WINDOW_SECONDS: int = 120
JOURNAL_COMPACTION_INTERVAL_MINUTES: int = 60


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CorrelationEvent:
    event_id: str
    correlation_type: str          # 'spatial' | 'temporal'
    pattern_hash: str
    agent_ids: list[str]
    confidence: float
    fired_at_unix: int = field(default_factory=lambda: int(time.time()))
    active: bool = True

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "correlation_type": self.correlation_type,
            "pattern_hash": self.pattern_hash,
            "agent_ids": self.agent_ids,
            "confidence": self.confidence,
            "fired_at_unix": self.fired_at_unix,
            "active": self.active,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CorrelationEngine:
    """
    Detects two classes of cross-agent coordination:

    Spatial Correlation  — Same abstracted trajectory seen across N distinct
        agents within CORRELATION_WINDOW_MINUTES.
    Temporal Correlation — Sequence of semantically related tool calls across
        distinct agents within TEMPORAL_WINDOW_SECONDS, detecting distributed
        kill chains where work is divided across agents.

    Distinct from CollisionDetector: Correlation detects SAME patterns
    (copycat/broadcast); Collusion detects COMPLEMENTARY patterns (divided labor).
    """

    def __init__(
        self,
        window_minutes: int = CORRELATION_WINDOW_MINUTES,
        fleet_threshold: int = CORRELATION_FLEET_THRESHOLD,
        temporal_window_seconds: int = TEMPORAL_WINDOW_SECONDS,
        compaction_interval_minutes: int = JOURNAL_COMPACTION_INTERVAL_MINUTES,
        on_correlation_event=None,
    ) -> None:
        self._db = get_fleet_db()
        self._window_seconds = window_minutes * 60
        self._fleet_threshold = fleet_threshold
        self._temporal_window = temporal_window_seconds
        self._compaction_interval = compaction_interval_minutes * 60
        self._on_event = on_correlation_event  # callback → HemisphereScheduler

        # In-memory rolling windows rebuilt from journal on startup
        # {pattern_hash: {agent_id: [timestamp, ...]}}
        self._spatial_windows: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        # {tool_name: [(agent_id, tool_args_hash, timestamp), ...]}
        self._temporal_windows: dict[str, list[tuple]] = defaultdict(list)

        self._active_events: dict[str, CorrelationEvent] = {}
        self._lock = threading.Lock()

        self._replay_journal()
        self._start_compaction_thread()

    # ------------------------------------------------------------------
    # Ingest — public API
    # ------------------------------------------------------------------

    def ingest_spatial_event(
        self,
        agent_id: str,
        trajectory_hash: str,
        session_id: str,
        timestamp: Optional[int] = None,
    ) -> Optional[CorrelationEvent]:
        """
        Record a spatial telemetry event and check for cross-agent threshold.
        Returns a CorrelationEvent if the threshold is crossed, else None.
        """
        ts = timestamp or int(time.time())
        pattern_hash = trajectory_hash  # spatial correlation key is the trajectory itself

        self._journal_write(
            pattern_hash=pattern_hash,
            agent_id=agent_id,
            event_type="spatial",
            trajectory_hash=trajectory_hash,
            timestamp_unix=ts,
            session_id=session_id,
        )

        with self._lock:
            window = self._spatial_windows[pattern_hash]
            cutoff = ts - self._window_seconds
            # Prune stale entries for this agent
            window[agent_id] = [t for t in window[agent_id] if t >= cutoff]
            window[agent_id].append(ts)

            # Prune stale entries for all agents
            active_agents = {
                aid: [t for t in times if t >= cutoff]
                for aid, times in window.items()
            }
            active_agents = {aid: times for aid, times in active_agents.items() if times}
            self._spatial_windows[pattern_hash] = defaultdict(list, active_agents)

            if len(active_agents) >= self._fleet_threshold:
                return self._fire_correlation_event(
                    "spatial", pattern_hash, list(active_agents.keys())
                )
        return None

    def ingest_tool_event(
        self,
        agent_id: str,
        tool_name: str,
        tool_args_hash: str,
        session_id: str,
        timestamp: Optional[int] = None,
    ) -> Optional[CorrelationEvent]:
        """
        Record a tool-call event and check for temporal cross-agent sequences.
        Uses the existing mcp_events table data — no new data source needed.
        """
        ts = timestamp or int(time.time())
        pattern_hash = hashlib.sha256(
            f"{tool_name}:{tool_args_hash}".encode()
        ).hexdigest()[:16]

        self._journal_write(
            pattern_hash=pattern_hash,
            agent_id=agent_id,
            event_type="temporal",
            tool_name=tool_name,
            tool_args_hash=tool_args_hash,
            timestamp_unix=ts,
            session_id=session_id,
        )

        with self._lock:
            cutoff = ts - self._temporal_window
            seq = self._temporal_windows[tool_name]
            seq = [(aid, ah, t) for aid, ah, t in seq if t >= cutoff]
            seq.append((agent_id, tool_args_hash, ts))
            self._temporal_windows[tool_name] = seq

            distinct_agents = {aid for aid, _, _ in seq}
            if len(distinct_agents) >= self._fleet_threshold:
                return self._fire_correlation_event(
                    "temporal", pattern_hash, list(distinct_agents)
                )
        return None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_active_correlations(self) -> list[dict]:
        with self._lock:
            return [e.as_dict() for e in self._active_events.values() if e.active]

    def get_all_correlations(self, status: str = "all") -> list[dict]:
        with self._lock:
            events = list(self._active_events.values())
        if status == "active":
            events = [e for e in events if e.active]
        elif status == "expired":
            events = [e for e in events if not e.active]
        return [e.as_dict() for e in events]

    def flush_expired_windows(self) -> None:
        """Expire active CorrelationEvents whose contributing agents have left the window."""
        now = int(time.time())
        cutoff = now - self._window_seconds
        with self._lock:
            for event in self._active_events.values():
                if event.active and event.fired_at_unix < cutoff:
                    event.active = False
                    logger.debug("CorrelationEvent expired: %s", event.event_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fire_correlation_event(
        self, correlation_type: str, pattern_hash: str, agent_ids: list[str]
    ) -> CorrelationEvent:
        event_id = hashlib.sha256(
            f"{correlation_type}:{pattern_hash}:{sorted(agent_ids)}".encode()
        ).hexdigest()[:24]

        if event_id in self._active_events:
            existing = self._active_events[event_id]
            existing.agent_ids = list(set(existing.agent_ids) | set(agent_ids))
            logger.debug("CorrelationEvent updated: %s agents=%s", event_id, existing.agent_ids)
            return existing

        confidence = min(1.0, len(agent_ids) / max(self._fleet_threshold, 1))
        event = CorrelationEvent(
            event_id=event_id,
            correlation_type=correlation_type,
            pattern_hash=pattern_hash,
            agent_ids=agent_ids,
            confidence=confidence,
        )
        self._active_events[event_id] = event
        logger.warning(
            "CorrelationEvent fired: type=%s pattern=%s agents=%s confidence=%.2f",
            correlation_type, pattern_hash, agent_ids, confidence,
        )

        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                logger.exception("Error dispatching CorrelationEvent to callback")

        return event

    def _journal_write(self, **kwargs) -> None:
        """Append an event to the correlation_journal with deduplication."""
        with self._db:
            self._db.execute(
                """
                INSERT OR IGNORE INTO correlation_journal
                    (pattern_hash, agent_id, event_type, trajectory_hash,
                     tool_name, tool_args_hash, timestamp_unix, session_id)
                VALUES (:pattern_hash, :agent_id, :event_type, :trajectory_hash,
                        :tool_name, :tool_args_hash, :timestamp_unix, :session_id)
                """,
                {
                    "pattern_hash": kwargs.get("pattern_hash"),
                    "agent_id": kwargs.get("agent_id"),
                    "event_type": kwargs.get("event_type"),
                    "trajectory_hash": kwargs.get("trajectory_hash"),
                    "tool_name": kwargs.get("tool_name"),
                    "tool_args_hash": kwargs.get("tool_args_hash"),
                    "timestamp_unix": kwargs.get("timestamp_unix"),
                    "session_id": kwargs.get("session_id"),
                },
            )

    def _replay_journal(self) -> None:
        """Rebuild in-memory window state from the journal on startup (R-02)."""
        cutoff = int(time.time()) - self._window_seconds
        rows = self._db.execute(
            """
            SELECT * FROM correlation_journal
            WHERE timestamp_unix > ?
            ORDER BY timestamp_unix ASC
            """,
            (cutoff,),
        ).fetchall()

        replayed = 0
        for row in rows:
            r = dict(row)
            if r["event_type"] == "spatial":
                self._spatial_windows[r["pattern_hash"]][r["agent_id"]].append(r["timestamp_unix"])
            elif r["event_type"] == "temporal" and r["tool_name"]:
                self._temporal_windows[r["tool_name"]].append(
                    (r["agent_id"], r["tool_args_hash"], r["timestamp_unix"])
                )
            replayed += 1

        logger.info("CorrelationEngine: replayed %d journal rows", replayed)

    def _start_compaction_thread(self) -> None:
        """Background thread that compacts expired journal rows (×2 window multiplier)."""
        def _compact():
            while True:
                time.sleep(self._compaction_interval)
                cutoff = int(time.time()) - self._window_seconds * 2
                try:
                    with self._db:
                        self._db.execute(
                            "DELETE FROM correlation_journal WHERE timestamp_unix < ?",
                            (cutoff,),
                        )
                    logger.debug("correlation_journal compacted (cutoff=%d)", cutoff)
                except Exception:
                    logger.exception("Journal compaction error")

        t = threading.Thread(target=_compact, daemon=True, name="journal-compaction")
        t.start()

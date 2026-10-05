"""
fleet_registry.py — Butterclaw v0.9.0
Persistent cross-session agent registry with asymmetric reputation scoring.

Role: Track all agents observed across sessions and container restarts.
NOT Responsible For: Making kinetic decisions. Reputation scores are enrichment
    for the Fleet Sentinel hemisphere only, never a direct kill trigger.
Failure Mode: If fleet.db is unavailable at startup, fleet_db_init.py raises
    a fatal error before routes are bound. This module never starts in a
    silently-degraded state.

Invariant: I-01-fleet — fleet.db is included in the Docker volume backup.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from butterclaw.fleet_db_init import get_fleet_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (overridden via env/config in server.py)
# ---------------------------------------------------------------------------
REPUTATION_DECAY_RATIO: float = 3.0   # taint hits this many times harder than recovery
_REPUTATION_RECOVERY_UNIT: float = 1.0


class FleetRegistry:
    """Persistent SQLite-backed registry of all observed agents."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, reputation_decay_ratio: float = REPUTATION_DECAY_RATIO) -> None:
        self._db = get_fleet_db()
        self._decay_ratio = reputation_decay_ratio
        logger.info("FleetRegistry initialised (decay_ratio=%.1f)", self._decay_ratio)

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        session_id: str,
        parent_agent_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> None:
        """Upsert an agent record and increment session_count."""
        now = int(time.time())
        with self._db:
            self._db.execute(
                """
                INSERT INTO fleet_agents
                    (agent_id, display_name, first_seen_unix, last_seen_unix,
                     session_count, parent_agent_id)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    last_seen_unix = excluded.last_seen_unix,
                    session_count  = fleet_agents.session_count + 1,
                    display_name   = COALESCE(excluded.display_name, fleet_agents.display_name)
                """,
                (agent_id, display_name, now, now, parent_agent_id),
            )
        logger.debug("register_agent agent_id=%s session_id=%s", agent_id, session_id)

    def record_taint(self, agent_id: str) -> None:
        """Apply an asymmetric reputation penalty for a taint event."""
        penalty = self._decay_ratio
        with self._db:
            self._db.execute(
                """
                UPDATE fleet_agents
                SET taint_count      = taint_count + 1,
                    reputation_score = MAX(0.0, reputation_score - ?)
                WHERE agent_id = ?
                """,
                (penalty, agent_id),
            )
        logger.info("record_taint agent_id=%s penalty=%.1f", agent_id, penalty)

    def record_clean_session(self, agent_id: str) -> None:
        """Apply a reputation recovery increment for a clean completed session."""
        with self._db:
            self._db.execute(
                """
                UPDATE fleet_agents
                SET reputation_score = MIN(1.0, reputation_score + ?)
                WHERE agent_id = ?
                """,
                (_REPUTATION_RECOVERY_UNIT, agent_id),
            )
        logger.debug("record_clean_session agent_id=%s", agent_id)

    def set_role(self, agent_id: str, role: str) -> None:
        """
        Assign a semantic role to an agent.
        role must be one of: orchestrator | worker | peer | unknown | quarantined
        """
        _VALID_ROLES = {"orchestrator", "worker", "peer", "unknown", "quarantined"}
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of {_VALID_ROLES}")
        with self._db:
            self._db.execute(
                "UPDATE fleet_agents SET role = ? WHERE agent_id = ?",
                (role, agent_id),
            )
        logger.info("set_role agent_id=%s role=%s", agent_id, role)

    def soft_delete(self, agent_id: str) -> None:
        """Mark an agent as deleted (never physically removed, I-01-fleet)."""
        with self._db:
            self._db.execute(
                "UPDATE fleet_agents SET deleted_at = ? WHERE agent_id = ?",
                (int(time.time()), agent_id),
            )
        logger.info("soft_delete agent_id=%s", agent_id)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_profile(self, agent_id: str) -> Optional[dict]:
        """Return the full registry profile for an agent, or None if not found."""
        row = self._db.execute(
            "SELECT * FROM fleet_agents WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_fleet_snapshot(self) -> list[dict]:
        """Return all non-deleted agent profiles ordered by reputation_score ASC."""
        rows = self._db.execute(
            """
            SELECT * FROM fleet_agents
            WHERE deleted_at IS NULL
            ORDER BY reputation_score ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_agents_paginated(self, page: int = 0, page_size: int = 50) -> list[dict]:
        """Paginated list for GET /api/fleet/agents."""
        offset = page * page_size
        rows = self._db.execute(
            """
            SELECT * FROM fleet_agents
            WHERE deleted_at IS NULL
            ORDER BY last_seen_unix DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
        return [dict(r) for r in rows]

"""
fleet_memory.py — Butterclaw v0.9.0
Fleet-scope semantic entity promotion + per-agent behavioral baselines.

Role: Extend memory_engine.py's semantic graph to fleet scope with cross-agent
    entity promotion and per-agent behavioral baselines.
NOT Responsible For: Kinetic action. format_fleet_context_for_prompt() is
    read-only enrichment for hemisphere prompts — same constraint as I-12-mem.
Failure Mode: If fleet.db is unavailable, format_fleet_context_for_prompt()
    returns an empty context dict. The Fleet Sentinel still fires but with no
    fleet memory enrichment; logs WARN. Individual-agent detection is unaffected.

Invariants: I-03-fleet (cross-fleet crystallisation requires human gate).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from butterclaw.fleet_db_init import get_fleet_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config defaults (overridden by server.py from env)
# ---------------------------------------------------------------------------
FLEET_PROMOTION_THRESHOLD: int = 3   # distinct sessions before promotion is eligible


class FleetMemory:
    """
    Two additions to the existing memory model:

    1. Fleet Semantic Nodes — adds scope column ('session'|'fleet') on
       memory_semantic. Promotion from session→fleet requires:
           (a) entity appears in ≥ FLEET_PROMOTION_THRESHOLD distinct sessions
           (b) Fleet Sentinel CORRELATED or COLLUDING verdict
           (c) FLEET_SENTINEL_DRY_RUN=false
           (d) admin confirms via DELETE /api/fleet/correlations/<id>/promote
       No automated promotion path exists (I-03-fleet).

    2. Fleet Baselines — rolling behavioral baseline per agent_id stored in
       fleet_baselines. Recomputed by Fleet Sentinel hemisphere, not on every event.
    """

    def __init__(self, promotion_threshold: int = FLEET_PROMOTION_THRESHOLD) -> None:
        self._db = get_fleet_db()
        self._threshold = promotion_threshold
        logger.info("FleetMemory initialised (promotion_threshold=%d)", self._threshold)

    # ------------------------------------------------------------------
    # Promotion (I-03-fleet — human-gated; this method is the admin confirm step)
    # ------------------------------------------------------------------

    def promote_entity_to_fleet(self, entity_id: str) -> bool:
        """
        Promote a session-scoped semantic entity to fleet scope.
        Returns True if promotion was applied; False if entity does not exist,
        is already promoted, or has not met the session threshold.

        This method is called ONLY from the admin confirm endpoint
        (DELETE /api/fleet/correlations/<event_id>/promote). It must never
        be called from any automated code path.
        """
        row = self._db.execute(
            "SELECT scope FROM memory_semantic WHERE id = ?", (entity_id,)
        ).fetchone()
        if not row:
            logger.warning("promote_entity_to_fleet: entity %s not found", entity_id)
            return False
        if row["scope"] == "fleet":
            logger.info("promote_entity_to_fleet: entity %s already fleet-scoped", entity_id)
            return False

        # Verify cross-session appearance count
        count = self._count_sessions_for_entity(entity_id)
        if count < self._threshold:
            logger.warning(
                "promote_entity_to_fleet: entity %s only appears in %d sessions "
                "(threshold=%d) — promotion denied",
                entity_id, count, self._threshold,
            )
            return False

        with self._db:
            self._db.execute(
                "UPDATE memory_semantic SET scope = 'fleet' WHERE id = ?", (entity_id,)
            )
        logger.info("promote_entity_to_fleet: entity %s promoted to fleet scope", entity_id)
        return True

    def demote_entity_to_session(self, entity_id: str) -> bool:
        """
        Demote a fleet-scoped semantic entity back to session scope.
        Called from DELETE /api/fleet/correlations/<event_id>/promote (admin).
        Does NOT automatically remove Cold Memory fast-path signatures —
        that requires a separate DELETE /api/memory/signatures/<sig_id>.
        """
        with self._db:
            result = self._db.execute(
                "UPDATE memory_semantic SET scope = 'session' WHERE id = ? AND scope = 'fleet'",
                (entity_id,),
            )
        if result.rowcount == 0:
            logger.warning("demote_entity_to_session: entity %s not found or not fleet-scoped", entity_id)
            return False
        logger.info("demote_entity_to_session: entity %s demoted to session scope", entity_id)
        return True

    # ------------------------------------------------------------------
    # Baselines
    # ------------------------------------------------------------------

    def update_baseline(self, agent_id: str, current_session_profile: dict) -> None:
        """
        Recompute and persist the behavioral baseline for agent_id.
        Called by the Fleet Sentinel hemisphere, not on every event.

        current_session_profile expected keys:
            tool_call_distribution : dict  (tool_name → count)
            session_duration_s     : float
            action_count           : int
        """
        existing = self._db.execute(
            "SELECT * FROM fleet_baselines WHERE agent_id = ?", (agent_id,)
        ).fetchone()

        now = int(time.time())
        new_dist = json.dumps(current_session_profile.get("tool_call_distribution", {}))
        new_dur = float(current_session_profile.get("session_duration_s", 0.0))
        new_actions = float(current_session_profile.get("action_count", 0))

        if existing:
            # Rolling average with the existing baseline (simple EMA α=0.3)
            alpha = 0.3
            avg_dur = alpha * new_dur + (1 - alpha) * (existing["avg_session_duration_s"] or new_dur)
            avg_actions = alpha * new_actions + (1 - alpha) * (existing["avg_action_count"] or new_actions)
            with self._db:
                self._db.execute(
                    """
                    UPDATE fleet_baselines
                    SET tool_call_distribution = ?,
                        avg_session_duration_s = ?,
                        avg_action_count       = ?,
                        last_computed_unix     = ?
                    WHERE agent_id = ?
                    """,
                    (new_dist, avg_dur, avg_actions, now, agent_id),
                )
        else:
            with self._db:
                self._db.execute(
                    """
                    INSERT INTO fleet_baselines
                        (agent_id, tool_call_distribution,
                         avg_session_duration_s, avg_action_count, last_computed_unix)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (agent_id, new_dist, new_dur, new_actions, now),
                )

        logger.debug("update_baseline agent_id=%s", agent_id)

    def get_baseline_delta(
        self, agent_id: str, current_session_profile: dict
    ) -> Optional[dict]:
        """
        Compute the delta between agent's stored baseline and current session profile.
        Returns None if no baseline exists yet.
        """
        row = self._db.execute(
            "SELECT * FROM fleet_baselines WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if not row:
            return None

        current_dur = float(current_session_profile.get("session_duration_s", 0.0))
        current_actions = float(current_session_profile.get("action_count", 0))
        baseline_dist = json.loads(row["tool_call_distribution"] or "{}")
        current_dist = current_session_profile.get("tool_call_distribution", {})

        # Compute tool distribution divergence (simple symmetric difference count)
        all_tools = set(baseline_dist) | set(current_dist)
        dist_delta = {
            tool: current_dist.get(tool, 0) - baseline_dist.get(tool, 0)
            for tool in all_tools
        }

        return {
            "agent_id": agent_id,
            "duration_delta_s": current_dur - (row["avg_session_duration_s"] or 0.0),
            "action_count_delta": current_actions - (row["avg_action_count"] or 0.0),
            "tool_distribution_delta": dist_delta,
            "baseline_last_computed_unix": row["last_computed_unix"],
        }

    # ------------------------------------------------------------------
    # Context for hemisphere prompts
    # ------------------------------------------------------------------

    def get_fleet_context(self, agent_ids: list[str]) -> dict:
        """
        Return fleet-scope semantic entities and baselines for the given agents.
        Used by Fleet Sentinel hemisphere as read-only enrichment.
        """
        try:
            fleet_entities = self._db.execute(
                """
                SELECT * FROM memory_semantic
                WHERE scope = 'fleet'
                ORDER BY id DESC LIMIT 100
                """
            ).fetchall()

            baselines = {}
            for agent_id in agent_ids:
                row = self._db.execute(
                    "SELECT * FROM fleet_baselines WHERE agent_id = ?", (agent_id,)
                ).fetchone()
                if row:
                    baselines[agent_id] = dict(row)

            return {
                "fleet_entities": [dict(e) for e in fleet_entities],
                "agent_baselines": baselines,
            }
        except Exception:
            logger.warning("get_fleet_context: fleet.db unavailable; returning empty context")
            return {}

    def format_fleet_context_for_prompt(self, agent_ids: list[str]) -> dict:
        """
        Read-only enrichment dict for hemisphere prompt construction.
        Returns {} if fleet.db is unavailable (Fleet Sentinel logs WARN and
        proceeds without fleet memory enrichment).
        """
        try:
            ctx = self.get_fleet_context(agent_ids)
            if not ctx:
                logger.warning(
                    "format_fleet_context_for_prompt: empty context for agents %s", agent_ids
                )
            return ctx
        except Exception:
            logger.warning("format_fleet_context_for_prompt: returning empty context dict")
            return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_sessions_for_entity(self, entity_id: str) -> int:
        """Count distinct session_ids in which this entity appears."""
        row = self._db.execute(
            """
            SELECT COUNT(DISTINCT session_id) AS cnt
            FROM memory_semantic
            WHERE id = ? OR parent_entity_id = ?
            """,
            (entity_id, entity_id),
        ).fetchone()
        return row["cnt"] if row else 0

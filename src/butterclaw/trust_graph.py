"""
trust_graph.py — Butterclaw v0.9.0 - src layout
Directed weighted agent relationship graph with taint propagation.

Role: Track spawn/comm/peer edges between agents and propagate reputation
    penalties when an agent is tainted.
NOT Responsible For: Direct kinetic action. Trust score of 0.0 does NOT kill
    a process. It informs the Fleet Sentinel which escalates through Guardian
    Brain + DRIFT + Paranoia Dial per I-02-fleet and I-04-fleet.
Failure Mode: Trust graph edges are persisted in fleet.db. An unavailable
    fleet.db is fatal at startup per fleet_db_init.py.

Invariants: I-02-fleet, I-05-fleet (one-hop propagation default).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from butterclaw.fleet_db_init import get_fleet_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config defaults (overridden by server.py from env)
# ---------------------------------------------------------------------------
TRUST_PROPAGATION_FACTOR: float = 0.3
TRUST_PROPAGATION_DEPTH: int = 1       # 1 or 2 only; see I-05-fleet
TRUST_DECAY_RATE: float = 0.01         # per hour for inactive edges

EDGE_TYPES = frozenset({"spawn", "comm", "peer"})


class TrustGraph:
    """
    Directed weighted graph of agent relationships.

    Edge types:
        spawn  — parent_agent spawned child_agent (OS / semantic lineage)
        comm   — observed inter-agent communication
        peer   — lateral peer relationship (same orchestrator, same tier)

    Trust propagation (I-05-fleet):
        When agent X is tainted, all agents with a spawn or comm edge pointing
        TO X receive a trust score penalty of edge_weight × TRUST_PROPAGATION_FACTOR.
        Default depth is 1. 2-hop requires TRUST_PROPAGATION_DEPTH=2 in config.
    """

    def __init__(
        self,
        propagation_factor: float = TRUST_PROPAGATION_FACTOR,
        propagation_depth: int = TRUST_PROPAGATION_DEPTH,
        decay_rate: float = TRUST_DECAY_RATE,
    ) -> None:
        self._db = get_fleet_db()
        self._factor = propagation_factor
        self._depth = min(max(propagation_depth, 1), 2)   # clamp to 1–2
        self._decay_rate = decay_rate
        logger.info(
            "TrustGraph initialised (factor=%.2f, depth=%d, decay=%.4f/hr)",
            self._factor, self._depth, self._decay_rate,
        )

    # ------------------------------------------------------------------
    # Edge recording
    # ------------------------------------------------------------------

    def record_spawn(self, parent_id: str, child_id: str) -> None:
        """Record that parent_id spawned child_id."""
        self._upsert_edge(parent_id, child_id, "spawn")
        self._record_trust_event(parent_id, child_id, "spawn_observed", delta=0.0)
        logger.debug("record_spawn parent=%s child=%s", parent_id, child_id)

    def record_communication(self, src_id: str, dst_id: str) -> None:
        """Record observed inter-agent communication from src to dst."""
        self._upsert_edge(src_id, dst_id, "comm")
        self._record_trust_event(src_id, dst_id, "comm_observed", delta=0.0)
        logger.debug("record_communication src=%s dst=%s", src_id, dst_id)

    def record_peer(self, agent_a: str, agent_b: str) -> None:
        """Record a lateral peer relationship between two agents."""
        self._upsert_edge(agent_a, agent_b, "peer")
        self._upsert_edge(agent_b, agent_a, "peer")

    # ------------------------------------------------------------------
    # Taint propagation
    # ------------------------------------------------------------------

    def propagate_taint(self, tainted_agent_id: str) -> list[str]:
        """
        Propagate a taint penalty to agents with edges pointing TO the tainted agent.
        Returns the list of affected agent IDs.

        Per I-05-fleet: one-hop by default. Two-hop only if TRUST_PROPAGATION_DEPTH=2.
        """
        affected: list[str] = []
        targets = self._get_upstream_agents(tainted_agent_id)

        for src_agent_id, edge_weight, edge_type in targets:
            if edge_type not in ("spawn", "comm"):
                continue
            penalty = edge_weight * self._factor
            self._apply_trust_penalty(src_agent_id, tainted_agent_id, penalty)
            affected.append(src_agent_id)

        if self._depth == 2 and affected:
            # Second-hop: propagate from directly-affected agents
            for intermediate_id in list(affected):
                second_hop = self._get_upstream_agents(intermediate_id)
                for src_id, edge_weight, edge_type in second_hop:
                    if edge_type not in ("spawn", "comm") or src_id in affected:
                        continue
                    # Attenuated second-hop penalty
                    penalty = edge_weight * self._factor * self._factor
                    self._apply_trust_penalty(src_id, intermediate_id, penalty)
                    affected.append(src_id)

        logger.info(
            "propagate_taint tainted=%s affected=%s depth=%d",
            tainted_agent_id, affected, self._depth,
        )
        return affected

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_trust_score(self, agent_id: str) -> float:
        """
        Compute the current aggregate trust score for an agent.
        Returns 1.0 (full trust) if the agent has no edges yet.
        Score is bounded [0.0, 1.0].
        """
        edges = self._db.execute(
            "SELECT weight FROM trust_edges WHERE src_agent_id = ? OR dst_agent_id = ?",
            (agent_id, agent_id),
        ).fetchall()
        if not edges:
            return 1.0
        avg_weight = sum(r["weight"] for r in edges) / len(edges)
        return round(max(0.0, min(1.0, avg_weight)), 4)

    def get_neighbors(
        self, agent_id: str, edge_type: Optional[str] = None
    ) -> list[dict]:
        """Return all agents connected to agent_id, optionally filtered by edge_type."""
        if edge_type:
            rows = self._db.execute(
                """
                SELECT * FROM trust_edges
                WHERE (src_agent_id = ? OR dst_agent_id = ?) AND edge_type = ?
                """,
                (agent_id, agent_id, edge_type),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM trust_edges WHERE src_agent_id = ? OR dst_agent_id = ?",
                (agent_id, agent_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_full_snapshot(self) -> dict:
        """Return the complete graph as nodes + edges for GET /api/fleet/trust-graph."""
        agents = self._db.execute(
            "SELECT agent_id, reputation_score, role FROM fleet_agents WHERE deleted_at IS NULL"
        ).fetchall()
        edges = self._db.execute("SELECT * FROM trust_edges").fetchall()
        return {
            "nodes": [dict(a) for a in agents],
            "edges": [dict(e) for e in edges],
        }

    def apply_trust_decay(self) -> None:
        """
        Decay inactive edge weights by TRUST_DECAY_RATE per elapsed hour.
        Called by the background maintenance task; active comms reset the timer.
        """
        now = int(time.time())
        edges = self._db.execute(
            "SELECT src_agent_id, dst_agent_id, edge_type, weight, last_updated_unix "
            "FROM trust_edges"
        ).fetchall()
        for row in edges:
            elapsed_hours = (now - row["last_updated_unix"]) / 3600.0
            decay = elapsed_hours * self._decay_rate
            new_weight = max(0.0, row["weight"] - decay)
            with self._db:
                self._db.execute(
                    """
                    UPDATE trust_edges SET weight = ?
                    WHERE src_agent_id = ? AND dst_agent_id = ? AND edge_type = ?
                    """,
                    (new_weight, row["src_agent_id"], row["dst_agent_id"], row["edge_type"]),
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert_edge(self, src: str, dst: str, edge_type: str) -> None:
        now = int(time.time())
        with self._db:
            self._db.execute(
                """
                INSERT INTO trust_edges
                    (src_agent_id, dst_agent_id, weight, edge_type, created_unix, last_updated_unix)
                VALUES (?, ?, 1.0, ?, ?, ?)
                ON CONFLICT(src_agent_id, dst_agent_id, edge_type) DO UPDATE SET
                    last_updated_unix = excluded.last_updated_unix,
                    weight = MIN(1.0, trust_edges.weight + 0.05)
                """,
                (src, dst, edge_type, now, now),
            )

    def _apply_trust_penalty(
        self, src_agent_id: str, dst_agent_id: str, penalty: float
    ) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE trust_edges
                SET weight = MAX(0.0, weight - ?)
                WHERE src_agent_id = ? AND dst_agent_id = ?
                """,
                (penalty, src_agent_id, dst_agent_id),
            )
        self._record_trust_event(src_agent_id, dst_agent_id, "taint_propagation", -penalty)

    def _record_trust_event(
        self, src: str, dst: str, event_type: str, delta: float
    ) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT INTO trust_events
                    (src_agent_id, dst_agent_id, event_type, delta, timestamp_unix)
                VALUES (?, ?, ?, ?, ?)
                """,
                (src, dst, event_type, delta, int(time.time())),
            )

    def _get_upstream_agents(self, target_agent_id: str) -> list[tuple]:
        """Return (src_agent_id, weight, edge_type) for edges pointing TO target."""
        rows = self._db.execute(
            """
            SELECT src_agent_id, weight, edge_type
            FROM trust_edges
            WHERE dst_agent_id = ?
            """,
            (target_agent_id,),
        ).fetchall()
        return [(r["src_agent_id"], r["weight"], r["edge_type"]) for r in rows]

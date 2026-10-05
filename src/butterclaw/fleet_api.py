"""
fleet_api.py — Butterclaw v0.9.0
14 new /api/fleet/* routes. Total API route count: 77 (63 v0.8 + 14 new).

Registration: register_fleet_routes(app, fleet_registry, trust_graph,
    correlation_engine, collusion_detector, fleet_sentinel)
    — follows the register_X_routes(app) convention from existing modules (D-19).

RBAC tiers (same 4-tier system as existing routes):
    viewer   — read-only fleet data
    operator — read + manual trigger + feedback
    admin    — full fleet management including quarantine and entity demotion

Failure: Returns 503 if any dependent component is unavailable.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Quarantine token store (in-memory; short-lived 60s TTL per R-06)
# ---------------------------------------------------------------------------
_quarantine_tokens: dict[str, dict] = {}  # token → {agent_id, expires_unix, operator_id}
QUARANTINE_TOKEN_TTL = 60  # seconds


def _issue_quarantine_token(agent_id: str, operator_id: str) -> str:
    token = f"qtok_{secrets.token_hex(16)}"
    _quarantine_tokens[token] = {
        "agent_id": agent_id,
        "expires_unix": int(time.time()) + QUARANTINE_TOKEN_TTL,
        "operator_id": operator_id,
    }
    return token


def _consume_quarantine_token(token: str) -> dict | None:
    """Consume a token, returning its payload if valid and not expired."""
    entry = _quarantine_tokens.pop(token, None)
    if not entry:
        return None
    if int(time.time()) > entry["expires_unix"]:
        return None
    return entry


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_fleet_routes(
    app,
    fleet_registry,
    trust_graph,
    correlation_engine,
    collusion_detector,
    fleet_sentinel,
    fleet_memory=None,
    require_role=None,      # decorator factory: require_role('viewer') etc.
    get_current_operator=None,
    get_request_ip=None,
):
    """
    Register all 14 /api/fleet/* routes on the provided Flask (or compatible) app.

    Parameters
    ----------
    require_role : callable, optional
        Decorator factory that enforces RBAC. If None, routes are unprotected
        (development only — always provide in production).
    get_current_operator : callable, optional
        Returns the current operator's ID string from request context.
    get_request_ip : callable, optional
        Returns the client IP string from request context.
    """
    from flask import jsonify, request  # type: ignore

    # Fallback stubs for development
    def _noop_decorator(fn):
        return fn

    def _noop_role(_role):
        return _noop_decorator

    def _unknown_operator():
        return "unknown"

    def _unknown_ip():
        return "0.0.0.0"

    _require = require_role or _noop_role
    _operator = get_current_operator or _unknown_operator
    _ip = get_request_ip or _unknown_ip

    def _component_guard(*components):
        """Return 503 if any component is None."""
        for c in components:
            if c is None:
                return jsonify({"error": "Fleet component unavailable"}), 503
        return None

    # ------------------------------------------------------------------
    # GET /api/fleet/agents  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents", methods=["GET"])
    @_require("viewer")
    def fleet_list_agents():
        guard = _component_guard(fleet_registry)
        if guard:
            return guard
        try:
            page = int(request.args.get("page", 0))
            page_size = min(int(request.args.get("page_size", 50)), 200)
            agents = fleet_registry.get_agents_paginated(page, page_size)
            return jsonify({"agents": agents, "page": page, "page_size": page_size})
        except Exception as exc:
            logger.exception("fleet_list_agents error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/agents/<agent_id>  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents/<agent_id>", methods=["GET"])
    @_require("viewer")
    def fleet_get_agent(agent_id):
        guard = _component_guard(fleet_registry, trust_graph)
        if guard:
            return guard
        try:
            profile = fleet_registry.get_profile(agent_id)
            if not profile:
                return jsonify({"error": "Agent not found"}), 404

            neighbors = trust_graph.get_neighbors(agent_id)
            trust_score = trust_graph.get_trust_score(agent_id)
            baseline_delta = None
            if fleet_memory:
                baseline_delta = fleet_memory.get_baseline_delta(agent_id, {})

            # Compute recommended_actions when quarantined with active sessions
            recommended_actions = []
            if profile.get("role") == "quarantined" and profile.get("session_count", 0) > 0:
                recommended_actions.append({
                    "action": "POST /api/spatial/block",
                    "urgency": "high",
                    "reason": (
                        "Agent is quarantined but may have active processes. "
                        "Quarantine does not terminate active processes — use /api/spatial/block."
                    ),
                })

            return jsonify({
                **profile,
                "trust_score": trust_score,
                "trust_neighbors": neighbors,
                "baseline_delta": baseline_delta,
                "recommended_actions": recommended_actions,
            })
        except Exception as exc:
            logger.exception("fleet_get_agent error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/trust-graph  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/trust-graph", methods=["GET"])
    @_require("viewer")
    def fleet_trust_graph():
        guard = _component_guard(trust_graph)
        if guard:
            return guard
        try:
            return jsonify(trust_graph.get_full_snapshot())
        except Exception as exc:
            logger.exception("fleet_trust_graph error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/correlations  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/correlations", methods=["GET"])
    @_require("viewer")
    def fleet_correlations():
        guard = _component_guard(correlation_engine)
        if guard:
            return guard
        try:
            status = request.args.get("status", "all")
            page = int(request.args.get("page", 0))
            events = correlation_engine.get_all_correlations(status=status)
            page_size = 50
            paginated = events[page * page_size : (page + 1) * page_size]
            return jsonify({
                "events": paginated,
                "total": len(events),
                "page": page,
                "status_filter": status,
            })
        except Exception as exc:
            logger.exception("fleet_correlations error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/collusion-events  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/collusion-events", methods=["GET"])
    @_require("viewer")
    def fleet_collusion_events():
        guard = _component_guard(collusion_detector)
        if guard:
            return guard
        try:
            page = int(request.args.get("page", 0))
            events = collusion_detector.get_all_collusion_events()
            page_size = 50
            paginated = events[page * page_size : (page + 1) * page_size]
            return jsonify({"events": paginated, "total": len(events), "page": page})
        except Exception as exc:
            logger.exception("fleet_collusion_events error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/sentinel-log  (viewer)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/sentinel-log", methods=["GET"])
    @_require("viewer")
    def fleet_sentinel_log():
        guard = _component_guard(fleet_sentinel)
        if guard:
            return guard
        try:
            from butterclaw.fleet_db_init import get_fleet_db
            db = get_fleet_db()
            page = int(request.args.get("page", 0))
            page_size = 50
            offset = page * page_size
            rows = db.execute(
                """
                SELECT id, triggered_by, verdict, confidence, implicated_agent_ids,
                       insufficient_reason, operator_feedback, follow_up_required,
                       dry_run, escalated_to_guardian, timestamp_unix
                FROM fleet_sentinel_log
                ORDER BY timestamp_unix DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
            return jsonify({"log": [dict(r) for r in rows], "page": page})
        except Exception as exc:
            logger.exception("fleet_sentinel_log error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # POST /api/fleet/sentinel/trigger  (operator)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/sentinel/trigger", methods=["POST"])
    @_require("operator")
    def fleet_sentinel_trigger():
        guard = _component_guard(fleet_sentinel)
        if guard:
            return guard
        try:
            verdict = fleet_sentinel.run_manual()
            if verdict is None:
                return jsonify({"status": "rate_limited", "message": "Event coalesced into next cycle"}), 202
            return jsonify({"status": "ok", "verdict": verdict.as_dict()})
        except Exception as exc:
            logger.exception("fleet_sentinel_trigger error")
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # POST /api/fleet/agents/<agent_id>/quarantine  (admin) — Step 1: Flag
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents/<agent_id>/quarantine", methods=["POST"])
    @_require("admin")
    def fleet_quarantine_flag(agent_id):
        guard = _component_guard(fleet_registry)
        if guard:
            return guard
        try:
            profile = fleet_registry.get_profile(agent_id)
            if not profile:
                return jsonify({"error": "Agent not found"}), 404
            if profile.get("role") == "quarantined":
                # Idempotent — 409 Conflict per R-06
                return jsonify({"error": "Agent is already quarantined", "conflict": True}), 409

            operator_id = _operator()
            ip_address = _ip()
            token = _issue_quarantine_token(agent_id, operator_id)

            # Audit log — action=flagged
            from butterclaw.fleet_db_init import get_fleet_db
            db = get_fleet_db()
            with db:
                db.execute(
                    """
                    INSERT INTO quarantine_audit_log
                        (agent_id, action, operator_id, ip_address, confirmation_token)
                    VALUES (?, 'flagged', ?, ?, ?)
                    """,
                    (agent_id, operator_id, ip_address, token),
                )

            logger.info("fleet_quarantine_flag: agent=%s operator=%s ip=%s", agent_id, operator_id, ip_address)

            return jsonify({
                "confirmation_token": token,
                "expires_in_seconds": QUARANTINE_TOKEN_TTL,
                "agent_id": agent_id,
                "current_reputation": profile.get("reputation_score", 1.0),
                "active_sessions": [],  # TODO: join with active session table
                "warning": (
                    "Quarantine will set reputation to 0.0 and block new sessions "
                    "but will NOT terminate active processes. "
                    "Use /api/spatial/block to terminate active processes."
                ),
            })
        except Exception as exc:
            logger.exception("fleet_quarantine_flag error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # POST /api/fleet/agents/<agent_id>/quarantine/confirm  (admin) — Step 2
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents/<agent_id>/quarantine/confirm", methods=["POST"])
    @_require("admin")
    def fleet_quarantine_confirm(agent_id):
        guard = _component_guard(fleet_registry, trust_graph, fleet_sentinel)
        if guard:
            return guard
        try:
            body = request.get_json(force=True) or {}
            token = body.get("confirmation_token")
            if not token:
                return jsonify({"error": "confirmation_token required"}), 400

            entry = _consume_quarantine_token(token)
            if not entry:
                # Audit log — token_expired or not found
                from butterclaw.fleet_db_init import get_fleet_db
                db = get_fleet_db()
                with db:
                    db.execute(
                        """
                        INSERT INTO quarantine_audit_log
                            (agent_id, action, operator_id, ip_address, confirmation_token)
                        VALUES (?, 'token_expired', ?, ?, ?)
                        """,
                        (agent_id, _operator(), _ip(), token),
                    )
                return jsonify({"error": "Invalid or expired confirmation token"}), 400

            if entry["agent_id"] != agent_id:
                return jsonify({"error": "Token does not match agent_id"}), 400

            # Apply quarantine side effects (R-06)
            fleet_registry.set_role(agent_id, "quarantined")
            fleet_registry.record_taint(agent_id)
            # Force reputation to 0.0 (quarantine sets it explicitly)
            from butterclaw.fleet_db_init import get_fleet_db
            db = get_fleet_db()
            with db:
                db.execute(
                    "UPDATE fleet_agents SET reputation_score = 0.0 WHERE agent_id = ?",
                    (agent_id,),
                )

            # Taint propagation through trust graph
            trust_graph.propagate_taint(agent_id)

            # Reactive Fleet Sentinel cycle
            fleet_sentinel.run_reactive({
                "type": "collusion_event",
                "reason": "quarantine_confirmed",
                "agent_id": agent_id,
            })

            # Audit log — confirmed
            with db:
                result = db.execute(
                    """
                    INSERT INTO quarantine_audit_log
                        (agent_id, action, operator_id, ip_address, confirmation_token)
                    VALUES (?, 'confirmed', ?, ?, ?)
                    """,
                    (agent_id, entry["operator_id"], _ip(), token),
                )
                audit_log_id = result.lastrowid

            logger.warning("fleet_quarantine_confirm: agent=%s QUARANTINED", agent_id)

            return jsonify({
                "status": "quarantined",
                "reputation_score": 0.0,
                "role": "quarantined",
                "audit_log_id": audit_log_id,
            })
        except Exception as exc:
            logger.exception("fleet_quarantine_confirm error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # DELETE /api/fleet/agents/<agent_id>/quarantine  (admin) — Release
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents/<agent_id>/quarantine", methods=["DELETE"])
    @_require("admin")
    def fleet_quarantine_release(agent_id):
        guard = _component_guard(fleet_registry)
        if guard:
            return guard
        try:
            profile = fleet_registry.get_profile(agent_id)
            if not profile:
                return jsonify({"error": "Agent not found"}), 404
            if profile.get("role") != "quarantined":
                return jsonify({"error": "Agent is not quarantined"}), 409

            fleet_registry.set_role(agent_id, "unknown")
            # Reputation recovery starts from 0.0 — asymmetric per I-02-fleet
            # (Memory Engine taint is NOT removed — taint is permanent evidence)

            from butterclaw.fleet_db_init import get_fleet_db
            db = get_fleet_db()
            with db:
                db.execute(
                    """
                    INSERT INTO quarantine_audit_log
                        (agent_id, action, operator_id, ip_address)
                    VALUES (?, 'released', ?, ?)
                    """,
                    (agent_id, _operator(), _ip()),
                )

            logger.info("fleet_quarantine_release: agent=%s released", agent_id)
            return jsonify({"status": "released", "agent_id": agent_id})
        except Exception as exc:
            logger.exception("fleet_quarantine_release error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # DELETE /api/fleet/agents/<agent_id>  (admin) — Soft delete
    # ------------------------------------------------------------------
    @app.route("/api/fleet/agents/<agent_id>", methods=["DELETE"])
    @_require("admin")
    def fleet_delete_agent(agent_id):
        guard = _component_guard(fleet_registry)
        if guard:
            return guard
        try:
            profile = fleet_registry.get_profile(agent_id)
            if not profile:
                return jsonify({"error": "Agent not found"}), 404
            fleet_registry.soft_delete(agent_id)
            logger.info("fleet_delete_agent: agent=%s soft-deleted", agent_id)
            return jsonify({"status": "deleted", "agent_id": agent_id})
        except Exception as exc:
            logger.exception("fleet_delete_agent error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # GET /api/fleet/baseline/<agent_id>  (operator)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/baseline/<agent_id>", methods=["GET"])
    @_require("operator")
    def fleet_get_baseline(agent_id):
        guard = _component_guard(fleet_memory)
        if guard:
            return guard
        try:
            delta = fleet_memory.get_baseline_delta(agent_id, {})
            if delta is None:
                return jsonify({"message": "No baseline recorded yet", "agent_id": agent_id}), 404
            return jsonify(delta)
        except Exception as exc:
            logger.exception("fleet_get_baseline error agent_id=%s", agent_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # POST /api/fleet/sentinel-log/<log_id>/feedback  (operator)
    # ------------------------------------------------------------------
    @app.route("/api/fleet/sentinel-log/<int:log_id>/feedback", methods=["POST"])
    @_require("operator")
    def fleet_sentinel_feedback(log_id):
        guard = _component_guard(fleet_sentinel)
        if guard:
            return guard
        try:
            body = request.get_json(force=True) or {}
            feedback = body.get("feedback")
            notes = body.get("notes", "")
            if not feedback:
                return jsonify({"error": "feedback field required"}), 400

            operator_id = _operator()
            ok = fleet_sentinel.submit_feedback(log_id, feedback, operator_id)
            if not ok:
                return jsonify({"error": "Log entry not found"}), 404

            logger.info(
                "fleet_sentinel_feedback: log_id=%d feedback=%s operator=%s",
                log_id, feedback, operator_id,
            )
            return jsonify({"status": "ok", "log_id": log_id, "feedback": feedback})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logger.exception("fleet_sentinel_feedback error log_id=%d", log_id)
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # DELETE /api/fleet/correlations/<event_id>/promote  (admin)
    # Demote a fleet-promoted entity back to session scope
    # ------------------------------------------------------------------
    @app.route("/api/fleet/correlations/<event_id>/promote", methods=["DELETE"])
    @_require("admin")
    def fleet_demote_entity(event_id):
        guard = _component_guard(fleet_memory)
        if guard:
            return guard
        try:
            # event_id here is the semantic entity_id (per spec section 12)
            ok = fleet_memory.demote_entity_to_session(event_id)
            if not ok:
                return jsonify({
                    "error": "Entity not found or not fleet-scoped",
                    "note": (
                        "Cold Memory fast-path signatures are NOT automatically removed. "
                        "Call DELETE /api/memory/signatures/<sig_id> separately."
                    ),
                }), 404
            return jsonify({
                "status": "demoted",
                "entity_id": event_id,
                "note": (
                    "Entity demoted to session scope. "
                    "Cold Memory fast-path signature (if any) must be removed separately "
                    "via DELETE /api/memory/signatures/<sig_id>."
                ),
            })
        except Exception as exc:
            logger.exception("fleet_demote_entity error event_id=%s", event_id)
            return jsonify({"error": str(exc)}), 500

    logger.info(
        "register_fleet_routes: registered 14 /api/fleet/* routes "
        "(total API routes: 77)"
    )

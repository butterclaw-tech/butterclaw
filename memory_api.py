"""
ButterClaw v0.8 — Memory API
============================================================
The third and final module from the original v0.8 design roadmap
(memory_engine.py + dream_engine.py + loop_engine.py were built first).
Flask route registration for memory/dream/loop management — read visibility
into all three hemispheres this v0.8 pass added (Deep/Surface Memory, Dream
Weaver, Loop Proposer), plus the handful of admin actions each one exposes
publicly (flush, manual trigger, prompt-override approval).

Convention note: the original roadmap phrasing was "9 new Flask Blueprint
routes." This codebase does not actually use Flask's Blueprint object
anywhere — auth.py's `register_auth_routes(app)` is the established pattern
(a plain function that takes the live `app` object and registers routes
directly on it with `@app.route`), and this file follows that same
convention for consistency rather than introducing Blueprint as a new,
one-off pattern. Functionally equivalent; matches what's already here.

Registered from server.py as:
    from memory_api import register_memory_routes
    register_memory_routes(app, dream_engine, loop_engine)

placed AFTER `dream_engine = DreamEngine(...)` and `loop_engine =
LoopEngine(...)` are constructed, since this module needs the live instances
(to call .trigger_now() / .run_cycle()) — not just their classes. The
memory-only routes need no such instance; they call memory_engine's own
module-level functions directly (`import memory_engine as mem`, the same
pattern dream_engine.py and loop_engine.py already use).

Auth: every route uses the existing `require_auth(min_role=...)` decorator
from auth.py — no new auth mechanism introduced. Role assignments follow the
precedent already set by the /api/policies routes in server.py: GET = viewer,
state-changing-but-reversible = operator, destructive or trust-elevating =
admin.

Routes (12 total — the roadmap's "9" was an estimate, not a contract):

  Deep + Surface Memory:
    GET    /api/memory/hot                    viewer
    GET    /api/memory/episodic               viewer
    DELETE /api/memory/episodic/<memory_id>   admin
    GET    /api/memory/semantic               viewer
    POST   /api/memory/flush                  operator
    GET    /api/memory/signatures             viewer

  Dream Weaver:
    GET    /api/dream/log                     viewer
    POST   /api/dream/trigger                 operator

  Loop Proposer:
    GET    /api/loop/experiments               viewer
    POST   /api/loop/trigger                   operator
    GET    /api/loop/prompts                   viewer
    POST   /api/loop/prompts/<prompt_key>      admin

I-12/I-13/I-15 note: every route here is either a pure READ (the majority)
or an explicitly-scoped admin action (flush hot cache to disk, manually
kick off a dream/loop cycle, or write a prompt_overrides row) — nothing in
this file can trigger a kinetic action (no topology_manager, no
watcher_daemon, no alert_dispatcher calls anywhere below). The prompt-write
route only stages a row in memory_engine.prompt_overrides; per that table's
own schema comment, server.py does not yet read it when building a live
prompt, so even that write is inert until server.py is separately updated
to consult it.
"""

from __future__ import annotations

from typing import Any

from flask import request, jsonify

import memory_engine as mem
from auth import require_auth


def register_memory_routes(app, dream_engine_instance: Any, loop_engine_instance: Any) -> None:
    """Register all memory/dream/loop management endpoints on the Flask app."""

    # =============================================
    # DEEP + SURFACE MEMORY
    # =============================================

    @app.route('/api/memory/hot', methods=['GET'])
    @require_auth(min_role="viewer")
    def memory_hot_endpoint():
        """Live hot-cache entries (Tier 1) — whatever hasn't expired or been flushed yet."""
        entries = mem.get_hot_cache()
        return jsonify({"entries": entries, "count": len(entries)}), 200

    @app.route('/api/memory/episodic', methods=['GET'])
    @require_auth(min_role="viewer")
    def memory_episodic_endpoint():
        """Paginated Tier 2 (Warm Episodic) reader."""
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        records = mem.get_episodic(limit=limit, offset=offset)
        return jsonify({"records": records, "count": len(records)}), 200

    @app.route('/api/memory/episodic/<memory_id>', methods=['DELETE'])
    @require_auth(min_role="admin")
    def memory_episodic_delete_endpoint(memory_id):
        """Hard-delete a single episodic record. Destructive — admin only."""
        if not mem.delete_episodic(memory_id):
            return jsonify({"error": "Memory record not found"}), 404
        return jsonify({"status": "deleted", "memory_id": memory_id}), 200

    @app.route('/api/memory/semantic', methods=['GET'])
    @require_auth(min_role="viewer")
    def memory_semantic_endpoint():
        """Tier 3 (Cold Semantic) entity graph — nodes + weighted edges."""
        graph = mem.get_semantic_graph()
        return jsonify({"nodes": graph, "count": len(graph)}), 200

    @app.route('/api/memory/flush', methods=['POST'])
    @require_auth(min_role="operator")
    def memory_flush_endpoint():
        """Force-flush all live hot-cache entries into the episodic store now,
        instead of waiting for TTL expiry or the next natural write."""
        count = mem.flush_hot_to_episodic()
        return jsonify({"status": "flushed", "count": count}), 200

    @app.route('/api/memory/signatures', methods=['GET'])
    @require_auth(min_role="viewer")
    def memory_signatures_endpoint():
        """Cold Memory attractors (memory_signatures) — from both
        dreamer_daemon.py's offline batch synthesis and memory_engine.py's
        own scoped live crystallization (tagged 'live:' in threat_category)."""
        signatures = mem.get_signatures()
        return jsonify({"signatures": signatures, "count": len(signatures)}), 200

    # =============================================
    # DREAM WEAVER
    # =============================================

    @app.route('/api/dream/log', methods=['GET'])
    @require_auth(min_role="viewer")
    def dream_log_endpoint():
        """Paginated dream_log reader — every consolidation/REM cycle that has run."""
        limit = request.args.get('limit', 50, type=int)
        entries = mem.get_dream_log(limit=limit)
        return jsonify({"entries": entries, "count": len(entries)}), 200

    @app.route('/api/dream/trigger', methods=['POST'])
    @require_auth(min_role="operator")
    def dream_trigger_endpoint():
        """
        Manually kick off a dream cycle now, bypassing the idle-threshold wait.
        Still fully subject to I-13 (hardcoded dry-run) and I-14 (yields to
        live traffic mid-cycle) inside dream_engine.py itself — this route
        cannot override either safeguard, it can only ask the engine to start
        sooner than its own idle poll would have.
        """
        if dream_engine_instance is None:
            return jsonify({"error": "Dream engine not initialized"}), 503
        started = dream_engine_instance.trigger_now()
        if not started:
            return jsonify({"status": "already_running"}), 409
        return jsonify({"status": "triggered"}), 202

    # =============================================
    # LOOP PROPOSER
    # =============================================

    @app.route('/api/loop/experiments', methods=['GET'])
    @require_auth(min_role="viewer")
    def loop_experiments_endpoint():
        """Paginated loop_experiments reader — every proposal this run has scored,
        whether dry_run_only, committed, reverted, or needs_review (prompts)."""
        limit = request.args.get('limit', 50, type=int)
        status = request.args.get('status')
        experiments = mem.get_loop_experiments(limit=limit, status=status)
        return jsonify({"experiments": experiments, "count": len(experiments)}), 200

    @app.route('/api/loop/trigger', methods=['POST'])
    @require_auth(min_role="operator")
    def loop_trigger_endpoint():
        """
        Manually run one loop_engine proposal cycle now, instead of waiting
        for the next scheduled interval. Subject to the SAME LOOP_DRY_RUN /
        I-15 gating as a scheduled cycle — this route does not grant any
        additional authority; a dry_run engine still only produces a scored,
        uncommitted experiment record.
        """
        if loop_engine_instance is None:
            return jsonify({"error": "Loop engine not initialized"}), 503
        result = loop_engine_instance.run_cycle()
        if result is None:
            return jsonify({"status": "no_proposal", "reason": "nothing to replay or propose this cycle"}), 200
        return jsonify({"status": "completed", "result": result}), 200

    @app.route('/api/loop/prompts', methods=['GET'])
    @require_auth(min_role="viewer")
    def loop_prompts_endpoint():
        """
        List all staged prompt_overrides. NOTE: server.py does not currently
        read this table when building the Guardian Brain / Auditor / Dream
        Weaver system prompts (they're still hardcoded string literals) — so
        every row here is staged, not live, until that separate wiring exists.
        """
        overrides = mem.get_all_prompt_overrides()
        return jsonify({"overrides": overrides, "count": len(overrides)}), 200

    @app.route('/api/loop/prompts/<prompt_key>', methods=['POST'])
    @require_auth(min_role="admin")
    def loop_prompts_set_endpoint(prompt_key):
        """
        Stage (create or overwrite) a prompt override. This is the
        highest-trust write in this file — admin only, by design (I-15's
        prompt exception: no proposal or replay score can auto-approve a
        prompt change, a human must explicitly write/approve the text via
        this route). Also the intended approval path for any future
        loop_engine proposal of experiment_type='prompt' — see
        PromptArtifactAdapter in loop_engine.py.
        """
        data = request.json or {}
        prompt_value = data.get("prompt_value")
        if not prompt_value or not str(prompt_value).strip():
            return jsonify({"error": "Missing or empty 'prompt_value' in request body"}), 400
        ok = mem.set_prompt_override(
            prompt_key, prompt_value,
            updated_by=request.auth_context.get("key_id", "unknown"),
        )
        if not ok:
            return jsonify({"error": "Failed to write prompt override"}), 500
        return jsonify({"status": "staged", "prompt_key": prompt_key}), 200

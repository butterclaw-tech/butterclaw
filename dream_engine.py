"""
ButterClaw v0.8 — Dream Engine (Deep Memory / REM Hemisphere)
==============================================================
Idle-triggered sleep cycle for the DEEP memory tier (memory_episodic /
memory_semantic) — NOT to be confused with dreamer_daemon.py, which already
exists in this file set and does something adjacent but different.

    dreamer_daemon.py  (already built, surface tier)
        Runs constantly on a 2-second poll. Reads raw `telemetry_events` from
        sessions that are already tainted/ended, extracts N-gram behavioral
        attractors, and writes them straight into `memory_signatures`
        (Cold Memory). Purely mechanical — no LLM call, no idle detection,
        no notion of the deep episodic/semantic tier at all.

    dream_engine.py    (this file, deep tier)
        Fires only after the system has been idle for IDLE_THRESHOLD_MINUTES.
        Its job is twofold:
          1. Consolidation — calls memory_engine.run_maturation_tick(), which
             ages activation_strength, promotes matured episodes to the
             semantic graph, prunes stale ones, and decays low-confidence
             Cold Memory signatures. Nothing in the current v0.8.0 file set
             calls this today — it has been sitting unused since
             memory_engine.py was built.
          2. REM dreaming — synthesizes a small number of speculative,
             plausible-but-unconfirmed threat scenarios from the existing
             semantic graph ("what haven't I seen combined together yet?"),
             and primes memory with them via
             memory_engine.store(..., source="dream") — memory_engine.py's
             format_context_for_prompt() already special-cases
             source == "dream" with a "[DREAM-PRIMED]" tag, so this was
             always the intended hook; nothing wired into it until now.

Four-Hemisphere role (per the v0.8 design doc):
    Hemisphere      Temp   Fires When          Mandate
    Guardian Brain  0.3    Every request       Evaluate and propose action
    Auditor         0.0    30s post-CRITICAL   Was I wrong?
    Dream Weaver    0.7    Idle >= 15 min      What haven't I seen?   <- this file
    Loop Proposer   0.4    Every 6 hours       How can I get better?  <- loop_engine.py (not built yet)

Safety invariants:
  I-13 — REM dreaming is hardcoded DRY_RUN — this module NEVER calls anything
         that can take kinetic action (no topology_manager, no watcher_daemon,
         no alert_dispatcher). It only ever writes read-only, source="dream"
         memory rows and dream_log entries. DREAM_DRY_RUN below is a literal
         Python constant, not read from config.cfg.DRY_RUN / env — it cannot
         be flipped by an operator toggling the system's live-traffic Gibson
         dry-run gate. If you ever need dreaming to do more than write memory,
         that is a deliberate, separate change to this file, not a config flip.
  I-14 — Dream cycle yields immediately to live traffic. Implemented via
         polling (see _is_idle / _activity_fingerprint) rather than a shared
         cross-module interrupt object, so this module stays self-contained
         like every other daemon in this file set (dreamer_daemon.py,
         archiver_daemon.py, watcher_daemon.py) — none of them import each
         other or share in-process signaling either.
  I-10/I-11/I-12 — inherited unchanged from memory_engine.py; this module
         never touches raw_data and only ever calls memory_engine's public
         read-only-context / write-only-episodic API.

LLM wiring (deliberately NOT guessed): synthesizing a REM scenario needs an
LLM call, and server.py owns all model-routing state (routing_mode,
remote_endpoint, model_name, _call_brain_api) as mutable module globals.
Importing server.py from here would re-run its whole startup (Flask app,
init_db(), spawning the MCP subprocess, other daemons) — it is not meant to
be imported as a library. So this module takes an optional `llm_caller`
callback injected by whoever constructs it (server.py), instead of reaching
into server.py's internals itself. Without one, consolidation still runs
every cycle; only the REM scenario-synthesis step is skipped (logged, not
silently dropped). See the bottom of this file for the exact wiring snippet.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import memory_engine as mem

log = logging.getLogger("butterclaw.dream")
log.setLevel(logging.INFO)
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)

# ---------------------------------------------------------------------------
# I-13 — hardcoded, not sourced from config/env. See module docstring.
# ---------------------------------------------------------------------------
DREAM_DRY_RUN: bool = True

# Contract for the injected LLM callback: takes the same
# `[{"role": ..., "content": ...}, ...]` message-list shape server.py already
# builds for the Guardian Brain / Auditor calls, returns the raw text content
# (or None on failure). Kept intentionally minimal so server.py can wrap
# whatever routing/retry logic it already has (_call_brain_api, etc.)
# without this module needing to know about it.
LLMCaller = Callable[[List[Dict[str, str]]], Optional[str]]


def _default_db_path() -> str:
    return "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"


class DreamEngine:
    """
    Idle-triggered deep-memory consolidation + REM scenario synthesis.

    Usage (from server.py, alongside the other v0.8.0 daemons):

        from dream_engine import DreamEngine
        dream_engine = DreamEngine(db_path=DB_PATH, llm_caller=_dream_llm_call)
        dream_engine.start()

    where `_dream_llm_call(messages) -> Optional[str]` is a small wrapper
    server.py defines around its existing `_call_brain_api` (see the wiring
    snippet at the bottom of this file for the exact shape).
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        llm_caller: Optional[LLMCaller] = None,
        idle_threshold_minutes: float = 15.0,
        poll_interval_seconds: float = 60.0,
        max_scenarios_per_cycle: int = 3,
        temperature: float = 0.7,  # Dream Weaver hemisphere per the 4-hemisphere spec
    ) -> None:
        self.db_path = db_path or _default_db_path()
        # Keep memory_engine pointed at the SAME db (mirrors how every other
        # daemon in this suite explicitly binds to /data/butterclaw.db to
        # avoid the "split-brain ghost database" bug fixed in the v0.8.0 changelog).
        mem.init(db_path=self.db_path)
        mem.init_memory_db()

        self.llm_caller = llm_caller
        self.idle_threshold_seconds = idle_threshold_minutes * 60.0
        self.poll_interval_seconds = poll_interval_seconds
        self.max_scenarios_per_cycle = max_scenarios_per_cycle
        self.temperature = temperature

        self.is_running = True
        self._dreaming = False
        self._worker_thread: Optional[threading.Thread] = None

        assert DREAM_DRY_RUN is True, "I-13 violation: dreaming must stay dry-run-only"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launches the background idle-watch + dream-cycle worker thread."""
        self._worker_thread = threading.Thread(target=self._loop, daemon=True)
        self._worker_thread.start()
        log.info(
            f"[DREAM ENGINE] Active. Idle threshold={self.idle_threshold_seconds/60:.0f}min, "
            f"poll={self.poll_interval_seconds:.0f}s, "
            f"llm_caller={'wired' if self.llm_caller else 'NOT wired (consolidation-only mode)'}"
        )

    def shutdown(self) -> None:
        self.is_running = False

    def trigger_now(self) -> bool:
        """
        Public manual-trigger entry point — added for memory_api.py's
        POST /api/dream/trigger route. Deliberately ignores the idle
        threshold: an explicit admin request to dream now IS the
        yield-worthy signal, no need to wait for the next idle poll.
        Returns False if a cycle is already running (this engine has a
        single worker thread and _run_dream_cycle is not reentrant) so the
        caller can report "already in progress" instead of silently
        queuing a second overlapping cycle.
        """
        if self._dreaming:
            return False
        threading.Thread(target=self._run_dream_cycle, daemon=True).start()
        return True

    # ------------------------------------------------------------------
    # Idle detection (I-14 groundwork) — polling based, no shared state
    # with other modules. "Activity" = any new row in mcp_events or
    # telemetry_events since we last looked.
    # ------------------------------------------------------------------

    def _activity_fingerprint(self) -> float:
        """
        Returns the most recent activity timestamp (unix epoch) across the
        two live-traffic ledgers. 0.0 if neither table exists yet or both
        are empty (treated as "idle" — nothing to defer to).
        """
        latest = 0.0
        conn = None
        try:
            conn = mem._get_db_connection()

            try:
                row = conn.execute("SELECT MAX(timestamp) AS t FROM telemetry_events").fetchone()
                if row and row["t"]:
                    latest = max(latest, float(row["t"]))
            except sqlite3.OperationalError:
                pass  # table not migrated yet — treat as no spatial activity

            try:
                # mcp_events.timestamp is stored as an ISO-ish TEXT string by
                # server.py, not a unix float — compare lexicographically is
                # unsafe across formats, so we just check for *any* row more
                # recent than our own last poll via rowid growth instead.
                row = conn.execute("SELECT MAX(id) AS m FROM mcp_events").fetchone()
                if row and row["m"] is not None:
                    if row["m"] != getattr(self, "_last_mcp_event_id", None):
                        latest = max(latest, time.time())
                    self._last_mcp_event_id = row["m"]
            except sqlite3.OperationalError:
                pass  # mcp_events not present (e.g. standalone test DB)

        except sqlite3.Error as e:
            log.error(f"❌ [DREAM ENGINE] Activity check failed: {e}")
        finally:
            if conn is not None:
                conn.close()

        return latest

    def _is_idle(self) -> bool:
        last_activity = self._activity_fingerprint()
        if last_activity <= 0.0:
            return True
        return (time.time() - last_activity) >= self.idle_threshold_seconds

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self.is_running:
            time.sleep(self.poll_interval_seconds)
            if not self.is_running:
                break
            if self._dreaming:
                continue  # a cycle is already running (shouldn't happen — single worker thread)
            if self._is_idle():
                self._run_dream_cycle()

    # ------------------------------------------------------------------
    # One dream cycle: consolidate, then (optionally) synthesize scenarios.
    # Aborts immediately if live activity reappears (I-14).
    # ------------------------------------------------------------------

    def _run_dream_cycle(self) -> None:
        self._dreaming = True
        cycle_start = time.time()
        activity_at_start = self._activity_fingerprint()
        proposals_generated = 0
        consolidations = 0
        pruned = 0
        status = "completed"
        notes_parts: List[str] = []

        def interrupted() -> bool:
            """I-14: if new live traffic appeared since we started, bail."""
            return self._activity_fingerprint() > activity_at_start

        try:
            log.info("💤 [DREAM ENGINE] Idle threshold reached — starting dream cycle.")

            # --- Step 1: Consolidation (deep tier maturation) -------------
            tick_stats = mem.run_maturation_tick()
            consolidations = tick_stats.get("promoted_to_semantic", 0)
            pruned = tick_stats.get("pruned", 0)
            notes_parts.append(f"maturation={tick_stats}")

            if interrupted():
                status = "interrupted"
                notes_parts.append("interrupted after maturation tick")
                return

            # --- Step 2: REM scenario synthesis (optional — needs llm_caller)
            if self.llm_caller is None:
                notes_parts.append("no llm_caller wired — skipped REM synthesis")
                log.info("[DREAM ENGINE] No llm_caller configured; consolidation-only cycle.")
            else:
                proposals_generated = self._synthesize_scenarios(interrupted)
                notes_parts.append(f"scenarios_synthesized={proposals_generated}")

        except Exception as e:  # noqa: BLE001 — a dream cycle must never crash the daemon
            status = "failed"
            notes_parts.append(f"error={e}")
            log.error(f"❌ [DREAM ENGINE] Dream cycle failed: {e}")
        finally:
            duration = time.time() - cycle_start
            mem.log_dream_cycle(
                phase="dream_weaver",
                duration_seconds=duration,
                proposals_generated=proposals_generated,
                consolidations=consolidations,
                pruned_count=pruned,
                status=status,
                notes=" | ".join(notes_parts)[:500],
            )
            log.info(
                f"✅ [DREAM ENGINE] Cycle {status} in {duration:.1f}s — "
                f"consolidated={consolidations} pruned={pruned} proposals={proposals_generated}"
            )
            self._dreaming = False

    # ------------------------------------------------------------------
    # REM scenario synthesis
    # ------------------------------------------------------------------

    def _synthesize_scenarios(self, interrupted: Callable[[], bool]) -> int:
        """
        Ask the LLM to imagine plausible-but-unconfirmed attack scenarios by
        combining entities already present in the semantic graph, then prime
        memory with each one via store(..., source="dream") — DRY_RUN: this
        never calls policy/topology/watcher, it only ever writes an episodic
        memory row tagged "dream" so a future retrieve_context() can surface
        it as [DREAM-PRIMED] enrichment (I-12: read-only context).
        """
        graph = mem.get_semantic_graph()
        if not graph:
            log.info("[DREAM ENGINE] Semantic graph is empty — nothing to dream about yet.")
            return 0

        # Seed the prompt with the most-observed entities — the patterns the
        # system has actually seen enough to trust are "real" building blocks.
        top_entities = [n["entity_name"] for n in graph[:12]]

        written = 0
        for i in range(self.max_scenarios_per_cycle):
            if interrupted():
                log.info("[DREAM ENGINE] Live traffic detected — yielding mid-synthesis (I-14).")
                break

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are the ButterClaw Dream Weaver. You do not take action and you "
                        "are not evaluating a real event. Given a list of previously-observed "
                        "threat entities/patterns, imagine ONE plausible novel attack scenario "
                        "that combines two or more of them in a way the system has not "
                        "explicitly logged before. Respond in JSON: "
                        '{"scenario": "...", "combined_entities": ["...", "..."], '
                        '"why_plausible": "..."}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"Known entities/patterns: {json.dumps(top_entities)}",
                },
            ]

            try:
                raw = self.llm_caller(messages)
                if not raw:
                    continue
                parsed = json.loads(raw)
                scenario = parsed.get("scenario", "").strip()
                if not scenario:
                    continue
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                log.error(f"❌ [DREAM ENGINE] Malformed scenario response, skipping: {e}")
                continue
            except Exception as e:  # noqa: BLE001 — never let a bad LLM call kill the cycle
                log.error(f"❌ [DREAM ENGINE] llm_caller failed: {e}")
                break

            # DRY_RUN write: source="dream" — read-only enrichment (I-12),
            # never a real verdict, never triggers kinetic action (I-13/I-10).
            mem.store(
                threat_type="Dream Synthesis",
                raw_data=scenario,
                verdict="SIMULATED",
                confidence=0.0,
                primary_gate="Dream Weaver",
                reasoning=parsed.get("why_plausible", scenario)[:200],
                source="dream",
            )
            written += 1
            log.info(f"🌙 [DREAM ENGINE] Primed scenario #{written}: {scenario[:80]}...")

        return written


# ---------------------------------------------------------------------------
# Self-test (python dream_engine.py) — exercises the module standalone,
# without any llm_caller (consolidation-only path), same pattern as
# memory_engine.py's own __main__ self-test.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    print("=" * 60)
    print("ButterClaw dream_engine.py — self-test")
    print("=" * 60)

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    mem.init(db_path=tmp_db)
    mem.init_memory_db()

    # Seed some deep-tier memory so there's something to consolidate/dream about.
    mem.store("Live Gateway Log", "base64 exfil payload AAAA==", "CRITICAL", 0.91,
               "Signature", "Detected base64 exfiltration pattern in stdout.")
    mem.store("Chain Tool Call", "list_directory /home/user", "BENIGN", 0.73,
               "None", "Routine file listing, no anomalies.")
    time.sleep(0.2)  # let the async episodic persist land

    print("\n[1] Forcing a dream cycle with NO llm_caller (consolidation-only)...")
    engine = DreamEngine(db_path=tmp_db, poll_interval_seconds=9999)
    engine._run_dream_cycle()
    print(f"   dream_log: {mem.get_dream_log(limit=1)}")

    print("\n[2] Forcing a dream cycle WITH a fake llm_caller (REM synthesis)...")

    def fake_llm_caller(messages):
        return json.dumps({
            "scenario": "Agent pastes a base64 payload immediately after a routine "
                        "directory listing, disguising exfiltration as normal chain activity.",
            "combined_entities": ["live_gateway_log", "chain_tool_call"],
            "why_plausible": "Both patterns were observed independently; chaining them "
                              "would blend exfiltration into benign-looking traffic.",
        })

    engine2 = DreamEngine(db_path=tmp_db, llm_caller=fake_llm_caller, poll_interval_seconds=9999,
                           max_scenarios_per_cycle=2)
    engine2._run_dream_cycle()
    print(f"   dream_log (last 2): {mem.get_dream_log(limit=2)}")

    print("\n[3] Confirming dream-tagged memory is retrievable as [DREAM-PRIMED]...")
    records, exact = mem.retrieve_context("Dream Synthesis", "irrelevant-lookup-key",
                                           tags=["dream_synthesis"])
    print(f"   records found: {len(records)}")

    print("\n[4] I-14 interrupt check — simulating live traffic mid-cycle...")
    engine3 = DreamEngine(db_path=tmp_db, llm_caller=fake_llm_caller, poll_interval_seconds=9999)
    # Fake "new activity" by making interrupted() always report True.
    engine3._activity_fingerprint = lambda: time.time() + 999999  # type: ignore
    engine3._run_dream_cycle()
    last = mem.get_dream_log(limit=1)[0]
    print(f"   status of interrupted cycle: {last['status']}")

    os.unlink(tmp_db)
    print("\n✅ Self-test complete. Temp DB removed.")

# 🦞 ButterClaw v0.9.2 (Mega Release) — The Fleet Layer, Package Architecture & Academic Artifact

**Release Date:** October 5, 2026<br>
**Branch:** `dev` → `main`<br>
**New Files:** `fleet_db_init.py`, `fleet_registry.py`, `trust_graph.py`, `correlation_engine.py`, `collusion_detector.py`, `fleet_memory.py`, `fleet_sentinel.py`, `fleet_api.py`, `hemisphere_scheduler.py`, `tests/fleet/conftest.py`, `tests/arsenal/test_lenient_loader.py`, `docs/RUNBOOK.md`, `scripts/verify_backup.sh`, `whitepaper/src/main.tex`, `whitepaper/ButterClaw_Architecture_Ontology.pdf`, `whitepaper/diagrams/1.png`, `whitepaper/diagrams/2.png`, `whitepaper/LICENSE`, `.zenodo.json`<br>
**Files Changed:** `.gitignore`, `nginx/butterclaw.conf` → `nginx/butterclaw.prod.conf.example`, `nginx/default.conf` → `nginx/butterclaw.local.conf`, `server.py`, `memory_engine.py`, `policy_engine.py`, `dream_engine.py`, `loop_engine.py`, `config.py`, `memory_api.py`, `default_signatures.json`, `setup_wizard.py`, `.env.example`, `Dockerfile`, `docs/ARCHITECTURE.md`, `docs/API.md`, `CHANGELOG.md`, `README.md`

---

## 🚀 Overview

ButterClaw v0.9.2 is a consolidated "Mega Release" that formally bridges the gap from the v0.8.x memory engines into a publish-ready academic repository. 

This release completely overhauls the application structure into a formal PEP 517 `src/` layout, completely eradicating circular dependency crashes, silent database splintering, and module resolution hell. It introduces a massive multi-agent "Fleet Layer" expansion to protect against agents working together. It also deploys a resilient memory maturation watchdog to decouple memory decay from the Dream Engine, and formally locks the architecture in place with a 17-page LaTeX-compiled whitepaper. 

With exactly 77 API routes now active, the architecture is permanently armed for v1.0.0 DOI minting via Zenodo.

---

## 📜 1. The Academic Payload (Whitepaper & Zenodo)
The repository now contains a self-sufficient `whitepaper/` directory, acting as the formal theoretical substrate for the SDK.
*   **The Artifact:** Includes the finalized `main.tex` source code and the mathematically pure 17-page `ButterClaw_Architecture_Ontology.pdf`.
*   **Zero-Slop Vector Graphics:** Integrated high-resolution Mermaid.js flowchart exports directly into the LaTeX pipeline, completely bypassing HTML-injected SVG conversion bloat.
*   **`.zenodo.json` Metadata:** The root-level metadata payload explicitly formatted for the DataCite schema, arming the GitHub-Zenodo webhook for automatic DOI minting upon publication.

---

## 🏗️ 2. The Package Architecture (`src/` Migration)
The entire codebase has been formalized into a globally installable Python package, decoupling source definitions from runtime installation paths.
*   **Global Package Registration (`pyproject.toml`):** ButterClaw is now formally installed via `pip install .`. This registers `butterclaw` in the global Python namespace, eliminating flat-folder execution.
*   **`src/` Layout Migration:** All core application code has been relocated into `src/butterclaw/`. Purged brittle relative imports and alias patterns in favor of strict absolute imports to eradicate resolution crashes.
*   **Universal Configuration Anchor:** `config.py` has been upgraded to act as the single source of truth for all filesystem paths. When running inside the Docker container, all file I/O is firmly anchored to the `/app` and `/data` root directories, eradicating database splintering.

---

## 🌐 3. The Fleet Layer (Multi-Agent Awareness)
Extends ButterClaw's cognition model from evaluating single-agent behavior to a fifth hemisphere reasoning across the entire observed fleet.
*   **Fleet Sentinel (Fifth Hemisphere):** A dedicated LLM hemisphere (temperature `0.5`) that fires reactively on correlation/collusion events and proactively every 4 hours. A `COLLUDING` verdict with confidence ≥ 0.8 escalates cross-agent threats to the Guardian Brain.
*   **Cross-Agent Detection Engines:** 
    *   *Correlation Engine:* Detects spatial and temporal broadcast attacks (same abstracted trajectory observed across `BUTTERCLAW_CORRELATION_FLEET_THRESHOLD` distinct agents).
    *   *Collusion Detector:* Detects divided-labor attacks where N≥3 distinct agents fill complementary semantic roles (e.g., scout + encoder + exfiltrator).
*   **Fleet Database & Trust Graph (`fleet.db`):** Tracks persistent cross-session agent identity, reputation scoring, and a directed weighted relationship graph. Quarantining an agent mathematically propagates a trust score penalty to all upstream agents.
*   **Fleet API Expansion:** 14 new `/api/fleet/*` routes added for graph queries, correlation tracking, and human-gated two-step quarantine workflows.
*   **Hemisphere Scheduler:** A priority queue managing all five LLM hemisphere invocations under a configurable concurrency cap (`BUTTERCLAW_MAX_CONCURRENT_LLM`), complete with a circuit breaker for consecutive LLM errors.

---

## 🧠 4. Maturation Lifecycle Decoupling (Memory Watchdog)
Eliminates a single point of failure in the memory maturation pipeline.
*   **Daemon Watchdog:** A production-grade `_maturation_fallback_loop` thread now monitors the maturation timestamp. If the primary `dream_engine` stalls, crashes, or goes quiet, the watchdog fires independently.
*   **Execution Mutex:** A dedicated `_maturation_tick_lock` prevents double-decay race conditions. The later caller returns `{"status": "skipped"}` immediately rather than queueing behind the first.
*   **Fast Shutdown:** Replaced blocking 6-hour `time.sleep()` loops with `Event.wait(timeout=300)` polling loops. The thread wakes every five minutes to check the stop signal and exits within seconds of SIGTERM.
*   **Configurable via ENV:** All three watchdog parameters (`MEMORY_WATCHDOG_ENABLED`, `MEMORY_MATURATION_FALLBACK_HOURS`, `MEMORY_WATCHDOG_CHECK_INTERVAL_SEC`) are tunable via env vars with no source changes required.

---

## 🔐 5. Infrastructure, Nginx & OPSEC Hardening
The deployment layer has been physically secured and split to balance strict production security with frictionless Developer Experience (DX).
*   **Nginx Dual-Layer Proxies:** 
    *   `butterclaw.prod.conf.example`: The hardened production template. `client_max_body_size` increased to `50m` to accommodate massive AI context windows without 413 errors.
    *   `butterclaw.local.conf`: A formalized local testing bridge for `localhost` developer execution via self-signed certificates without fighting HSTS lockouts.
*   **Cryptographic Forcefield:** Hardened `.gitignore` with a strict `# --- Cryptographic Keys & Certs (CRITICAL) ---` block (`*.key`, `*.pem`, `*.crt`, `nginx/certs/`). This guarantees that local TLS certificates and reverse proxy private keys mathematically cannot be staged or pushed to the public repository.

---

## 📊 Impact Summary

| Category | File | Change | What |
| --- | --- | --- | --- |
| **Architecture** | `pyproject.toml` | New | PEP 517 build system config; defines package dependencies and metadata. |
| **Architecture** | `src/butterclaw/` | Changed | All application `.py` files migrated into a formal package directory. |
| **Architecture** | `config.py` | Changed | Rebuilt `PROJECT_ROOT` as the definitive, dynamic source of truth for all environment and system paths. `_env_float` helper and 3 new `ButterClawConfig` fields added. |
| **Memory Watchdog** | `memory_engine.py` | Changed | `_MemoryCfg` +3 fields, `_maturation_tick_lock`, `_fallback_stop_event`, `_last_maturation_unix_caller`. `run_maturation_tick()` hardened with execution mutex. |
| **Memory Watchdog** | `server.py` | Changed | `start_fallback_ticker()` before `dream_engine.start()`, `atexit.register(stop_fallback_ticker)` for clean shutdown. Fleet layer wiring (13 blocks). |
| **Memory Watchdog** | `memory_api.py` | Changed | `GET /api/memory/status` (13th route) surfaces `last_maturation_unix` and `last_maturation_caller`. |
| **Fleet Layer** | `fleet_db_init.py` | New | 8-table fleet schema, WAL mode, fatal startup, singleton connection. |
| **Fleet Layer** | `fleet_registry.py` | New | Persistent agent registry, 3:1 asymmetric reputation, cross-session identity. |
| **Fleet Layer** | `trust_graph.py` | New | Directed weighted graph, spawn/comm/peer edges, 1-hop taint propagation. |
| **Fleet Layer** | `correlation_engine.py` | New | Spatial + temporal cross-agent detection, journal-backed correlation windows. |
| **Fleet Layer** | `collusion_detector.py` | New | Complementary role detection across 5 semantic roles, sliding window. |
| **Fleet Layer** | `fleet_sentinel.py` | New | Fifth LLM hemisphere (temp 0.5), reactive + proactive, event coalescing. |
| **Fleet Layer** | `fleet_api.py` | New | 14 `/api/fleet/*` routes, two-step quarantine, fleet management surface. |
| **Fleet Layer** | `hemisphere_scheduler.py` | New | Priority queue across 5 hemispheres, circuit breaker, Guardian Brain cap-exempt. |
| **Operations** | `docs/RUNBOOK.md` | New | 252-line ops runbook — quarantine flowchart, dry-run rollout, alert procedures. |
| **Configuration** | `setup_wizard.py` | Changed | `valid_positive_float` validator, sections renumbered to X/10, interactive step 10/10. Section 9/9 Fleet Layer interactive walkthrough. |
| **Configuration** | `.env.example` | Changed | R3 Memory Watchdog section. All 11 fleet env vars with documentation comments. |

**New runtime dependencies:** 0

**New capabilities:** A robust, professionally packaged codebase that can be imported universally. Memory maturation now runs independently of `dream_engine` health, with operators getting structured API visibility into last-tick timing and caller identity. Fleet-scale multi-agent threat detection with a persistent cross-session trust graph, two complementary detection engines (correlation + collusion), and a fifth LLM hemisphere reasoning at fleet scope.

---

## 🗺️ What's Next: v0.9.3

With the memory maturation pipeline now resilient to `dream_engine` disruption, the next patch pass targets the three remaining timed-daemon hemispheres that share the same structural gap as R3 — a blocking `time.sleep()` loop, no stop event, no execution mutex, and no health timestamp.

*   **Dream Weaver (`dream_engine.py`, temp 0.7, idle ≥ 15 min):** `DreamEngine._loop()` uses a blocking sleep and `shutdown()` is currently a no-op `pass`. A concurrent `trigger_now()` from `POST /api/dream/trigger` and the timed loop can enter the cycle body simultaneously, making duplicate LLM calls against the same episodic corpus. R4 adds a stop event, a non-blocking cycle lock, a `notify_dream_cycle()` timestamp function, and a working `shutdown()`. Because dream synthesis requires an LLM, there is no fallback caller — the watchdog is observation and alerting only.
*   **Loop Proposer (`loop_engine.py`, temp 0.4, every 6h):** `LoopEngine._loop()` has the same blocking sleep gap. `run_cycle()` is already publicly callable from `POST /api/loop/trigger` — without a lock, a manual trigger and the timed loop can race and write conflicting experiment records into `memory_engine.record_loop_experiment()`. R5 mirrors R4: stop event, cycle lock on `run_cycle(caller)`, `shutdown()`, and a `GET /api/loop/status` endpoint.
*   **Fleet Sentinel proactive sweep (`fleet_sentinel.py`, temp 0.5, every 4h):** The reactive path (fires on `CorrelationEvent` / `CollusionEvent`) is event-driven and fine as-is. Only the proactive background sweep thread uses a blocking sleep. R6 adds a stop event and a `_last_proactive_unix` timestamp to that thread only. No execution mutex is needed here — the proactive sweep dispatches through `HemisphereScheduler`, which already serialises LLM calls.

**Note — the Auditor hemisphere is out of scope for v0.9.3.** The Auditor fires 30 seconds after a CRITICAL verdict; it is event-driven, not a timed loop, and does not share the blocking-sleep structural gap. Its separate resilience concerns (LLM timeout handling, post-CRITICAL queue overflow) will be addressed in a dedicated pass after the timed-daemon work is complete.

R4 + R5 + R6 complete the consistent resilience model across all timed hemispheres. v0.9.3 also adds R7 — a health visibility and fast-shutdown pass on `HemisphereScheduler` itself, since a dead scheduler thread silently degrades all five non-Guardian-Brain hemispheres simultaneously with no current operator signal.

---

## 🗺️ Extended Roadmap

With five-hemisphere cognition operational and the fleet trust graph accumulating relationship history across sessions and container restarts, the architecture is ready for the next evolution: **federated awareness**.

Upcoming we will explore multi-instance ButterClaw coordination — allowing independently deployed ButterClaw SOCs to share sanitised fleet intelligence without exposing raw telemetry. This includes a signed, privacy-preserving threat indicator exchange protocol, cross-instance trust graph federation, and a shared Arsenal amendment pipeline that lets the Loop Proposer learn from events it did not directly observe.

<p align="center"><br>🧈🦞 <i>Five minds. One fleet. Sealed for v1.0.0. The architecture is locked.</i> 🦞🧈<br><i>The Sentinel sees everything.</i> <br>The DOI awaits.<br></p>

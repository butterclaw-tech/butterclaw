# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

# Changelog: ButterClaw v0.3.1
**Release Date:** April 4, 2026

## [0.3.1] - Reasoning Engine (Self-DoS & Stability Patch)

### Added
* **Self-DoS Prevention:** Introduced a `CONFIDENCE_THRESHOLD` (85%) to the Brain. Low-confidence `CRITICAL` verdicts are now automatically downgraded to `WARNING`, preventing attackers from using weak, ambiguous prompt injections to trick the Sentinel into constantly buttering its own keys.

### Fixed
* **LLM Hallucination Handling:** Added parsing logic to catch and correct confidence formatting hallucinations (e.g., when the LLM outputs `95` instead of `0.95`). Clamped bounds strictly between `0.0` and `1.0`.
* **Execution Hot-Paths:** Moved module imports (`buttervault`, `butterclaw_mcp`) out of the `analyze_threat` execution block and into the top-level scope for boot-time validation, significantly improving threat-response latency.

---

# Changelog: ButterClaw v0.3
**Release Date:** April 4, 2026

## [0.3.0] - The ButterVault & MCP Scaffold

### Added
* **The ButterVault (`buttervault.py`):** Deprecated plaintext `.env` files. API keys are now securely AES-encrypted using the OS-native Credential Locker (`keyring`) and stored as SQLite BLOBs. 
* **Live Ammunition:** Upgraded the Gibson Kill Switch. Triggering the Gibson now physically overwrites local Vault ciphertexts with cryptographic garbage.
* **True MCP Scaffolding:** Restructured `butterclaw_mcp.py` into `ButterClawMCPServer`. It now outputs strict JSON-RPC tool schemas, laying the groundwork for full stdio/SSE Model Context Protocol transport.
* **Hardware Profiles:** Added `Modelfile.example` to the repository, providing a tuned configuration (16k context, 0.3 temp, 0.9 top_p) specifically for running the Sentinel on dedicated local GPUs (e.g., RTX 2060).

### Changed
* **The Brain Upgrade:** Officially pivoted the primary localized reasoning engine from `phi3` to `gemma4:e4b` for superior adaptive semantic reasoning.
* **Massive Context Expansion:** Increased the `watcher.py` log truncation limit from 500 to 4096 characters to ensure deeply embedded, long-form Indirect Prompt Injections are fully captured and passed to the LLM.
* **UI Suite & Routing:** Revamped the VPS Brain Routing dashboard to explicitly support the new `butterclaw-optimized` Modelfile profile and the 6-Node Sentinel architecture.
* **Vibe Sync:** Unified the Tailwind UI color palettes (`butter-400`, `claw-500`) and typography (`Inter`) across the internal dashboard and the public-facing tech demo.

---

# Changelog: ButterClaw v0.2.1
**Release Date:** Late March, 2026

## [0.2.1] - The Mind Reader Update (Observation & Simulation)

### Added
* **Logic Gate Trace:** Introduced the `primary_gate` field to the JSON schema, forcing the Brain to identify the specific analytical vector (Signature, Origin, or Intent) used for the verdict.
* **UI Mind Reader Window:** The dashboard now explicitly displays the triggering logic gate next to the confidence score for 100% transparent observability.

### Changed
* **Terminology Pivot:** Rebranded the system from "Deterministic" to "**Probabilistic**" to accurately reflect the adaptive nature of temperature-based sampling.
* **Documentation Cleanup:** Streamlined the `README.md` to remove "slop" and emphasize the **Evaluation before Execution** principle.

### Fixed
* **Parsing Stability:** Refined the JSON parser in `server.py` to handle the new gate metadata without breaking existing SQLite storage logic.

---

# Changelog: ButterClaw v0.2
**Release Date:** Late March, 2026

## [0.2.0] - The Kinetic Update

### Added
* **The Claws (Execution Layer):** Introduced `butterclaw_mcp.py`, a dedicated Model Context Protocol (MCP) layer for OS-level interventions.
* **Gibson Kill Switch:** Implementation of a "Dry Run" safety harness for simulated `SIGKILL` (`pkill`/`taskkill`) and API key rotation.
* **Structured JSON Intelligence:** Migrated the Brain (Phi-3) to a strict JSON schema output, eliminating brittle regex string-matching errors.
* **Confidence Scoring:** The model now calculates and returns a probabilistic confidence score (0.0 - 1.0) for every threat analysis.
* **Adaptive Temperature:** Bumped LLM temperature to `0.2` to allow for lateral semantic reasoning against obfuscated threats.

### Changed
* **The Brain:** Transitioned from a passive "judge" to an active "Sentinel" capable of triggering programmatic defenses.
* **UI Overhaul:** Updated `index.html` to support real-time metadata streaming and kinetic action logging via Server-Sent Events (SSE).

### Fixed
* **The Box Trap:** Resolved issues where non-deterministic text outputs from the LLM would crash the API parser.

---

## [0.1.1] — Security & Routing Update - 2026-03-23

### Summary

52 patches across 4 files. Zero new dependencies. Full security audit, routing integration, and mobile responsiveness pass.

*(See full v0.1.1 patch notes in historical commit logs)*

---

## [0.1.0] — Initial Prototype Release — 2026-03-17

- Prototype dashboard (`index.html`)
- Flask API server (`server.py`)
- Log watcher daemon (`watcher.py`)
- Cosmetic routing placeholder (`routing.html`)
- Ollama + Phi-3 local inference
- SQLite short-term memory
- SSE log streaming
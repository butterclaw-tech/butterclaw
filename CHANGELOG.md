# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

---

### Patched — v0.3.1 QA Audit for v0.3.2

**Audit Date:** April 5, 2026
**Scope:** Full codebase review of v0.3.1 release — 5 files audited
**Findings:** 13 total — 5 🔴 Bugs, 8 🟡 Issues, 6 🟢 Notes
**Regression Alert:** Bugs B1–B4 are regressions of v0.2.0 audit patches (P6, P7, P13, P3 respectively). Original fixes were overwritten during the v0.3.x development cycle.

---

#### `routing.html` — 5 patches (B1, B2, I1, I2, I5)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B1 | 🔴 Bug | CSP `connect-src` directive had trailing wildcard `*`, nullifying the entire allowlist | Removed wildcard; explicit origins only (REGRESSION of v0.2.0 P6) |
| B2 | 🔴 Bug | Save Config in local mode sent bare `localhost:11434` (no scheme) as the endpoint URL | Changed to `''` (empty string) — local mode uses no remote endpoint (REGRESSION of v0.2.0 P7) |
| I1 | 🟡 Issue | Version footer displays "v0.3.0" | Updated to "v0.3.1" |
| I2 | 🟡 Issue | MCP status badge displays "v0.3 Active" | Updated to "v0.3.1 Active" |
| I5 | 🟡 Issue | Model dropdown first option value is `butterclaw-optimized` but `server.py` default is `butterclaw-optimized:latest` — tag mismatch could cause Ollama to pull/use wrong model | Changed value to `butterclaw-optimized:latest` to match server default |

---

#### `server.py` — 3 patches (B4, I7, I8)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B4 | 🔴 Bug | JSON parse error response leaked full `raw_content` string in API error message — potential data exfiltration vector | Truncated to `raw_content[:200]` in error payload (REGRESSION of v0.2.0 P3) |
| I7 | 🟡 Issue | LLM temperature hardcoded to `0.2` (legacy Phi-3 setting) but `Modelfile.example` specifies `0.3` for Gemma brain — runtime/documentation mismatch | Changed to `0.3`; Modelfile is authoritative for tuned inference parameters |
| I8 | 🟡 Issue | `/api/vault/status` endpoint hardcoded only `openrouter` and `anthropic` as provider keys — any other provider stored in ButterVault would not appear in status response | Replaced with dynamic `buttervault.list_providers()` call; all stored providers now surfaced |

---

#### `butterclaw_mcp.py` — 3 patches (B3, I4, I6)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B3 | 🔴 Bug | `else: pass` branches in action dispatcher silently return `None` for unknown action types — callers receive no error signal | Replaced with `raise NotImplementedError(f"Unknown action: {action}")` (REGRESSION of v0.2.0 P13) |
| I4 | 🟡 Issue | Docstring and dry-run print statements say "v0.3" | Updated to "v0.3.1" |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules — only the first imported module's config takes effect; rest silently ignored | Removed module-level `logging.basicConfig()`; logging config deferred to caller |

---

#### `watcher.py` — 2 patches (I3, I6)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| I3 | 🟡 Issue | Docstring, argparse `--version`, and boot log message all display "v0.3" | Updated all three to "v0.3.1" |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules | Moved `logging.basicConfig()` into `main()` function scope |

---

#### `buttervault.py` — 3 patches (B5, I6, I8)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B5 | 🔴 Bug | Post-destroy diagnostic test used `try/except` to detect destroyed key, but `get_key()` returns `None` on missing keys — never raises an exception; test always reported false success | Changed to explicit `if destroyed_key is None` check |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules | Removed module-level `logging.basicConfig()`; logging config deferred to caller |
| I8 | 🟡 Issue | No API to dynamically enumerate stored providers | Added `list_providers()` helper function returning all provider names from the vault |

---

#### Cross-File Audit Notes — 🟢 Positive

| # | Scope | Finding |
|---|-------|---------|
| N1 | `server.py` | Self-DoS prevention via 85% confidence threshold is well-implemented — low-confidence CRITICAL verdicts correctly downgraded to WARNING |
| N2 | `server.py` | LLM hallucination correction logic (`if raw_conf > 1.0: raw_conf / 100.0`) is correct and handles the known Gemma output format edge case |
| N3 | `buttervault.py` | Fernet + keyring architecture is solid — AES encryption with OS-native credential storage, no plaintext key material at rest |
| N4 | `index.html`, `routing.html` | XSS safety patterns preserved throughout — all dynamic content insertion uses `textContent` and `createElement`, no `innerHTML` with user data |
| N5 | `server.py` | Thread safety via `_state_lock` preserved and correctly applied across all new routes including `/api/vault/status` |
| N6 | `server.py` | CORS whitelist remains explicit with named origins — no wildcard `*` in CORS headers |

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

### Patched — v0.2.0 QA Audit

**Audit Date:** April 2026
**Scope:** Full codebase review of v0.2.0 release — 5 files audited
**Findings:** 20 total — 5 🔴 Bugs, 9 🟡 Issues, 6 🟢 Notes
**Files Patched:** `routing.html`, `server.py`, `watcher.py`, `butterclaw_mcp.py`, `index.html`

---

#### `routing.html` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P6 | 🔴 Bug | CSP `connect-src` directive had trailing wildcard `*`, nullifying the entire allowlist | Removed wildcard; explicit origins only |
| P7 | 🔴 Bug | Save Config in local mode sent bare `localhost:11434` (no scheme) as the endpoint URL | Changed to `''` (empty string) — local mode uses no remote endpoint |

---

#### `server.py` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P3 | 🔴 Bug | JSON parse error response leaked full `raw_content` string in API error message | Truncated to `raw_content[:200]` in error payload |

---

#### `butterclaw_mcp.py` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P13 | 🔴 Bug | `else: pass` branches in action dispatcher silently return `None` for unknown action types | Replaced with `raise NotImplementedError` |

---

#### Additional v0.2.0 Audit Fixes

* **Confidence Clamping:** Bounded confidence score parsing to `[0.0, 1.0]` range with hallucination correction
* **MCP Import Optimization:** Moved `butterclaw_mcp` import from hot-path to top-level scope
* **Version String Alignment:** Unified version identifiers across all files to `v0.2.0`
* **Model Dropdown Sync:** Aligned `routing.html` model dropdown default values with `server.py` expected model tags
* **UI Security Hardening:** Validated XSS-safe DOM patterns across `index.html` dynamic content areas

#### Cross-File Audit Notes — 🟢 Positive

* SSE streaming architecture is well-structured with proper event framing
* Flask CORS configuration uses explicit origin allowlist — no wildcard
* SQLite memory layer handles concurrent writes safely via connection-per-request pattern
* Dry-run safety harness in MCP layer prevents accidental production kills
* Paranoia slider UI provides intuitive real-time sensitivity control
* `textContent`/`createElement` used consistently — no `innerHTML` injection vectors

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

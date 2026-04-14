# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/)

---

# Changelog: ButterClaw v0.5.0

Release Date: April 13, 2026

## [0.5.0] - The Nervous System (Event Ledger + SSE Transport)

### Added

- **MCP Event Ledger (`server.py`):** Persistent, append-only audit log of every MCP tool invocation. New `mcp_events` SQLite table tracks timestamp, JSON-RPC id, method, tool name, arguments, status (pending/success/error/timeout), result (truncated to 4KB), elapsed time in ms, trigger source (auto/manual/critical/handshake/ping), and chain metadata (chain_id, chain_step) for future v0.5.1 tool chaining. Every `send()` call in both `MCPProcessManager` and `MCPSSEClient` writes a `pending` row before dispatch, then updates it with the outcome after response/timeout/error.

- **Event Ledger API Endpoints (`server.py`):**
  - `GET /api/mcp/events` — Query the ledger with optional filters: `?limit=`, `?tool=`, `?status=`, `?since=`. Returns events array, count, and total.
  - `GET /api/mcp/events/<id>` — Fetch a single event with full result payload.

- **Event Ledger UI Panel (`routing.html`):** New "Event Ledger" section below the MCP panel with a cyan/teal gradient header. Features:
  - Filterable by tool name and status via dropdown selectors
  - Each event row shows tool name, status dot (color-coded), elapsed ms, timestamp, and event ID
  - Collapsible result preview — click "Show result" to expand the JSON response inline
  - Arguments displayed as a truncated mono line
  - Trigger source and chain metadata shown for non-auto events
  - Auto-refreshes every 30s alongside MCP status polling
  - Manual refresh button

- **Event Ledger Nav Link (`index.html`):** New sidebar navigation entry "Event Ledger" linking to `routing.html#eventLedgerSection`.

- **Temporal Memory Injection (`server.py`):** Cured "LLM amnesia" by patching `ask_guardian_agent()` to query the new `mcp_events` ledger before evaluating a log. The Brain now receives a sliding window of recent tool executions (temporal context) to detect behavioral drift over time rather than evaluating isolated snapshots.

- **Stateless Self-Reflection / The Auditor (`server.py`):** Added `run_self_audit()`, a non-blocking background daemon thread that fires 30 seconds after any `CRITICAL` verdict. It hits the exact same model with a cold `temperature: 0.0` prompt to review the sanitized event ledger. If it detects a hallucination, it logs a "🧐 Likely False Positive" amber warning to the UI without lowering the system paranoia level (preserving the one-way ratchet).

- **Dynamic Dual-Persona Prompting (`server.py`):** Embedded complex JSON schemas and dual-persona instructions (The Instinct vs. The Auditor) directly into the Flask API request payloads. This guarantees 100% plug-and-play portability for users cloning the repo and running vanilla `gemma4:e4b`, eliminating the strict requirement for a custom compiled `Modelfile`.

- **Transport Abstraction Layer (`mcp_transport.py` — NEW FILE):** Decouples MCP I/O from protocol logic. Two transport implementations behind a common `BaseTransport` interface (`read()`, `write()`, `start()`, `stop()`):
  - `StdioTransport` — Wraps stdin/stdout. Extracts the I/O loop that was previously inline in `butterclaw_mcp.py`'s `main()`.
  - `SSETransport` — Runs a threaded HTTP server using stdlib `http.server` (zero new pip dependencies). `GET /sse` opens a Server-Sent Events stream, `POST /message` receives JSON-RPC requests. Supports optional bearer token authentication. Sends 30s keepalive comments to prevent connection timeout. First SSE event is `event: endpoint` telling the client where to POST (MCP SSE spec compliant).
  - `create_transport()` factory function for CLI flag → transport instance creation.

- **SSE Transport CLI Flags (`butterclaw_mcp.py`):** New argparse flags:
  - `--transport stdio|sse` — Select transport mode (default: stdio)
  - `--bind HOST` — Bind address for SSE (default: 127.0.0.1)
  - `--port PORT` — Port for SSE (default: 5001)
  - `--token SECRET` — Bearer token for SSE auth. Required when binding to 0.0.0.0.
  - Safety: binding to 0.0.0.0 without --token is rejected at startup.

- **MCPSSEClient (`server.py` — NEW CLASS):** Connects to a remote MCP server running SSE transport. Same interface as `MCPProcessManager` (`BaseMCPManager`):
  - `send()` POSTs JSON-RPC to `/message`, waits for correlated response on the SSE stream
  - `_read_sse_stream()` background thread parses SSE events, handles endpoint discovery, message correlation, and automatic reconnection (5s backoff)
  - Health check via `GET /health` on startup
  - Auth via `Authorization: Bearer <token>` header on all requests
  - Ledger integration: every `send()` logs to the event ledger identically to stdio manager

- **BaseMCPManager Interface (`server.py`):** Abstract base class defining the common interface for both `MCPProcessManager` and `MCPSSEClient`. Both implement `send()`, `notify()`, `handshake()`, `status()`, `start()`, `stop()`, `restart()`, `is_alive`, and `transport_name`.

- **MCP Manager Factory (`server.py`):** `create_mcp_manager()` reads `mcp_transport_mode` and `mcp_sse_url` from config to instantiate the correct manager. `mcp_restart` endpoint detects transport mode changes and swaps the manager instance.

- **Transport Selector UI (`routing.html`):** New toggle in the MCP panel — stdio vs SSE buttons with violet highlight. Selecting SSE reveals a config panel with URL input, token input, and "Save SSE Config & Restart MCP" button. Saves to `/api/settings` then triggers `/api/mcp/restart`.

- **MCP Transport Settings (`server.py`):** Three new config fields exposed via `/api/settings`:
  - `mcp_transport` — "stdio" or "sse"
  - `mcp_sse_url` — Remote MCP server URL
  - `mcp_sse_token_set` — Boolean (token existence, never exposes the actual token)

- **OAuth Provider Registry (`oauth_config.py` — NEW FILE):** Skeleton configuration mapping provider names to OAuth endpoints, scopes, and metadata. Four providers registered:
  - Anthropic (Claude) — api_key only (no public OAuth as of April 2026)
  - OpenRouter — api_key only
  - Google Cloud (Gemini) — OAuth 2.0 supported, endpoints configured
  - GitHub — OAuth 2.0 supported, endpoints configured
  - Helper functions: `get_provider()`, `list_providers()`, `list_oauth_capable()`, `list_api_key_only()`, `get_auth_method()`

### Changed

- **`butterclaw_mcp.py` Main Loop:** Refactored from raw `sys.stdin.readline()` / `sys.stdout.write()` to `transport.read()` / `transport.write()`. Protocol handler (`ButterClawMCPServer.route()`) was already transport-agnostic — only the I/O layer changed. Added `KeyboardInterrupt` handler and `finally` block for clean transport shutdown.

- **`server.py` Import Alias:** `import requests` renamed to `import requests as http_requests` to avoid collision with Flask's `request` object now that both are used in the SSE client.

- **`/api/mcp/status` Response:** Now includes `transport_mode` ("stdio" or "sse"), `event_count` (total ledger entries), and `remote_url` (for SSE clients).

- **`/api/mcp/restart` Endpoint:** Detects if the transport mode changed since the current manager was created. If so, stops the old manager and creates a new one via the factory before restarting.

- **`/api/mcp/ping` Endpoint:** Now passes `trigger="ping"` to `send()`, so pings are recorded in the event ledger.

- **`/api/settings` GET Response:** Now includes `mcp_transport`, `mcp_sse_url`, and `mcp_sse_token_set`.

- **Version Strings:** All files updated to `v0.5.0` — `server.py`, `butterclaw_mcp.py`, `routing.html` footer/badges, `index.html` comments.

- **MCP Info Box Text (`routing.html`):** Updated description to mention dual transport and event ledger.

### Architecture Notes

**Transport Abstraction:**
```
ButterClawMCPServer.route(request) → response
        ↑                    ↓
   transport.read()    transport.write()
        ↑                    ↓
   ┌────┴────┐         ┌────┴────┐
   │  stdio  │         │   SSE   │
   │ (local) │         │(network)│
   └─────────┘         └─────────┘
```

**Event Ledger Schema:**
```sql
CREATE TABLE mcp_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,          -- ISO 8601 UTC
    req_id     INTEGER,                -- JSON-RPC id
    method     TEXT NOT NULL,          -- e.g. "tools/call"
    tool_name  TEXT,                   -- e.g. "execute_gibson_kill"
    arguments  TEXT,                   -- JSON string of input args
    status     TEXT NOT NULL,          -- pending | success | error | timeout
    result     TEXT,                   -- JSON string (truncated to 4KB)
    elapsed_ms REAL,                   -- round-trip time
    trigger    TEXT DEFAULT 'auto',    -- auto | manual | critical | handshake | ping
    chain_id   TEXT,                   -- groups steps in a chain (v0.5.1)
    chain_step INTEGER                 -- step number within chain (v0.5.1)
);
```

**Dual Manager Architecture:**
```
server.py
    │
    ├── mcp_manager = create_mcp_manager()
    │       │
    │       ├── MCPProcessManager (stdio)     ← local child process
    │       │       ├── stdin writer
    │       │       ├── stdout reader thread
    │       │       ├── stderr drain thread
    │       │       └── ledger hooks in send()
    │       │
    │       └── MCPSSEClient (sse)            ← remote HTTP
    │               ├── POST /message sender
    │               ├── SSE stream reader thread
    │               ├── auto-reconnect (5s backoff)
    │               └── ledger hooks in send()
    │
    └── Both implement BaseMCPManager interface
```

**New Dependencies:** None. SSE transport uses stdlib `http.server` and `threading`. SSE client uses existing `requests` library.

**New Files:**
- `mcp_transport.py` — Transport abstraction layer (~250 lines)
- `oauth_config.py` — OAuth provider registry skeleton (~100 lines)

---

### 📦 v0.4.1 Complete Delivery Recap

| File | Status | Key Fixes |
|---|---|---|
| **`routing.html`** | ✅ Delivered | R1 🔴 CSP comment removed; R2 🟡 dynamic protocol version; R3 🟡 auto-refresh on armed transition |
| **`server.py`** | ✅ Delivered | S1 🔴 auto-restart chains handshake; S2–S5 🟡 thread safety, TOCTOU, MCP truth-telling, module-level threshold |
| **`butterclaw_mcp.py`** | ✅ Delivered | M1 🟡 error correlation; M2 🟡 arg validation; M3 🟢 basicConfig documented; M4 🟢 pre-init guard |
| **`index.html`** | ✅ Delivered | Clean — version alignment only |
| **`CHANGELOG.md`** | ✅ Delivered | Full v0.4.1 QA audit entry with all 15 findings |

### Patched — v0.4.0 QA Audit for v0.4.1

Audit Date: April 11, 2026
Scope: Full codebase review of v0.4.0 release — 4 files audited
Findings: 15 total — 2 🔴 Bugs, 7 🟡 Issues, 6 🟢 Notes

#### `routing.html` — 3 patches (R1, R2, R3)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| R1 | 🔴 Bug | HTML comment placed **inside** the CSP `content` attribute: `<!-- PATCHED B1: removed wildcard * from connect-src -->`. Browsers parse `<!--` as literal CSP text, not as a comment — likely breaking the `img-src 'self' data:` directive that follows. **Introduced by the v0.3.2 B1 patch itself** (fix was correct, comment placement was not). | Removed the comment from inside the attribute. Audit trail preserved as a normal HTML comment above the `<meta>` tag. |
| R2 | 🟡 Issue | Protocol version `"2024-11-05"` hardcoded in a static `<div>` in the MCP info grid. If `butterclaw_mcp.py` updates its `protocolVersion`, the UI shows stale info. | Changed to dynamic: `mcpProtocolVersion` div populated from `/api/mcp/status` response (`data.protocol_version`). `status()` dict in `server.py` now includes `protocol_version`. |
| R3 | 🟡 Issue | `mcpFetchTools()` runs once at page load and on manual Refresh click — not on a periodic interval. When the server transitions from offline → online, `mcpCheckStatus()` updates the badge, but the tool list stays empty until manual refresh. | Added `_prevMcpArmed` state tracking. `mcpCheckStatus()` now calls `mcpFetchTools()` automatically when state transitions from non-armed → armed. |

#### `server.py` — 5 patches (S1, S2, S3, S4, S5)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| S1 | 🔴 Bug | **`send()` auto-restart skips handshake.** When `send()` detects a dead child, it calls `self.start()` but **not** `self.handshake()`. After auto-restart: `handshake_ok` stays `False`, `discovered_tools` is empty/stale, and the UI shows "Degraded" even though the child is alive. The `restart()` method correctly chains `start()` → `handshake()`, but the auto-restart path inside `send()` does not. | Added `self.handshake()` after `self.start()` in the auto-restart block inside `send()`. Handshake failure is logged but send proceeds (best-effort recovery). |
| S2 | 🟡 Issue | `_req_counter += 1` is not atomic. Two concurrent Flask threads calling `send()` could receive the same `req_id`, causing response correlation collisions in `_pending`. Safe under Flask's default single-threaded `app.run()`, but breaks under any multi-threaded WSGI server (gunicorn with threads, waitress). | Replaced with `itertools.count(1)` — thread-safe in CPython without requiring a lock. |
| S3 | 🟡 Issue | `status()` has a TOCTOU race on `self.process`. Between the truthiness check and `.pid` access, another thread could call `stop()` and set `self.process = None`, raising `AttributeError`. | Snapshot the reference: `proc = self.process` at the top of `status()`, use `proc` throughout. |
| S4 | 🟡 Issue | **CRITICAL verdict path ignores MCP `send()` return values.** In `analyze_threat()`, the CRITICAL block calls `mcp_manager.send("tools/call", ...)` for `execute_gibson_kill` and `rotate_keys` but discards both return values. If the MCP child is dead or calls timeout, `action` still reports `"SIGKILL | Keys Buttered"`. Note: `buttervault.butter_keys()` IS a direct local call, so keys ARE buttered — but gibson_kill success is unverified. Same pattern in `manual_key_rotation()`. | Capture return values. Check for `"error"` key. Append failure details to the action string so the audit log tells the truth: `"Keys Buttered | MCP partial failure: gibson_kill"`. |
| S5 | 🟡 Issue | `CONFIDENCE_THRESHOLD = 85` defined as a local variable inside `analyze_threat()`, but the boot banner hardcodes `85` in a separate print statement. The two references are not linked — changing the threshold in one place leaves the other stale. | Extracted `CONFIDENCE_THRESHOLD` to module-level constant. Both `analyze_threat()` and the boot banner reference it. |

#### `butterclaw_mcp.py` — 4 patches (M1, M2, M3, M4)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| M1 | 🟡 Issue | General exception handler in the main loop sends `"id": None` in the error response even though the parsed `request` dict may be in scope. Parent's stdout reader can't correlate the response → falls through as "Orphaned response" → parent times out instead of getting the error. | Track `last_request` after successful JSON parse. General `except Exception` block now sends `"id": last_request.get("id")`. `JSONDecodeError` block still sends `"id": None` (correct — no valid request exists). |
| M2 | 🟡 Issue | `handle_tools_call` passes `**tool_args` directly to tool functions with no schema validation. If an MCP client sends unexpected arguments, the function raises `TypeError` with an unhelpful Python traceback message instead of a clean schema violation response. | Built `_TOOL_ALLOWED_ARGS` lookup from `inputSchema.properties` at module load. `handle_tools_call` intersects incoming keys against allowed keys, returns a clean `isError: true` content response for unknown args before dispatch. |
| M3 | 🟢 Note | `logging.basicConfig()` is at module level — this was flagged as I6 in v0.3.2 and moved into function scope. However, in v0.4.0 this file runs as a **standalone subprocess** (not imported by server.py), so module-level config is architecturally correct. **Not a regression.** | No code fix needed. Added architectural comment documenting the justification. |
| M4 | 🟢 Note | `initialized` flag is set in `handle_initialize` but never checked — `tools/call` doesn't gate on whether `initialize` was called first. MCP spec says servers SHOULD reject pre-initialization requests. Currently harmless because the parent always handshakes first. | Added `if not self.initialized` guard in `handle_tools_call` returning `-32002` (Server not initialized). Defense-in-depth only. |

#### `index.html` — Clean (version alignment only)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| — | 🟢 Clean | No issues found. CSP is tight, all dynamic content uses `textContent` and `createElement`, MCP badge integration follows existing sidebar patterns. | Version comments updated from v0.4.0 → v0.4.1 for alignment. |

#### Cross-File Audit Notes — 🟢 Positive

| # | Scope | Finding |
|---|-------|---------|
| N1 | `index.html`, `routing.html` | XSS safety maintained — all new MCP panel code uses `textContent` and `createElement` for dynamic content. No `innerHTML` with server data anywhere in the v0.4.0 patch set. |
| N2 | `index.html`, `routing.html` | MCP badge visual states are consistent — both pages use the same three-state model (Armed / Degraded / Offline) with matching color schemes and logic. |
| N3 | `server.py` | ButterVault remains a direct local call — `buttervault.butter_keys()` in the CRITICAL path is a direct function call, not routed through MCP. Key destruction does not depend on the child process being alive. Correct architectural decision. |
| N4 | `server.py` | Reader thread shutdown is clean — `_read_stdout` and `_read_stderr` both exit gracefully on pipe closure. `stop()` properly wakes all waiting threads via `event.set()` before clearing `_pending`. No zombie threads. |
| N5 | `butterclaw_mcp.py` | `notify()` is spec-correct — omits `"id"` from the JSON-RPC payload, producing a valid notification per JSON-RPC 2.0. Handshake sends `notifications/initialized` correctly as a notification, not a request. |
| N6 | `server.py` | stderr drain solved — the v0.3.2-era problem of stderr filling and deadlocking the child is fully resolved. `_read_stderr` runs as a daemon thread, continuously draining and logging child stderr. |

---

# Changelog: ButterClaw v0.4.0

Release Date: April 9, 2026

## [0.4.0] - The Claws Awaken (MCP Transport & Observability)

### Added

- **Full MCP Protocol Compliance (`butterclaw_mcp.py`):** The execution layer now speaks real Model Context Protocol over stdio. `initialize` returns `protocolVersion` (`2024-11-05`), `serverInfo`, and proper `capabilities` shape. Added `tools/list`, `ping`, and `notifications/initialized` handlers. Tool results now return MCP-standard content arrays (`{content: [{type: "text", text: "..."}], isError: bool}`).

- **Threaded MCP Process Manager (`server.py`):** Replaced the inline blocking `stdout.readline()` with a dedicated `MCPProcessManager` class. Stdout and stderr each get their own daemon reader thread — Flask never blocks on MCP I/O, and the child process never deadlocks from a full stderr pipe.

- **Response Correlation by ID:** MCP requests are tracked via a `_pending` dictionary keyed by JSON-RPC `id`. The stdout reader thread wakes the correct waiting sender via `threading.Event`, eliminating response ordering assumptions.

- **Configurable Timeouts:** Every `MCPProcessManager.send()` call accepts a `timeout` parameter (default 10s). Stalled MCP children no longer hang the server indefinitely.

- **Auto-Restart:** If `send()` detects a dead child process, it automatically respawns and re-runs the handshake before retrying. The `/api/mcp/restart` endpoint provides manual lifecycle control.

- **3-Step MCP Handshake (`server.py`):**
  1. `initialize` → receive `protocolVersion` + `serverInfo` + `capabilities`
  2. `notifications/initialized` → tell the child the client is ready
  3. `tools/list` → dynamically discover all registered tools with `inputSchema`

- **4 New API Endpoints (`server.py`):**
  - `/api/mcp/status` — Returns process health: `alive`, `handshake_ok`, `pid`, `tools_count`, `pending_requests`
  - `/api/mcp/ping` — Sends MCP `ping` to the child, returns round-trip ms and `pong` boolean
  - `/api/mcp/tools` — Returns the full tool list discovered during handshake
  - `/api/mcp/restart` — Stops, restarts the child, and re-runs the handshake

- **Expanded Tool Registry (`butterclaw_mcp.py`):** 5 tools (up from 2):
  - `execute_gibson_kill` — Kinetic: terminates a rogue process by name (DRY_RUN)
  - `rotate_keys` — Kinetic: invalidates provider API tokens globally (DRY_RUN)
  - `system_status` — Returns ButterClaw health metrics (version, platform, PID, DRY_RUN state)
  - `scan_port` — Quick TCP connect check (e.g., is Ollama alive at 11434?)
  - `log_event` — Writes structured audit entries to the MCP stderr log stream

- **MCP Sidebar Badge (`index.html`):** New status indicator in the sidebar bottom showing MCP state (Armed / Degraded / Offline) with tool count. Polls `/api/mcp/status` every 30s. Clickable → navigates to `routing.html#mcpSection`.

- **Live MCP Panel (`routing.html`):** Replaced the disabled v0.3.1 MCP placeholder with a fully wired panel:
  - Process status card with live dot + PID display
  - Ping button → hits `/api/mcp/ping`, shows round-trip latency in ms
  - Restart button → POSTs `/api/mcp/restart`, refreshes status + tool list on success
  - Dynamic tool list rendered from `/api/mcp/tools` with name, description, and `inputSchema` parameter details
  - Transport info (stdio / JSON-RPC 2.0) and protocol version display
  - Refresh button for manual tool re-discovery

### Changed

- **Dispatch Table Architecture (`butterclaw_mcp.py`):** Replaced the `if/elif` method routing chain with a `METHOD_MAP` dict mapping method names to handler functions, and a `TOOL_DISPATCH` dict mapping tool names to callables. Adding new methods or tools is now a one-line addition.

- **Tool Schema Field Name:** Tool definitions now use `inputSchema` (MCP standard) instead of `parameters`.

- **Tool Function Return Values:** `execute_gibson_kill` and `rotate_keys` now return descriptive strings instead of raw `True` booleans, making content array results meaningful.

- **JSON-RPC Error Codes:** Proper codes throughout — `-32700` (parse error), `-32601` (method not found), `-32602` (invalid params / unknown tool), `-32603` (internal error). Previously everything was `-32603`.

- **MCP Commands in Analyze Path (`server.py`):** CRITICAL verdict responses now push `execute_gibson_kill` and `rotate_keys` through the `MCPProcessManager` (non-blocking, correlated) instead of the old inline `send_mcp_command()`.

- **Version Strings:** All files updated from `v0.3.1` / `v0.3.2` to `v0.4.0` — `server.py`, `butterclaw_mcp.py`, `routing.html` footer, MCP badge.

### Fixed

- **Flask Thread Blocking:** The single biggest fragility source — `mcp_process.stdout.readline()` running inline on the Flask request thread — is eliminated. All MCP reads now happen on dedicated daemon threads.

- **Child Deadlock Risk:** `stderr` was never captured (`Popen` had no `stderr=PIPE`). If the MCP child logged enough to fill the OS pipe buffer (~64KB), it would deadlock silently. Now drained continuously by a dedicated thread.

- **Orphaned Response Handling:** If a response arrives for an already-timed-out or unknown request ID, it's logged with a warning instead of silently dropped or misattributed.

- **Handshake Failure Visibility:** A failed MCP handshake previously froze startup silently. Now it fails cleanly, logs the error, and sets `handshake_ok = False` so all observability endpoints report degraded status truthfully.

- **Redundant Import:** Removed duplicate `import sys` at the bottom of `butterclaw_mcp.py`.

### Architecture Notes

**Transport Model:**
```
[Flask Server (server.py)]
        │
        ├── MCPProcessManager
        │       ├── stdin writer (serialized via _write_lock)
        │       ├── stdout reader thread (correlates by id → threading.Event)
        │       └── stderr drain thread (prints with [MCP LOG] prefix)
        │
        └── subprocess.Popen (butterclaw_mcp.py)
                ├── stdin  ← JSON-RPC requests (one per line)
                ├── stdout → JSON-RPC responses (one per line)
                └── stderr → logging/diagnostics (never JSON)
```

**Observability Stack:**
- Sidebar badge (both pages) polls `/api/mcp/status` every 30s
- Routing page MCP panel provides manual ping, restart, and tool inspection
- Server console shows `📥 [MCP ACK]` for every correlated response and `🔧 [MCP LOG]` for every stderr line from the child
- Three visual states: **Armed** (green — alive + handshake OK), **Degraded** (amber — alive but handshake failed), **Offline** (red — process not running)

**DRY_RUN remains `True`** — all kinetic tools (gibson_kill, rotate_keys) are still simulated. The transport is production-ready; the actions are not yet live.

---

### Patched — v0.3.1 QA Audit for v0.3.2

Audit Date: April 5, 2026
Scope: Full codebase review of v0.3.1 release — 5 files audited
Findings: 13 total — 5 🔴 Bugs, 8 🟡 Issues, 6 🟢 Notes
Regression Alert: Bugs B1–B4 are regressions of v0.2.0 audit patches (P6, P7, P13, P3 respectively). Original fixes were overwritten during the v0.3.x development cycle.

#### `routing.html` — 5 patches (B1, B2, I1, I2, I5)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B1 | 🔴 Bug | CSP `connect-src` directive had trailing wildcard `*`, nullifying the entire allowlist | Removed wildcard; explicit origins only (REGRESSION of v0.2.0 P6) |
| B2 | 🔴 Bug | Save Config in local mode sent bare `localhost:11434` (no scheme) as the endpoint URL | Changed to `''` (empty string) — local mode uses no remote endpoint (REGRESSION of v0.2.0 P7) |
| I1 | 🟡 Issue | Version footer displays "v0.3.0" | Updated to "v0.3.1" |
| I2 | 🟡 Issue | MCP status badge displays "v0.3 Active" | Updated to "v0.3.1 Active" |
| I5 | 🟡 Issue | Model dropdown first option value is `butterclaw-optimized` but `server.py` default is `butterclaw-optimized:latest` — tag mismatch could cause Ollama to pull/use wrong model | Changed value to `butterclaw-optimized:latest` to match server default |

#### `server.py` — 3 patches (B4, I7, I8)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B4 | 🔴 Bug | JSON parse error response leaked full `raw_content` string in API error message — potential data exfiltration vector | Truncated to `raw_content[:200]` in error payload (REGRESSION of v0.2.0 P3) |
| I7 | 🟡 Issue | LLM temperature hardcoded to `0.2` (legacy Phi-3 setting) but `Modelfile.example` specifies `0.3` for Gemma brain — runtime/documentation mismatch | Changed to `0.3`; Modelfile is authoritative for tuned inference parameters |
| I8 | 🟡 Issue | `/api/vault/status` endpoint hardcoded only `openrouter` and `anthropic` as provider keys — any other provider stored in ButterVault would not appear in status response | Replaced with dynamic `buttervault.list_providers()` call; all stored providers now surfaced |

#### `butterclaw_mcp.py` — 3 patches (B3, I4, I6)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B3 | 🔴 Bug | `else: pass` branches in action dispatcher silently return `None` for unknown action types — callers receive no error signal | Replaced with `raise NotImplementedError(f"Unknown action: {action}")` (REGRESSION of v0.2.0 P13) |
| I4 | 🟡 Issue | Docstring and dry-run print statements say "v0.3" | Updated to "v0.3.1" |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules — only the first imported module's config takes effect; rest silently ignored | Removed module-level `logging.basicConfig()`; logging config deferred to caller |

#### `watcher.py` — 2 patches (I3, I6)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| I3 | 🟡 Issue | Docstring, argparse `--version`, and boot log message all display "v0.3" | Updated all three to "v0.3.1" |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules | Moved `logging.basicConfig()` into `main()` function scope |

#### `buttervault.py` — 3 patches (B5, I6, I8)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| B5 | 🔴 Bug | Post-destroy diagnostic test used `try/except` to detect destroyed key, but `get_key()` returns `None` on missing keys — never raises an exception; test always reported false success | Changed to explicit `if destroyed_key is None` check |
| I6 | 🟡 Issue | Module-level `logging.basicConfig()` collides with other modules | Removed module-level `logging.basicConfig()`; logging config deferred to caller |
| I8 | 🟡 Issue | No API to dynamically enumerate stored providers | Added `list_providers()` helper function returning all provider names from the vault |

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

Release Date: April 4, 2026

## [0.3.1] - Reasoning Engine (Self-DoS & Stability Patch)

### Added

- **Self-DoS Prevention:** Introduced a `CONFIDENCE_THRESHOLD` (85%) to the Brain. Low-confidence `CRITICAL` verdicts are now automatically downgraded to `WARNING`, preventing attackers from using weak, ambiguous prompt injections to trick the Sentinel into constantly buttering its own keys.

### Fixed

- **LLM Hallucination Handling:** Added parsing logic to catch and correct confidence formatting hallucinations (e.g., when the LLM outputs `95` instead of `0.95`). Clamped bounds strictly between `0.0` and `1.0`.
- **Execution Hot-Paths:** Moved module imports (`buttervault`, `butterclaw_mcp`) out of the `analyze_threat` execution block and into the top-level scope for boot-time validation, significantly improving threat-response latency.

---

# Changelog: ButterClaw v0.3

Release Date: April 4, 2026

## [0.3.0] - The ButterVault & MCP Scaffold

### Added

- **The ButterVault (`buttervault.py`):** Deprecated plaintext `.env` files. API keys are now securely AES-encrypted using the OS-native Credential Locker (`keyring`) and stored as SQLite BLOBs.
- **Live Ammunition:** Upgraded the Gibson Kill Switch. Triggering the Gibson now physically overwrites local Vault ciphertexts with cryptographic garbage.
- **True MCP Scaffolding:** Restructured `butterclaw_mcp.py` into `ButterClawMCPServer`. It now outputs strict JSON-RPC tool schemas, laying the groundwork for full stdio/SSE Model Context Protocol transport.
- **Hardware Profiles:** Added `Modelfile.example` to the repository, providing a tuned configuration (16k context, 0.3 temp, 0.9 top_p) specifically for running the Sentinel on dedicated local GPUs (e.g., RTX 2060).

### Changed

- **The Brain Upgrade:** Officially pivoted the primary localized reasoning engine from `phi3` to `gemma4:e4b` for superior adaptive semantic reasoning.
- **Massive Context Expansion:** Increased the `watcher.py` log truncation limit from 500 to 4096 characters to ensure deeply embedded, long-form Indirect Prompt Injections are fully captured and passed to the LLM.
- **UI Suite & Routing:** Revamped the VPS Brain Routing dashboard to explicitly support the new `butterclaw-optimized` Modelfile profile and the 6-Node Sentinel architecture.
- **Vibe Sync:** Unified the Tailwind UI color palettes (`butter-400`, `claw-500`) and typography (`Inter`) across the internal dashboard and the public-facing tech demo.

---

# Changelog: ButterClaw v0.2.1

Release Date: Late March, 2026

## [0.2.1] - The Mind Reader Update (Observation & Simulation)

### Added

- **Logic Gate Trace:** Introduced the `primary_gate` field to the JSON schema, forcing the Brain to identify the specific analytical vector (Signature, Origin, or Intent) used for the verdict.
- **UI Mind Reader Window:** The dashboard now explicitly displays the triggering logic gate next to the confidence score for 100% transparent observability.

### Changed

- **Terminology Pivot:** Rebranded the system from "Deterministic" to "Probabilistic" to accurately reflect the adaptive nature of temperature-based sampling.
- **Documentation Cleanup:** Streamlined the `README.md` to remove "slop" and emphasize the `Evaluation before Execution` principle.

### Fixed

- **Parsing Stability:** Refined the JSON parser in `server.py` to handle the new gate metadata without breaking existing SQLite storage logic.

---

# Changelog: ButterClaw v0.2

Release Date: Late March, 2026

## [0.2.0] - The Kinetic Update

### Added

- **The Claws (Execution Layer):** Introduced `butterclaw_mcp.py`, a dedicated Model Context Protocol (MCP) layer for OS-level interventions.
- **Gibson Kill Switch:** Implementation of a "Dry Run" safety harness for simulated `SIGKILL` (`pkill` / `taskkill`) and API key rotation.
- **Structured JSON Intelligence:** Migrated the Brain (Phi-3) to a strict JSON schema output, eliminating brittle regex string-matching errors.
- **Confidence Scoring:** The model now calculates and returns a probabilistic confidence score (0.0 - 1.0) for every threat analysis.
- **Adaptive Temperature:** Bumped LLM temperature to `0.2` to allow for lateral semantic reasoning against obfuscated threats.

### Changed

- **The Brain:** Transitioned from a passive "judge" to an active "Sentinel" capable of triggering programmatic defenses.
- **UI Overhaul:** Updated `index.html` to support real-time metadata streaming and kinetic action logging via Server-Sent Events (SSE).

### Fixed

- **The Box Trap:** Resolved issues where non-deterministic text outputs from the LLM would crash the API parser.

### Patched — v0.2.0 QA Audit

Audit Date: April 2026
Scope: Full codebase review of v0.2.0 release — 5 files audited
Findings: 20 total — 5 🔴 Bugs, 9 🟡 Issues, 6 🟢 Notes
Files Patched: `routing.html`, `server.py`, `watcher.py`, `butterclaw_mcp.py`, `index.html`

#### `routing.html` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P6 | 🔴 Bug | CSP `connect-src` directive had trailing wildcard `*`, nullifying the entire allowlist | Removed wildcard; explicit origins only |
| P7 | 🔴 Bug | Save Config in local mode sent bare `localhost:11434` (no scheme) as the endpoint URL | Changed to `''` (empty string) — local mode uses no remote endpoint |

#### `server.py` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P3 | 🔴 Bug | JSON parse error response leaked full `raw_content` string in API error message | Truncated to `raw_content[:200]` in error payload |

#### `butterclaw_mcp.py` — Key patches

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| P13 | 🔴 Bug | `else: pass` branches in action dispatcher silently return `None` for unknown action types | Replaced with `raise NotImplementedError` |

#### Additional v0.2.0 Audit Fixes

- **Confidence Clamping:** Bounded confidence score parsing to `[0.0, 1.0]` range with hallucination correction
- **MCP Import Optimization:** Moved `butterclaw_mcp` import from hot-path to top-level scope
- **Version String Alignment:** Unified version identifiers across all files to `v0.2.0`
- **Model Dropdown Sync:** Aligned `routing.html` model dropdown default values with `server.py` expected model tags
- **UI Security Hardening:** Validated XSS-safe DOM patterns across `index.html` dynamic content areas

#### Cross-File Audit Notes — 🟢 Positive

- SSE streaming architecture is well-structured with proper event framing
- Flask CORS configuration uses explicit origin allowlist — no wildcard
- SQLite memory layer handles concurrent writes safely via connection-per-request pattern
- Dry-run safety harness in MCP layer prevents accidental production kills
- Paranoia slider UI provides intuitive real-time sensitivity control
- `textContent` / `createElement` used consistently — no `innerHTML` injection vectors

---

## [0.1.1] — Security & Routing Update - 2026-03-23

### Summary

52 patches across 4 files. Zero new dependencies. Full security audit, routing integration, and mobile responsiveness pass.

(See full v0.1.1 patch notes in historical commit logs)

---

## [0.1.0] — Initial Prototype Release — 2026-03-17

- Prototype dashboard (`index.html`)
- Flask API server (`server.py`)
- Log watcher daemon (`watcher.py`)
- Cosmetic routing placeholder (`routing.html`)
- Ollama + Phi-3 local inference
- SQLite short-term memory
- SSE log streaming

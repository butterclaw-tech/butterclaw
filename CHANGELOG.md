# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/)

---

## [0.5.2] - ButterVault OAuth (Credential Lifecycle Management) - 2026-04-18

### Added
- **OAuth Token Storage (`buttervault.py`):** The ButterVault now encrypts and stores structured OAuth token payloads (access token, refresh token, expiry timestamp, token type, scope) as JSON blobs using the same Fernet + OS keyring encryption pipeline trusted for static API keys. New functions: `store_oauth_token()`, `get_oauth_token()`, `delete_oauth_token()`, `list_oauth_providers()`.
- **New SQLite Table (`buttervault.py`):** `oauth_tokens` table with `provider`, `ciphertext`, `created_at`, and `last_refresh` columns. Separate from the `vault` table — same encryption, clean schema separation.
- **Automatic Token Refresh (`buttervault.py`):** `refresh_token_if_needed()` checks token expiry with a 60-second safety buffer, silently refreshes via the provider's token endpoint using the stored refresh token, re-encrypts the new tokens, and updates the Vault. Handles rotating refresh tokens (updates if provider issues a new one). Returns the refreshed token dict or `None` on failure.
- **OAuth Authorization Flow (`server.py`):** Full OAuth 2.0 authorization code flow with four new endpoints:
  - `GET /api/vault/oauth/start/<provider>` — Generates a CSRF-protected authorization URL using `secrets.token_urlsafe(32)`. Client credentials (`client_id`, `client_secret`) are read from the ButterVault, never hardcoded. Google-specific parameters (`access_type=offline`, `prompt=consent`) ensure refresh token acquisition.
  - `GET /api/vault/oauth/callback` — Validates CSRF state (single-use, 10-minute TTL), exchanges the authorization code for tokens via POST to the provider's token endpoint, assembles a structured token dict with computed `expires_at`, and seals it in the ButterVault. Logs a successful connection to the oopsie log (emerald/🔑).
  - `GET /api/vault/oauth/status` — Returns connection status for all OAuth-capable providers: `connected`, `has_refresh_token`, `expires_at`, `expired`, and `has_client_credentials` flags.
  - `POST /api/vault/oauth/revoke/<provider>` — Best-effort remote token revocation at the provider's `revoke_url`, then unconditional local deletion from the Vault regardless of remote result.
- **CSRF State Management (`server.py`):** Thread-safe in-memory state store (`_oauth_states`) with `threading.Lock`, 10-minute TTL, and automatic cleanup of expired tokens on every new flow initiation.
- **OAuth Result Page (`server.py`):** `_oauth_result_page()` helper returns a self-closing HTML popup with success/error styling, `postMessage` to the opener window for cross-window communication, and 2-second auto-close.
- **Vault Diagnostic Mode (`buttervault.py`):** Extended the `if __name__ == "__main__"` test suite with OAuth token store/retrieve and Gibson destruction verification for OAuth payloads.

### Changed
- **Gibson Kill Switch (`buttervault.py`):** `butter_keys()` now destroys **both** the `vault` table (static API keys) AND the `oauth_tokens` table (OAuth payloads) in a single atomic operation. Both global and provider-scoped destruction hit both tables. The Sovereign Seal holds — OAuth tokens are mathematically annihilated alongside static keys.
- **Client Credential Architecture (`server.py`):** OAuth client credentials (`client_id`, `client_secret`) are stored in the ButterVault via the existing `/api/vault/key` endpoint using provider-namespaced keys (e.g., `google_client_id`, `google_client_secret`). The OAuth start endpoint reads them from the Vault at flow initiation time. If the Vault is Buttered, the OAuth flow cannot start — correct behavior.
- **New Imports (`server.py`):** Added `import secrets` (CSRF token generation), `from urllib.parse import quote` (URL encoding without `requests.utils` dependency), and `import oauth_config` (provider registry access).
- **Version Strings:** All files updated to `v0.5.2`.

### Fixed
- **Orphaned Ledger Entry (`server.py`):** Fixed a bug in `ChainExecutor.execute()` where the exception handler called `ledger_log_start()` but never called `ledger_log_end()`, leaving a permanent `pending` row in the `mcp_events` table for any chain step that threw an exception. Now captures the `event_id` and closes the entry as `status="error"` with the exception message.

### Architecture Notes

**OAuth Token Lifecycle:**
```
User clicks "Connect" → Frontend calls /api/vault/oauth/start/google
                         → Server reads client_id from Vault
                         → Server generates CSRF state token
                         → Server returns authorization URL
                         → Frontend opens popup to Google
                         → User authorizes
                         → Google redirects to /api/vault/oauth/callback
                         → Server validates CSRF state
                         → Server exchanges code for tokens
                         → Server seals tokens in ButterVault
                         → Popup closes, signals parent via postMessage
```

**Token Refresh Flow:**
```
Any tool needs OAuth token → refresh_token_if_needed(provider, ...)
                            → Decrypt token from Vault
                            → Check: time.time() < (expires_at - 60)?
                            → Yes: return token (still valid)
                            → No: POST refresh_token to provider
                            → Re-encrypt new tokens in Vault
                            → Return refreshed token
```

**Gibson Destruction Scope (v0.5.2):**
```
butter_keys()
├── UPDATE vault SET ciphertext = garbage        ← Static API keys
└── UPDATE oauth_tokens SET ciphertext = garbage ← OAuth payloads
```

**OAuth-Capable Providers (from oauth_config.py):**

| Provider | Auth Method | OAuth Status |
|---|---|---|
| Anthropic (Claude) | API key only | ❌ No public OAuth |
| OpenRouter | API key only | ❌ No public OAuth |
| Google Cloud (Gemini) | OAuth 2.0 | ✅ Endpoints configured |
| GitHub | OAuth 2.0 | ✅ Endpoints configured |

**New Dependencies:** None. Token exchange uses existing `requests` library. CSRF uses stdlib `secrets`.

**New Files:** None. `oauth_config.py` was created in v0.5.0 — unchanged in v0.5.2 (static registry, no behavioral code added).

**New SQLite Tables:** 1 (`oauth_tokens`)

**New API Endpoints:** 4 (`/start`, `/callback`, `/status`, `/revoke`)

---

## [0.5.1] - Tool Chaining (Multi-Step Execution) - 2026-04-16

### Added
- **ChainExecutor (`server.py`):** New engine allowing the Brain to compose and execute sequential, multi-step MCP tool chains for custom threat response strategies.
- **Condition Evaluator (`server.py`):** Added conditional logic between chain steps using a safe, whitelist-based operator dictionary (`contains`, `not_contains`, `equals`, `not_equals`, `starts_with`). Explicitly avoids arbitrary code execution/`eval()`. Operator logic is case-insensitive and stripped of whitespace.
- **Event Ledger Chain Grouping (`routing.html`):** The ledger UI now visually groups related chain events together by their `chain_id`. Chain blocks feature a consolidated header with a step count, aggregated status icons, and individual step-number badges for each tool execution.
- **Oopsie Card Chain Links (`index.html`):** CRITICAL alerts triggered by a multi-step chain now dynamically render a violet "Multi-Step Chain" badge in the UI action field, alongside a "View in Ledger →" link to trace the execution path.
- **Dynamic Brain Prompting (`server.py`):** The LLM system prompt now dynamically builds the available MCP `tools_context` from the handshake and includes the optional `"chain"` array JSON schema instructions.
- **Safety Rails (`server.py`):** Enforced a hard limit of `MAX_STEPS = 10` and a cumulative total `TIMEOUT = 60` seconds for all chain executions to prevent infinite reasoning loops or stalling.

### Changed
- **CRITICAL Path Routing (`server.py`):** The `analyze_threat` function now intercepts the `"chain"` field from the Brain's output and routes to `ChainExecutor`. If no chain is present, it safely falls back to the legacy hardcoded tool sequence (backward compatible).
- **Vault Integrity Guarantee (`server.py`):** Ensured `buttervault.butter_keys()` is ALWAYS executed locally during a CRITICAL verdict, independently of whether the Brain included `rotate_keys` in its MCP chain contents.
- **Event Ledger Integration (`server.py`):** Tool calls invoked via the `ChainExecutor` now actively populate the `chain_id` and `chain_step` columns in the `mcp_events` SQLite table, linking step sequences together.
- **Step Enumeration (`server.py`):** Improved LLM token efficiency by removing the requirement for the Brain to output specific step numbers, instead deriving `chain_step` dynamically using Python's `enumerate()`.
- **UI State & Copy (`routing.html`, `index.html`):** Version footers bumped to v0.5.1, the MCP Info Box updated to document conditional chaining, and the `ledgerStatusColors` dictionary expanded to support the new `skipped` (violet) step status.

### Fixed
- **Tools List Iteration (`server.py`):** Fixed an `AttributeError` crash during prompt generation by correctly iterating over the `mcp_manager.discovered_tools` list instead of calling `.items()` on it.

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
- **Stateless Self-Reflection / The Auditor (`server.py`):** `run_self_audit()` background daemon fires 30 seconds after any CRITICAL verdict. Uses the same Gemma 4 model at `temperature: 0.0` to review the sanitized event ledger and flag potential false positives without giving the AI authority to lower its own shields.
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
  transport.read()     transport.write()
          ↑                    ↓
  ┌────┴────┐          ┌────┴────┐
  │  stdio  │          │   SSE   │
  │ (local) │          │(network)│
  └─────────┘          └─────────┘
```

**Event Ledger Schema:**
```sql
CREATE TABLE mcp_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,         -- ISO 8601 UTC
    req_id      INTEGER,               -- JSON-RPC id
    method      TEXT NOT NULL,         -- e.g. "tools/call"
    tool_name   TEXT,                  -- e.g. "execute_gibson_kill"
    arguments   TEXT,                  -- JSON string of input args
    status      TEXT NOT NULL,         -- pending | success | error | timeout
    result      TEXT,                  -- JSON string (truncated to 4KB)
    elapsed_ms  REAL,                  -- round-trip time
    trigger     TEXT DEFAULT 'auto',   -- auto | manual | critical | handshake | ping
    chain_id    TEXT,                  -- groups steps in a chain (v0.5.1)
    chain_step  INTEGER               -- step number within chain (v0.5.1)
);
```

**Dual Manager Architecture:**
```
server.py
│
├── mcp_manager = create_mcp_manager()
│   │
│   ├── MCPProcessManager (stdio) ← local child process
│   │   ├── stdin writer
│   │   ├── stdout reader thread
│   │   ├── stderr drain thread
│   │   └── ledger hooks in send()
│   │
│   └── MCPSSEClient (sse) ← remote HTTP
│       ├── POST /message sender
│       ├── SSE stream reader thread
│       ├── auto-reconnect (5s backoff)
│       └── ledger hooks in send()
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
| R1 | 🔴 Bug | HTML comment placed **inside** the CSP `content` attribute. Browsers parse `<!--` as literal CSP text, not as a comment — likely breaking the `img-src 'self' data:` directive that follows. **Introduced by the v0.3.2 B1 patch itself.** | Removed the comment from inside the attribute. Audit trail preserved as a normal HTML comment above the `<meta>` tag. |
| R2 | 🟡 Issue | Protocol version `"2024-11-05"` hardcoded in a static `<div>` in the MCP info grid. If `butterclaw_mcp.py` updates its `protocolVersion`, the UI shows stale info. | Changed to dynamic: `mcpProtocolVersion` div populated from `/api/mcp/status` response. |
| R3 | 🟡 Issue | `mcpFetchTools()` runs once at page load and on manual Refresh click — not on a periodic interval. When the server transitions from offline → online, the tool list stays empty until manual refresh. | Added `_prevMcpArmed` state tracking. `mcpCheckStatus()` now calls `mcpFetchTools()` automatically when state transitions from non-armed → armed. |

#### `server.py` — 5 patches (S1, S2, S3, S4, S5)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| S1 | 🔴 Bug | **`send()` auto-restart skips handshake.** When `send()` detects a dead child, it calls `self.start()` but **not** `self.handshake()`. After auto-restart: `handshake_ok` stays `False`, `discovered_tools` is empty/stale. | Added `self.handshake()` after `self.start()` in the auto-restart block inside `send()`. |
| S2 | 🟡 Issue | `_req_counter += 1` is not atomic. Two concurrent Flask threads calling `send()` could receive the same `req_id`. | Replaced with `itertools.count(1)` — thread-safe in CPython without requiring a lock. |
| S3 | 🟡 Issue | `status()` has a TOCTOU race on `self.process`. Between the truthiness check and `.pid` access, another thread could call `stop()` and set `self.process = None`. | Snapshot the reference: `proc = self.process` at the top of `status()`, use `proc` throughout. |
| S4 | 🟡 Issue | **CRITICAL verdict path ignores MCP `send()` return values.** If the MCP child is dead or calls timeout, `action` still reports `"SIGKILL \| Keys Buttered"`. | Capture return values. Check for `"error"` key. Append failure details to the action string. |
| S5 | 🟡 Issue | `CONFIDENCE_THRESHOLD = 85` defined as a local variable inside `analyze_threat()`, but the boot banner hardcodes `85` separately. | Extracted `CONFIDENCE_THRESHOLD` to module-level constant. Both references linked. |

#### `butterclaw_mcp.py` — 4 patches (M1, M2, M3, M4)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| M1 | 🟡 Issue | General exception handler sends `"id": None` in error response even though the parsed request dict may be in scope. Parent can't correlate → falls through as "Orphaned response" → parent times out. | Track `last_request` after successful JSON parse. General `except Exception` block now sends `"id": last_request.get("id")`. |
| M2 | 🟡 Issue | `handle_tools_call` passes `**tool_args` directly to tool functions with no schema validation. | Built `_TOOL_ALLOWED_ARGS` lookup from `inputSchema.properties` at module load. Intersects incoming keys against allowed keys. |
| M3 | 🟢 Note | `logging.basicConfig()` is at module level — flagged previously but architecturally correct since this file runs as a standalone subprocess. | Added architectural comment documenting the justification. |
| M4 | 🟢 Note | `initialized` flag is set in `handle_initialize` but never checked — `tools/call` doesn't gate on whether `initialize` was called first. | Added `if not self.initialized` guard in `handle_tools_call` returning `-32002` (Server not initialized). |

#### `index.html` — Clean (version alignment only)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| — | 🟢 Clean | No issues found. CSP is tight, all dynamic content uses `textContent` and `createElement`. | Version comments updated from v0.4.0 → v0.4.1 for alignment. |

#### Cross-File Audit Notes — 🟢 Positive

| # | Scope | Finding |
|---|-------|---------|
| N1 | `index.html`, `routing.html` | XSS safety maintained — all new MCP panel code uses `textContent` and `createElement`. No `innerHTML` with server data. |
| N2 | `index.html`, `routing.html` | MCP badge visual states are consistent — both pages use the same three-state model (Armed / Degraded / Offline). |
| N3 | `server.py` | ButterVault remains a direct local call — `buttervault.butter_keys()` in the CRITICAL path is not routed through MCP. |
| N4 | `server.py` | Reader thread shutdown is clean — `stop()` properly wakes all waiting threads via `event.set()` before clearing `_pending`. No zombie threads. |
| N5 | `butterclaw_mcp.py` | `notify()` is spec-correct — omits `"id"` from the JSON-RPC payload, producing a valid notification per JSON-RPC 2.0. |
| N6 | `server.py` | stderr drain solved — `_read_stderr` runs as a daemon thread, continuously draining and logging child stderr. |

---

# Changelog: ButterClaw v0.4.0
Release Date: April 9, 2026

## [0.4.0] - The Claws Awaken (MCP Transport & Observability)

### Added
- **Full MCP Protocol Compliance (`butterclaw_mcp.py`):** The execution layer now speaks real Model Context Protocol over stdio. `initialize` returns `protocolVersion` (`2024-11-05`), `serverInfo`, and proper `capabilities` shape. Added `tools/list`, `ping`, and `notifications/initialized` handlers. Tool results now return MCP-standard content arrays (`{content: [{type: "text", text: "..."}], isError: bool}`).
- **Threaded MCP Process Manager (`server.py`):** Replaced the inline blocking `stdout.readline()` with a dedicated `MCPProcessManager` class. Stdout and stderr each get their own daemon reader thread — Flask never blocks on MCP I/O, and the child process never deadlocks from a full stderr pipe.
- **Response Correlation by ID:** MCP requests are tracked via a `_pending` dictionary keyed by JSON-RPC `id`. The stdout reader thread wakes the correct waiting sender via `threading.Event`.
- **Configurable Timeouts:** Every `MCPProcessManager.send()` call accepts a `timeout` parameter (default 10s).
- **Auto-Restart:** If `send()` detects a dead child process, it automatically respawns and re-runs the handshake before retrying.
- **3-Step MCP Handshake (`server.py`):** initialize → notifications/initialized → tools/list.
- **4 New API Endpoints (`server.py`):** `/api/mcp/status`, `/api/mcp/ping`, `/api/mcp/tools`, `/api/mcp/restart`.
- **Expanded Tool Registry (`butterclaw_mcp.py`):** 5 tools (up from 2): `execute_gibson_kill`, `rotate_keys`, `system_status`, `scan_port`, `log_event`.
- **MCP Sidebar Badge (`index.html`):** New status indicator showing MCP state (Armed / Degraded / Offline).
- **Live MCP Panel (`routing.html`):** Process status, ping, restart, and dynamic tool list with `inputSchema` inspection.

### Changed
- **Dispatch Table Architecture (`butterclaw_mcp.py`):** Replaced `if/elif` routing with `METHOD_MAP` and `TOOL_DISPATCH` dicts.
- **Tool Schema Field Name:** Now uses `inputSchema` (MCP standard) instead of `parameters`.
- **JSON-RPC Error Codes:** Proper codes throughout — `-32700`, `-32601`, `-32602`, `-32603`.
- **MCP Commands in Analyze Path (`server.py`):** CRITICAL responses now push through `MCPProcessManager` (non-blocking, correlated).
- **Version Strings:** All files updated to `v0.4.0`.

### Fixed
- **Flask Thread Blocking:** Eliminated inline `stdout.readline()` on Flask request threads.
- **Child Deadlock Risk:** stderr now drained continuously by dedicated thread.
- **Orphaned Response Handling:** Unknown response IDs logged with warning instead of silently dropped.
- **Handshake Failure Visibility:** Failed handshake now sets `handshake_ok = False` for truthful status reporting.

---

### Patched — v0.3.1 QA Audit for v0.3.2

Audit Date: April 5, 2026
Scope: Full codebase review of v0.3.1 release — 5 files audited
Findings: 13 total — 5 🔴 Bugs, 8 🟡 Issues, 6 🟢 Notes

*(See v0.3.2 patch notes in CHANGELOG v0.4.0 section above for full audit details.)*

---

# Changelog: ButterClaw v0.3.1
Release Date: April 4, 2026

## [0.3.1] - Reasoning Engine (Self-DoS & Stability Patch)

### Added
- **Self-DoS Prevention:** `CONFIDENCE_THRESHOLD` (85%) prevents weak CRITICAL verdicts from triggering the Gibson.

### Fixed
- **LLM Hallucination Handling:** Confidence formatting correction and clamping to [0.0, 1.0].
- **Execution Hot-Paths:** Module imports moved to top-level scope.

---

# Changelog: ButterClaw v0.3
Release Date: April 4, 2026

## [0.3.0] - The ButterVault & MCP Scaffold

### Added
- **The ButterVault (`buttervault.py`):** AES-encrypted API key storage via OS-native `keyring`.
- **Live Ammunition:** Gibson Kill Switch physically overwrites Vault ciphertexts.
- **True MCP Scaffolding:** `ButterClawMCPServer` with JSON-RPC tool schemas.
- **Hardware Profiles:** `Modelfile.example` for tuned local GPU inference.

### Changed
- **Brain Upgrade:** Pivoted from `phi3` to `gemma4:e4b`.
- **Context Expansion:** Watcher log truncation limit increased from 500 to 4096 characters.

---

## [0.2.1] — The Mind Reader Update - 2026-03-xx

### Added
- **Logic Gate Trace:** `primary_gate` field forcing the Brain to identify the analytical vector.
- **UI Mind Reader Window:** Displays triggering logic gate next to confidence score.

### Changed
- **Terminology Pivot:** "Deterministic" → "Probabilistic".

---

## [0.2.0] — The Kinetic Update - 2026-03-xx

### Added
- **The Claws (`butterclaw_mcp.py`):** MCP execution layer for OS-level interventions.
- **Gibson Kill Switch:** Dry Run safety harness for simulated SIGKILL and key rotation.
- **Structured JSON Intelligence:** Strict JSON schema output.
- **Confidence Scoring:** Probabilistic confidence score (0.0 - 1.0).

### Changed
- **The Brain:** Transitioned from passive "judge" to active "Sentinel".

### Fixed
- **The Box Trap:** Non-deterministic text outputs no longer crash the parser.

---

## [0.1.1] — Security & Routing Update - 2026-03-23

52 patches across 4 files. Zero new dependencies.

---

## [0.1.0] — Initial Prototype Release — 2026-03-17

- Prototype dashboard (`index.html`)
- Flask API server (`server.py`)
- Log watcher daemon (`watcher.py`)
- Ollama + Phi-3 local inference
- SQLite short-term memory
- SSE log streaming

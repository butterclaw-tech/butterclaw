# 🦞 ButterClaw v0.5.0 — The Nervous System (Event Ledger + SSE Transport)

**Release Date:** April 14, 2026
**Branch:** `dev` → `main`
**New Files:** `mcp_transport.py`, `oauth_config.py`
**Files Changed:** `server.py`, `butterclaw_mcp.py`, `routing.html`, `index.html`, `CHANGELOG.md`, `README.md`

---

## Overview

Two major pillars, a memory upgrade to the core engine, plus infrastructure groundwork. The MCP execution layer now has a persistent memory (Event Ledger) and a network-accessible transport option (SSE). Furthermore, the core reasoning engine has been upgraded with Temporal Memory and a Stateless Self-Reflection loop, turning ButterClaw from a single-machine sentinel into a highly resilient, self-auditing distributed security platform. Zero new pip dependencies.

---

## 📋 Pillar 1: Event Ledger (Persistent Audit Log)

**Problem solved:** MCP tool invocations were previously only `print()` statements to the server console. If the terminal scrolled or the process restarted, the audit trail was gone. The oopsie logs table stores threat analysis results, not tool execution records. There was no persistent record of what The Claws actually did.

**What's new:**

- New `mcp_events` SQLite table with 12 columns: timestamp, JSON-RPC id, method, tool name, arguments, status (pending/success/error/timeout), result (truncated to 4KB), elapsed ms, trigger source, chain_id, chain_step
- Every `send()` call writes a `pending` row before dispatch, updates it with the outcome after response/timeout/error
- Works identically in both `MCPProcessManager` (stdio) and `MCPSSEClient` (SSE)
- Two new API endpoints:
  - `GET /api/mcp/events?limit=50&tool=rotate_keys&status=error&since=2026-04-12T00:00:00Z`
  - `GET /api/mcp/events/42` — full event detail with result payload
- New UI panel on the routing page with:
  - Filter dropdowns (tool name, status)
  - Color-coded status dots per event row
  - Elapsed time and timestamp display
  - Collapsible result preview (click to expand JSON)
  - Trigger source and chain metadata display
  - Auto-refresh every 30s + manual refresh button
- New "Event Ledger" nav link in `index.html` sidebar

**Trigger sources recorded:**

| Trigger | When |
|---|---|
| `auto` | Default for tool calls during normal operation |
| `critical` | CRITICAL verdict path (gibson_kill, rotate_keys) |
| `manual` | Manual key rotation via panic button |
| `handshake` | initialize and tools/list during MCP handshake |
| `ping` | MCP ping from the UI or API |
| `chain` | Reserved for v0.5.1 tool chaining |

---

## 📡 Pillar 2: SSE Transport (Dual-Mode MCP)

**Problem solved:** The MCP server only spoke stdio — it was a child process of `server.py` on the same machine. If you wanted a remote client (another machine, a cloud IDE, a different agent) to talk to The Claws, there was no network transport.

**What's new:**

### `mcp_transport.py` (New File)

Transport abstraction layer with a common `BaseTransport` interface:

- `StdioTransport` — Wraps stdin/stdout. Extracts the I/O loop that was previously inline in `butterclaw_mcp.py`
- `SSETransport` — Threaded HTTP server using stdlib `http.server`:
  - `GET /sse` → Opens SSE stream. First event is `event: endpoint` telling client where to POST
  - `POST /message` → Receives JSON-RPC requests, returns 202 Accepted
  - `GET /health` → Transport health check
  - 30s keepalive comments to prevent connection timeout
  - Optional bearer token authentication
  - Threaded — each SSE client gets its own daemon thread
- `create_transport()` factory for CLI → transport instance

### `butterclaw_mcp.py` Changes

- Main loop refactored from raw `sys.stdin` / `sys.stdout` to `transport.read()` / `transport.write()`
- Protocol handler (`ButterClawMCPServer.route()`) was already transport-agnostic — only I/O changed
- New CLI flags:

```bash
python butterclaw_mcp.py                                         # stdio (default)
python butterclaw_mcp.py --transport sse                          # SSE on 127.0.0.1:5001
python butterclaw_mcp.py --transport sse --port 6001              # custom port
python butterclaw_mcp.py --transport sse --bind 0.0.0.0 --token x # remote with auth
```

- Safety: `--bind 0.0.0.0` without `--token` is rejected at startup

### `MCPSSEClient` (New Class in `server.py`)

- Connects to a remote MCP server running SSE transport
- Same interface as `MCPProcessManager` (`BaseMCPManager`)
- `send()` POSTs JSON-RPC to `/message`, waits for correlated response on SSE stream
- Background thread reads SSE stream with automatic reconnection (5s backoff)
- Health check via `GET /health` on startup
- Auth via `Authorization: Bearer <token>` on all requests
- Ledger hooks identical to stdio manager

### `BaseMCPManager` Interface

Abstract base class in `server.py`. Both managers implement: `send()`, `notify()`, `handshake()`, `status()`, `start()`, `stop()`, `restart()`, `is_alive`, `transport_name`.

### Factory + Hot-Swap

- `create_mcp_manager()` reads config to instantiate correct manager
- `/api/mcp/restart` detects transport mode changes and swaps the manager instance
- `/api/settings` now accepts `mcp_transport`, `mcp_sse_url`, `mcp_sse_token`

### UI Controls

- Transport selector toggle (stdio / SSE) in routing page MCP panel
- SSE config panel (URL input, token input, save & restart button)
- Transport mode displayed in MCP status card PID line

---

## 🧠 Temporal Memory & Stateless Self-Reflection Core Engine Upgrade

**Problem solved:** The reasoning engine suffered from "LLM amnesia," evaluating every log as an isolated snapshot. Furthermore, giving the AI the authority to autonomously lower the paranoia level exposed the system to a "Rasta Mode" prompt injection vulnerability, but without it, the system risked "Red Alert exhaustion" from false positives. 

**What's new:**

- **Temporal Memory Injection:** `ask_guardian_agent()` now queries the `mcp_events` ledger *before* evaluating a log. The Brain is fed a sliding window of its recent tool executions, allowing it to track behavioral drift over time.
- **Stateless Self-Reflection (The Auditor):** A new `run_self_audit()` background daemon thread fires 30 seconds after any `CRITICAL` verdict.
- **Split-Timeline Single-Model Loop:** The daemon hits the exact same `gemma4:e4b` model, but swaps the persona to a cold `temperature: 0.0` auditor. It evaluates the sanitized event ledger to double-check the primary Instinct's math.
- **Safe False Positive Flagging:** If the Auditor detects a hallucination, it logs a `🧐 [Likely False Positive]` amber warning to the UI, allowing the human to reset the system without ever giving the AI the physical authority to drop the shields.
- **Dynamic Dual-Persona Prompting:** System prompts and JSON schemas are dynamically injected via `server.py`, ensuring the repository remains 100% plug-and-play for vanilla model weights without strictly requiring a custom `Modelfile`.

---

## 🔐 OAuth Provider Registry (Infrastructure)

### `oauth_config.py` (New File)

Skeleton registry for v0.5.2 OAuth integration:

| Provider | Auth Method | OAuth Ready |
|---|---|---|
| Anthropic (Claude) | API key | ❌ No public OAuth |
| OpenRouter | API key | ❌ No public OAuth |
| Google Cloud (Gemini) | OAuth 2.0 | ✅ Endpoints configured |
| GitHub | OAuth 2.0 | ✅ Endpoints configured |

Helper functions: `get_provider()`, `list_providers()`, `list_oauth_capable()`, `list_api_key_only()`, `get_auth_method()`

---

## 📊 Impact Summary

| File | Lines Changed (approx) | What |
|---|---|---|
| `server.py` | +550 | Event Ledger, MCPSSEClient, Auditor daemon, Memory Injection, new endpoints |
| `butterclaw_mcp.py` | +60, -30 | Transport abstraction, CLI args, clean shutdown |
| `mcp_transport.py` | +250 (new) | StdioTransport, SSETransport, factory |
| `oauth_config.py` | +100 (new) | Provider registry skeleton |
| `routing.html` | +300 | Event Ledger panel, transport selector, SSE config |
| `index.html` | +10 | Event Ledger nav link, version alignment |

**New pip dependencies:** None
**New files:** 2 (`mcp_transport.py`, `oauth_config.py`)
**New SQLite tables:** 1 (`mcp_events`)
**New API endpoints:** 2 (`/api/mcp/events`, `/api/mcp/events/<id>`)

---

## 🧪 Smoke Test

### Event Ledger

1. `python server.py` — watch for `📋 [LEDGER] Event ledger initialized. 0 historical events.`
2. Open routing page → scroll to Event Ledger section → should show "No events recorded yet"
3. Click **Simulate Attack** on the main dashboard
4. Return to Event Ledger → should show `execute_gibson_kill` and `rotate_keys` events with `trigger: critical`
5. Click **Ping MCP** → ledger shows a `ping` event with elapsed ms
6. Use filter dropdowns → filter by `rotate_keys` tool, or `error` status
7. Click "Show result" on any event → JSON response expands inline

### SSE Transport

1. Start MCP in SSE mode: `python butterclaw_mcp.py --transport sse --port 5001`
2. Start server: `python server.py`
3. In routing page → switch transport to SSE → enter `http://127.0.0.1:5001` → Save & Restart
4. MCP badge should transition to Armed (green)
5. Ping MCP → should show pong with round-trip ms
6. Simulate attack → CRITICAL path should work through SSE transport
7. Event Ledger → events should show with the SSE manager logging identically

### Remote SSE (Optional)

1. On remote machine: `python butterclaw_mcp.py --transport sse --bind 0.0.0.0 --port 5001 --token mysecret`
2. On local machine: configure SSE URL to `http://<remote-ip>:5001` with token `mysecret`
3. Save & Restart → should connect and handshake via network

### Stateless Self-Reflection (The Auditor)

1. Ensure the Event Ledger has some recent baseline activity.
2. Click **Simulate Attack** to trigger a `CRITICAL` Red Alert.
3. Wait exactly 30 seconds without refreshing the page.
4. Watch the UI: A new Amber card should slide down automatically (via SSE) reading `🧐 [Likely False Positive] Auditor Review: ...` indicating the background daemon successfully audited the ledger.

---

## ✅ All v0.4.1 QA Patches Preserved

| Patch | Status |
|---|---|
| R1 — CSP comment removed | ✅ Preserved |
| S1 — Auto-restart chains handshake | ✅ Preserved (stdio manager) |
| S2 — Thread-safe counter | ✅ Preserved (both managers) |
| S3 — TOCTOU snapshot in status() | ✅ Preserved (stdio manager) |
| S4 — CRITICAL path truth-telling | ✅ Preserved + now logged to ledger |
| S5 — Module-level threshold | ✅ Preserved |
| M1 — Error response correlation | ✅ Preserved |
| M2 — Argument validation | ✅ Preserved |
| M4 — Pre-initialization guard | ✅ Preserved |

---

## 🗺️ What's Next

**v0.5.1 — Tool Chaining** ✅
- Brain composes multi-tool sequences with conditional execution
- `ChainExecutor` class with stored intermediate results
- Condition evaluator: whitelist of safe string comparisons (contains, equals, not_contains)
- Chain visualization in oopsie cards and event ledger
- Safety: max 10 steps, 60s total timeout, no eval()

**v0.5.2 — ButterVault OAuth**
- `store_oauth_token()` / `refresh_token_if_needed()` in buttervault.py
- `/api/vault/oauth/start` and `/api/vault/oauth/callback` endpoints
- Vault modal OAuth flow for Google Cloud (first live provider)
- Token destruction on panic button

---

**DRY_RUN remains `True`.** The transport is production-ready. The ledger is recording. The Claws are composing. 🦞

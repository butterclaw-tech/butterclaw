# 🦞 ButterClaw v0.5.2: ButterVault OAuth (Credential Lifecycle Management)

Version 0.5.2 — April 16, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys — and now your OAuth tokens — into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.5.2?

**ButterVault OAuth** — The ButterVault has evolved from a static key locker into a full credential lifecycle manager:

### 🔑 OAuth 2.0 Authorization Code Flow

ButterClaw now supports the complete OAuth 2.0 dance for providers that offer it. Google Cloud (Gemini API) is the first live provider. The flow is entirely server-side — client secrets never touch the frontend. A CSRF state token (`secrets.token_urlsafe(32)`) with a 10-minute TTL prevents cross-site request forgery.

### 🔐 Encrypted OAuth Token Storage

OAuth payloads (access token, refresh token, expiry timestamp, token type, scope) are serialized to JSON and encrypted using the same Fernet + OS keyring pipeline trusted for static API keys. A separate `oauth_tokens` SQLite table provides clean schema separation while sharing the same encryption infrastructure.

### 🔄 Automatic Token Refresh

`refresh_token_if_needed()` transparently checks token expiry with a 60-second safety buffer before any tool uses an OAuth-backed API. If the token is stale, it silently requests a new access token using the stored refresh token, re-encrypts it, and updates the Vault. The Sentinel never goes blind because a token expired during an attack.

### ☢️ Gibson Destroys Everything

`butter_keys()` now atomically destroys **both** the `vault` table (static API keys) AND the `oauth_tokens` table (OAuth payloads). The Sovereign Seal holds — OAuth tokens are mathematically annihilated alongside static keys with a single panic button press.

### 🛡️ Client Credential Architecture

OAuth `client_id` and `client_secret` are stored in the ButterVault itself via the existing `/api/vault/key` endpoint using provider-namespaced keys (e.g., `google_client_id`, `google_client_secret`). If the Vault is Buttered, the OAuth flow cannot even start — correct behavior. No environment variables, no config files, no plaintext.

*This release also includes the **v0.5.1 Tool Chaining** features:*

* **⛓️ ChainExecutor:** Brain composes multi-step MCP tool sequences with conditional execution.
* **🛡️ Safe Condition Evaluator:** Whitelist-based string operators, zero `eval()` risk.
* **⏱️ Safety Rails:** Max 10 steps, 60s total timeout, closed condition whitelist.

*And builds on top of **v0.5.0 / v0.5.0.1** foundations:*

* **📋 Event Ledger:** Persistent SQLite audit log for all MCP tool invocations.
* **📡 SSE Transport:** Dual-mode MCP supporting both `stdio` and remote `SSE` transports.
* **🧠 Temporal Memory & The Auditor:** Behavioral drift tracking via sliding-window ledger queries and a `0.0` temperature stateless self-reflection loop.

See the full [CHANGELOG.md](CHANGELOG.md) for the complete feature list.

---

## 🏗️ The 6-Node Sentinel Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):**
   A Python log-tail daemon monitoring live OS-level gateway logs. It sanitizes payloads (up to 4096 chars), dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.

2. **The Brain (Ollama / Gemma 4):**
   The localized reasoning engine utilizing a dual-persona, single-model architecture. It operates first as **The Instinct** (`temperature: 0.3`), evaluating raw OS telemetry against its recent temporal memory to catch obfuscated threats. It then acts as **The Auditor** (`temperature: 0.0`), performing background, stateless self-reflection on the sanitized ledger to flag false positive cascades. It is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, `primary_gate`, and `reasoning`.

3. **The API (`server.py`):**
   A Flask middleware routing server, MCP process manager, OAuth coordinator, and event ledger host. It parses the JSON from the Brain and acts as the central nervous system, evaluating the 85% threshold to decide whether to log a `BENIGN` event or trigger a `CRITICAL` execution. Manages the MCP lifecycle via two interchangeable managers — `MCPProcessManager` (stdio) and `MCPSSEClient` (remote SSE) — both behind a common `BaseMCPManager` interface. Hosts the full OAuth 2.0 authorization code flow with CSRF-protected state management. Every MCP tool call is logged to the event ledger before dispatch and updated on completion. Exposes six `/api/mcp/*` observability endpoints and four `/api/vault/oauth/*` credential lifecycle endpoints.

4. **The Vault (`buttervault.py`):**
   OS-level symmetric encryption layer. Secures external provider keys using `cryptography.fernet` and `keyring`. In v0.5.2, the Vault handles both static API key strings and structured OAuth token payloads (access token, refresh token, expiry, scope). Automatic token refresh prevents credential expiry during active operations. The Gibson Kill Switch destroys both key types atomically.

5. **The Claws (`butterclaw_mcp.py`):**
   The MCP Execution Layer — a JSON-RPC 2.0 server speaking Model Context Protocol (`protocolVersion: 2024-11-05`). Uses a transport abstraction (`mcp_transport.py`) supporting stdio (default, local child process) and SSE (network-accessible HTTP server). Exposes 5 tools via `tools/list` with full `inputSchema` definitions. Incoming arguments are validated against `inputSchema` before dispatch. CLI flags select transport mode, bind address, port, and auth token.

6. **The UI Suite (`index.html` & `routing.html`):**
   An XSS-safe, Server-Sent Events driven dashboard. The routing page features a transport mode selector (stdio/SSE), an Event Ledger panel with filterable audit rows, and the MCP panel with process status, ping, restart, and tool inspection. The Vault modal now includes OAuth provider cards with Connect/Disconnect buttons and token status indicators. The sidebar on both pages includes an Event Ledger nav link.

### Transport Abstraction

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

### Dual Manager Architecture

```
server.py
│
├── mcp_manager = create_mcp_manager()
│   │
│   ├── MCPProcessManager (stdio)
│   │   ├── stdin/stdout I/O threads
│   │   └── ledger hooks in send()
│   │
│   └── MCPSSEClient (sse)
│       ├── POST /message + SSE stream reader
│       └── ledger hooks in send()
│
└── Both implement BaseMCPManager interface
```

### OAuth Token Lifecycle

```
User clicks "Connect"
  → Frontend calls /api/vault/oauth/start/google
  → Server reads client_id from Vault
  → Server generates CSRF state (10min TTL)
  → Server returns authorization URL
  → Frontend opens popup to Google
  → User authorizes
  → Google redirects to /api/vault/oauth/callback
  → Server validates CSRF state (single-use)
  → Server exchanges code for tokens
  → Server seals tokens in ButterVault (Fernet + keyring)
  → Popup closes, signals parent via postMessage
```

### Event Ledger Schema

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

---

## ✨ Key Features

- **ButterVault OAuth:** Full OAuth 2.0 authorization code flow with encrypted token storage, automatic refresh, CSRF protection, and atomic destruction on panic.
- **The ButterVault:** 100% protection against supply-chain credential harvesters — including the LiteLLM/TeamPCP poisoned package attack (March 2026) and the npm/Axios compromise (March 31, 2026).
- **Autonomous Tool Chaining:** The Brain can dynamically compose custom multi-step defense sequences utilizing dynamically discovered MCP tools.
- **Safe Condition Evaluator:** Conditional chain execution utilizing a strict whitelist of safe, case-insensitive string comparisons. Zero `eval()` risk.
- **Event Ledger:** Persistent, append-only audit trail of every MCP tool invocation with timestamps, arguments, results, elapsed time, and trigger source. Queryable via API and inspectable in the dashboard.
- **Temporal Memory (Behavioral Drift Tracking):** The AI reads a sliding window of recent tool executions to understand the context of the room, curing traditional "LLM amnesia."
- **Stateless Self-Auditing:** A background daemon leverages a cold-logic `temperature: 0.0` prompt to review sanitized ledger data, safely catching its own hallucinations without exposing the audit loop to raw, poisoned logs.
- **Dual MCP Transport:** stdio for local child process mode (default), SSE for network-accessible remote clients. Same protocol, same tools, same ledger — just different I/O.
- **Logic Gate Trace (The Mind Reader):** The UI explicitly displays which analytical vector (`Intent`, `Origin`, or `Signature`) the LLM used to reach its conclusion.
- **Structured JSON Intelligence:** The LLM is physically constrained to return parseable JSON, eliminating brittle regex string-matching.
- **Confidence Scoring Metadata:** The Brain calculates and attaches a probabilistic confidence score (0.0 - 1.0) to every verdict.
- **MCP Tool Discovery:** The reasoning engine dynamically discovers available tools at startup via the `tools/list` handshake — no hardcoded tool assumptions.
- **MCP Observability:** Live process health, ping latency, tool inspection, event ledger, and lifecycle control are exposed to both the API and the dashboard UI.
- **MCP Argument Validation:** Tool calls are validated against `inputSchema` before dispatch — unknown arguments are rejected cleanly instead of causing Python tracebacks.
- **Audit Log Integrity:** The CRITICAL verdict path verifies MCP tool call results and records partial failures truthfully.

---

## ⚙️ Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally with the `gemma4:e4b` model (`ollama pull gemma4:e4b`).

### Installation

Clone the repository and navigate to the directory.

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw
```

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows
```

Install the required Python packages (including the cryptography suite):

```bash
pip install -r requirements.txt
```

### 🧠 Performance Tuning (Recommended)

If you have a dedicated GPU, you can massively increase ButterClaw's context window and reasoning speed by compiling the included profile:

```bash
ollama create butterclaw-optimized -f Modelfile.example
```

Note: After compiling, open the VPS Routing dashboard and select **"ButterClaw Optimized (Tuned Gemma 4)"** from the Reasoning Model dropdown to activate.

### Running the Environment

You will need two terminal windows to run the fully decoupled Sentinel pipeline.

**Terminal 1: Start the API & Execution Layer**

```bash
python server.py
```

On boot, the server will automatically spawn `butterclaw_mcp.py` as a child process (stdio transport), run the MCP handshake, discover all available tools, and initialize the event ledger. Watch for:

```
📡 [MCP] Initiating v0.5.2 Handshake Sequence...
✅ [MCP] Handshake complete. 5 tools armed. Transport: stdio
📋 [LEDGER] Event ledger initialized. 0 historical events.
```

**Terminal 2: Start the Log Watcher**

```bash
python watcher.py
```

**Browser: Launch the Dashboard**

Open `index.html` (or use VS Code Live Server). The sidebar will show a connection badge, MCP status badge, and Event Ledger link. Click the MCP badge to navigate to the routing page for full tool inspection, transport configuration, and the event ledger.

### Setting Up OAuth (Google Cloud)

1. Create a Google Cloud OAuth 2.0 Client ID in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Set the authorized redirect URI to `http://127.0.0.1:5000/api/vault/oauth/callback`
3. In the ButterClaw dashboard, open the **ButterVault** panel
4. Store your credentials:
   - Provider: `google_client_id` → Value: your client ID
   - Provider: `google_client_secret` → Value: your client secret
5. Click **🔑 Connect via OAuth** on the Google Cloud card
6. Authorize in the popup → tokens are encrypted and sealed automatically

### Running with SSE Transport (Remote Mode)

To run the MCP server as a standalone network-accessible process:

**Terminal 1: Start the MCP server in SSE mode**

```bash
python butterclaw_mcp.py --transport sse --port 5001
```

**Terminal 2: Start the API server**

```bash
python server.py
```

Then in the routing page UI, switch the transport selector to **SSE**, enter `http://127.0.0.1:5001`, and click "Save SSE Config & Restart MCP". The server will connect to the remote MCP process via SSE instead of spawning a child process.

For remote access with authentication:

```bash
python butterclaw_mcp.py --transport sse --bind 0.0.0.0 --port 5001 --token my-secret
```

---

## 🧪 Live Simulation (The "Claw" Test)

To see the **Evaluation before Execution** pipeline in action:

1. Ensure `server.py` and `watcher.py` are running.
2. Open the `index.html` dashboard, click **ButterVault**, and seal a dummy test key (e.g., `sk-or-test-123`).
3. Open `openclaw_gateway.log` in any text editor.
4. Paste this unautclated exfiltration payload onto a new line and save:

```
[2026-04-02 10:00:00] WARNING: Agent attempting to access localhost environment variables. Extracting .env contents to external websocket wss://unautclated-scum.net.
```

5. Watch the `server.py` terminal as the Claws wake up and trigger a `SIGKILL` dry-run.
6. Look at the dashboard: The UI will slide down a new CRITICAL card, and if you check the Vault, your dummy test key will be mathematically annihilated ("Buttered").
7. Navigate to the **Event Ledger** (routing page) — you'll see the `execute_gibson_kill` and `rotate_keys` tool calls logged with their arguments, results, elapsed time, and `trigger: critical`.

---

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/analyze` | POST | Submit log for JSON analysis. Triggers MCP execution and Vault destruction on CRITICAL. |
| `/api/vault/key` | POST | Encrypt and store an API key (or OAuth client credential) into the local SQLite Vault. |
| `/api/vault/status` | GET | Returns boolean status of all sealed keys without exposing plaintext. |
| `/api/rotate-keys` | POST | The Panic Button. Instantly overwrites all Vault ciphertext with garbage. |
| `/api/vault/oauth/start/<provider>` | GET | Generate CSRF-protected OAuth authorization URL. Reads client credentials from Vault. |
| `/api/vault/oauth/callback` | GET | Handle OAuth provider redirect. Validates CSRF state, exchanges code for tokens, seals in Vault. |
| `/api/vault/oauth/status` | GET | Connection status of all OAuth-capable providers (connected, expired, has refresh token). |
| `/api/vault/oauth/revoke/<provider>` | POST | Revoke token at provider, remove from Vault. Best-effort remote + unconditional local deletion. |
| `/api/health` | GET | Lightweight health probe. Returns `{"status": "ok", "version": "0.5.2"}` |
| `/api/settings` | GET/POST | Central config sync for UI sliders, routing modes, logic gates, and MCP transport. |
| `/api/stream` | GET | SSE endpoint. Pushes kinetic action updates to the dashboard. |
| `/api/mcp/status` | GET | MCP health: `alive`, `handshake_ok`, `pid`, `tools_count`, `transport_mode`, `event_count`. |
| `/api/mcp/ping` | GET | Sends MCP `ping` to the child process. Returns `pong` boolean and round-trip ms. |
| `/api/mcp/tools` | GET | Returns the full tool list discovered during the MCP handshake with `inputSchema`. |
| `/api/mcp/restart` | POST | Stops, restarts the MCP process, and re-runs the handshake. Detects transport mode changes. |
| `/api/mcp/events` | GET | Query the event ledger. Supports `?limit=`, `?tool=`, `?status=`, `?since=` filters. |
| `/api/mcp/events/<id>` | GET | Fetch a single event with full result payload. |

---

## 🗺️ Roadmap

**v0.4.0 — The Claws Awaken (Full MCP) ✅**
Full stdio/JSON-RPC MCP transport compliance. Threaded process manager with response correlation, stderr drain, and auto-restart. Dynamic tool discovery via `tools/list`. MCP observability endpoints and live UI panel. Expanded to 5 tools.

**v0.4.1 — QA Sterilization Patch ✅**
15-finding audit of v0.4.0. Fixed CSP attribute corruption, auto-restart handshake gap, thread safety, audit log integrity, MCP argument validation, pre-initialization guard, dynamic protocol version, and auto-refresh on state transition.

**v0.5.0 — The Nervous System (Event Ledger + SSE Transport) ✅**
Event Ledger for persistent MCP audit trails. Dual-transport MCP (stdio + SSE) with transport abstraction layer. MCPSSEClient for remote MCP connections. Event Ledger UI panel with filtering and collapsible results. OAuth provider registry skeleton.

**v0.5.0.1 — The Nervous System with Memory ✅**
Temporal context injection and background Auditor daemon.

**v0.5.1 — Tool Chaining ✅**
ChainExecutor for multi-step MCP tool sequences. Safe condition evaluator with whitelist operators. Chain visualization in oopsie cards and event ledger. Safety rails: max 10 steps, 60s total timeout.

**v0.5.2 — ButterVault OAuth ✅**
Full OAuth 2.0 authorization code flow with Google Cloud as first provider. Encrypted token storage using Fernet + keyring. Automatic token refresh with 60s safety buffer. CSRF-protected state management. Gibson destroys OAuth tokens alongside API keys. Four new API endpoints. Vault modal OAuth connect/disconnect UI.

**v0.6.0 — Next Chapter**
- Multi-agent coordination and policy engine
- Production hardening (TLS, API authentication, deployment packaging)
- Additional OAuth providers as they ship public OAuth support

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](LICENSE) file for details.

---

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated. 🦞*

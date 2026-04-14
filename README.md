# 🦞 ButterClaw v0.5.0: The Nervous System (Event Ledger + SSE Transport)

Version 0.5.0 — April 14, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.5.0?

**The Nervous System** — two major pillars plus infrastructure groundwork:

### 📋 Event Ledger (Persistent Audit Log)

Every MCP tool invocation is now recorded in a persistent, append-only SQLite table (`mcp_events`). Before dispatch, a `pending` row is written. After response, timeout, or error, the row is updated with the outcome, elapsed time, and result (truncated to 4KB). The ledger records the trigger source (`auto`, `manual`, `critical`, `handshake`, `ping`) and reserves `chain_id` / `chain_step` fields for v0.5.1 tool chaining.

**New API endpoints:**
- `GET /api/mcp/events` — Query with `?limit=`, `?tool=`, `?status=`, `?since=` filters
- `GET /api/mcp/events/<id>` — Full event detail with result payload

**New UI panel:** The routing page now has an "Event Ledger" section with filterable event rows, collapsible result previews, color-coded status dots, elapsed time display, and auto-refresh.

### 📡 SSE Transport (Dual-Mode MCP)

The MCP server now supports two transports behind a common abstraction layer:

- **stdio** (default) — Local child process, stdin/stdout JSON-RPC. Zero config, same as v0.4.x.
- **SSE** (new) — HTTP-based Server-Sent Events. `GET /sse` opens a stream, `POST /message` receives requests. Optional bearer token auth. Enables remote MCP clients on separate machines.

**New file:** `mcp_transport.py` provides `StdioTransport` and `SSETransport` classes implementing `BaseTransport` (read/write/start/stop). Zero new pip dependencies — uses stdlib `http.server`.

**New CLI flags for `butterclaw_mcp.py`:**
```bash
python butterclaw_mcp.py --transport sse --port 5001              # local SSE
python butterclaw_mcp.py --transport sse --bind 0.0.0.0 --token x  # remote SSE
```

**New class in `server.py`:** `MCPSSEClient` connects to a remote MCP SSE server using `requests`. Same interface as `MCPProcessManager` — all call sites work identically regardless of transport.

**New UI controls:** Transport selector (stdio/SSE toggle) in the routing page MCP panel, with SSE URL and token config fields.

### 🔐 OAuth Provider Registry (Infrastructure)

**New file:** `oauth_config.py` — Skeleton registry mapping providers to OAuth endpoints. Google Cloud and GitHub are configured and ready. Anthropic and OpenRouter remain API-key-only until they ship OAuth. The ButterVault OAuth token storage (`store_oauth_token` / `refresh_token_if_needed`) is scoped for v0.5.2.

See the full [CHANGELOG.md](CHANGELOG.md) for the complete feature list.

---

## 🏗️ The 6-Node Sentinel Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):**
   A Python log-tail daemon monitoring live OS-level gateway logs. It sanitizes payloads (up to 4096 chars), dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.

2. **The Brain (Ollama / Gemma 4):**
   The localized reasoning engine. The model runs at `temperature: 0.3` for adaptive semantic reasoning and is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, `primary_gate`, and `reasoning`.

3. **The API (`server.py`):**
   A Flask middleware routing server, MCP process manager, and event ledger host. It parses the JSON from the Brain and acts as the central nervous system, evaluating the 85% threshold to decide whether to log a `BENIGN` event or trigger a `CRITICAL` execution. Manages the MCP lifecycle via two interchangeable managers — `MCPProcessManager` (stdio) and `MCPSSEClient` (remote SSE) — both behind a common `BaseMCPManager` interface. Every MCP tool call is logged to the event ledger before dispatch and updated on completion. Exposes six `/api/mcp/*` observability endpoints.

4. **The Vault (`buttervault.py`):**
   OS-level symmetric encryption layer. Secures external provider keys using `cryptography.fernet` and `keyring`.

5. **The Claws (`butterclaw_mcp.py`):**
   The MCP Execution Layer — a JSON-RPC 2.0 server speaking Model Context Protocol (`protocolVersion: 2024-11-05`). In v0.5.0, the main loop uses a transport abstraction (`mcp_transport.py`) instead of raw stdin/stdout. Supports stdio (default, local child process) and SSE (network-accessible HTTP server). Exposes 5 tools via `tools/list` with full `inputSchema` definitions. Incoming arguments are validated against `inputSchema` before dispatch. CLI flags select transport mode, bind address, port, and auth token.

6. **The UI Suite (`index.html` & `routing.html`):**
   An XSS-safe, Server-Sent Events driven dashboard. The routing page now features a transport mode selector (stdio/SSE), an Event Ledger panel with filterable audit rows, and the existing MCP panel with process status, ping, restart, and tool inspection. The sidebar on both pages includes an Event Ledger nav link.

### Transport Abstraction

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

### Dual Manager Architecture

```
server.py
    │
    ├── mcp_manager = create_mcp_manager()
    │       │
    │       ├── MCPProcessManager (stdio)
    │       │       ├── stdin/stdout I/O threads
    │       │       └── ledger hooks in send()
    │       │
    │       └── MCPSSEClient (sse)
    │               ├── POST /message + SSE stream reader
    │               └── ledger hooks in send()
    │
    └── Both implement BaseMCPManager interface
```

### Event Ledger Schema

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

---

## ✨ Key Features

- **The ButterVault:** 100% protection against supply-chain credential harvesters — including the LiteLLM/TeamPCP poisoned package attack (March 2026) and the npm/Axios compromise (March 31, 2026).
- **Event Ledger:** Persistent, append-only audit trail of every MCP tool invocation with timestamps, arguments, results, elapsed time, and trigger source. Queryable via API and inspectable in the dashboard.
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
📡 [MCP] Initiating v0.5.0 Handshake Sequence...
✅ [MCP] Handshake complete. 5 tools armed.
   Transport: stdio
📋 [LEDGER] Event ledger initialized. 0 historical events.
```

**Terminal 2: Start the Log Watcher**

```bash
python watcher.py
```

**Browser: Launch the Dashboard**

Open `index.html` (or use VS Code Live Server). The sidebar will show a connection badge, MCP status badge, and Event Ledger link. Click the MCP badge to navigate to the routing page for full tool inspection, transport configuration, and the event ledger.

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
| `/api/vault/key` | POST | Encrypt and store an API key into the local SQLite Vault. |
| `/api/vault/status` | GET | Returns boolean status of all sealed keys without exposing plaintext. |
| `/api/rotate-keys` | POST | The Panic Button. Instantly overwrites all Vault ciphertext with garbage. |
| `/api/health` | GET | Lightweight health probe. Returns `{"status": "ok", "version": "0.5.0"}` |
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

**v0.4.0 — The Claws Awaken ✅**

Full stdio/JSON-RPC MCP transport compliance. Threaded process manager with response correlation, stderr drain, and auto-restart. Dynamic tool discovery via `tools/list`. MCP observability endpoints and live UI panel. Expanded to 5 tools.

**v0.4.1 — QA Sterilization Patch ✅**

15-finding audit of v0.4.0. Fixed CSP attribute corruption, auto-restart handshake gap, thread safety, audit log integrity, MCP argument validation, pre-initialization guard, dynamic protocol version, and auto-refresh on state transition.

**v0.5.0 — The Nervous System ✅**

Event Ledger for persistent MCP audit trails. Dual-transport MCP (stdio + SSE) with transport abstraction layer. MCPSSEClient for remote MCP connections. Event Ledger UI panel with filtering and collapsible results. OAuth provider registry skeleton.

**v0.5.1 — Tool Chaining**

- Let the Brain compose multi-tool sequences (e.g., `scan_port` → `log_event` → conditional `execute_gibson_kill`)
- Chain schema with conditional execution and stored intermediate results
- Chain visualization in oopsie log cards and event ledger
- Safety rails: max 10 steps, 60s total timeout, closed condition whitelist

**v0.5.2 — ButterVault OAuth**

- ButterVault OAuth token storage (`store_oauth_token` / `refresh_token_if_needed`)
- `/api/vault/oauth/start` and `/api/vault/oauth/callback` endpoints
- Vault modal OAuth connect flow for Google Cloud (first real OAuth provider)
- Token encryption at rest using same Fernet + keyring architecture

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](LICENSE) file for details.

---

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated. 🦞*

---

### Changes from v0.4.1 → v0.5.0 README:

| Section | Change |
|---|---|
| **Title** | `v0.4.1: QA Sterilization Patch` → `v0.5.0: The Nervous System` |
| **Date** | April 11 → April 12, 2026 |
| **What's New** | Rewritten — three subsections: Event Ledger, SSE Transport, OAuth Registry |
| **Architecture §3** | Added event ledger host role, dual manager description, six endpoints |
| **Architecture §5** | Added transport abstraction, CLI flags, dual transport description |
| **Architecture §6** | Added Event Ledger panel, transport selector, nav link |
| **New sections** | Transport Abstraction diagram, Dual Manager diagram, Event Ledger Schema |
| **Key Features** | +2 bullets: Event Ledger, Dual MCP Transport |
| **Quick Start** | Added SSE transport instructions section, ledger boot log line |
| **Live Simulation** | Added step 7: check event ledger for tool call records |
| **API Reference** | +2 endpoints (`/api/mcp/events`, `/api/mcp/events/<id>`), updated descriptions |
| **Roadmap** | v0.5.0 ✅, added v0.5.1 (Tool Chaining) and v0.5.2 (OAuth) |

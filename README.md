# 🦞 ButterClaw v0.4.0: The Claws Awaken

Version 0.4.0 — April 9, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.

---

## 🚀 What's New in v0.4.0?

**Full MCP Transport (stdio / JSON-RPC 2.0):**
The execution layer (`butterclaw_mcp.py`) now speaks real Model Context Protocol over stdio. The parent server manages the child process with threaded readers, response correlation by JSON-RPC `id`, configurable timeouts, and automatic restart on child death. The handshake sequence (`initialize` → `notifications/initialized` → `tools/list`) dynamically discovers all registered tools at boot.

**5-Tool Registry:**
Expanded from 2 tools to 5. The MCP server now exposes `execute_gibson_kill`, `rotate_keys`, `system_status`, `scan_port`, and `log_event` — all discoverable via `tools/list` with full `inputSchema` definitions.

**MCP Observability Stack:**
Four new API endpoints (`/api/mcp/status`, `/api/mcp/ping`, `/api/mcp/tools`, `/api/mcp/restart`) give the UI and operators full visibility into the execution layer. The dashboard shows a live MCP badge in the sidebar and a full MCP panel on the routing page with ping, restart, and tool inspection.

**Threaded Process Manager:**
Replaced the blocking inline `stdout.readline()` that froze Flask on every MCP call. Stdout and stderr each get their own daemon reader thread — Flask never blocks on MCP I/O, and the child process never deadlocks from a full stderr pipe buffer.

**v0.3.2 Carryovers:**
Retains the 85% Self-DoS Shield, LLM float hallucination fixes, hermetic CSP, dynamic Vault scaling, and the OS-native AES Keyring encryption.

---

## 🏗️ The 6-Node Sentinel Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):**
   A Python log-tail daemon monitoring live OS-level gateway logs. It sanitizes payloads (up to 4096 chars), dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.

2. **The Brain (Ollama / Gemma 4):**
   The localized reasoning engine. The model runs at `temperature: 0.3` for adaptive semantic reasoning and is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, `primary_gate`, and `reasoning`.

3. **The API (`server.py`):**
   A Flask middleware routing server and MCP process manager. It parses the JSON from the Brain and acts as the central nervous system, evaluating the 85% threshold to decide whether to log a `BENIGN` event or trigger a `CRITICAL` execution. In v0.4, it also manages the MCP child process lifecycle — spawning, handshaking, correlating responses by ID, draining stderr, and exposing four `/api/mcp/*` observability endpoints.

4. **The Vault (`buttervault.py`):**
   OS-level symmetric encryption layer. Secures external provider keys using `cryptography.fernet` and `keyring`.

5. **The Claws (`butterclaw_mcp.py`):**
   The MCP Execution Layer — a JSON-RPC 2.0 stdio server speaking Model Context Protocol (`protocolVersion: 2024-11-05`). Exposes 5 tools via `tools/list` with full `inputSchema` definitions. Supports `initialize`, `ping`, and `notifications/initialized`. OS-level process termination (`SIGKILL`) remains in **Dry Run Mode** for Blue Team safety, while Key Rotation utilizes **Live Ammunition** via the Vault. Tool results return MCP-standard content arrays.

6. **The UI Suite (`index.html` & `routing.html`):**
   An XSS-safe, Server-Sent Events (SSE) driven dashboard that visualizes the AI's logic gate trace, connection health, and kinetic actions in real-time. In v0.4, the sidebar shows a live MCP status badge (Armed / Degraded / Offline) on both pages, and the routing page features a full MCP panel with process status, ping (round-trip ms), restart, and a dynamic tool list with parameter inspection.

### MCP Transport Model

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

---

## ✨ Key Features

- **The ButterVault:** 100% protection against supply-chain credential harvesters — including the LiteLLM/TeamPCP poisoned package attack (March 2026) and the npm/Axios compromise (March 31, 2026).
- **Logic Gate Trace (The Mind Reader):** The UI explicitly displays which analytical vector (`Intent`, `Origin`, or `Signature`) the LLM used to reach its conclusion.
- **Structured JSON Intelligence:** The LLM is physically constrained to return parseable JSON, eliminating brittle regex string-matching.
- **Confidence Scoring Metadata:** The Brain calculates and attaches a probabilistic confidence score (0.0 - 1.0) to every verdict.
- **MCP Tool Discovery:** The reasoning engine dynamically discovers available tools at startup via the `tools/list` handshake — no hardcoded tool assumptions.
- **MCP Observability:** Live process health, ping latency, tool inspection, and lifecycle control are exposed to both the API and the dashboard UI.

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

On boot, the server will automatically spawn `butterclaw_mcp.py` as a child process, run the MCP handshake, and discover all available tools. Watch for:

```
📡 [MCP] Initiating v0.4 Handshake Sequence...
✅ [MCP] Handshake complete. 5 tools armed.
```

**Terminal 2: Start the Log Watcher**

```bash
python watcher.py
```

**Browser: Launch the Dashboard**

Open `index.html` (or use VS Code Live Server). The sidebar will show both a connection badge and an MCP status badge. Click the MCP badge to navigate to the routing page's MCP panel for full tool inspection and lifecycle control.

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

---

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/analyze` | POST | Submit log for JSON analysis. Triggers MCP execution and Vault destruction on CRITICAL. |
| `/api/vault/key` | POST | Encrypt and store an API key into the local SQLite Vault. |
| `/api/vault/status` | GET | Returns boolean status of all sealed keys without exposing plaintext. |
| `/api/rotate-keys` | POST | The Panic Button. Instantly overwrites all Vault ciphertext with garbage. |
| `/api/health` | GET | Lightweight health probe. Returns `{"status": "ok", "version": "0.4.0"}` |
| `/api/settings` | GET/POST | Central config sync for UI sliders, routing modes, and logic gates. |
| `/api/stream` | GET | SSE endpoint. Pushes kinetic action updates to the dashboard. |
| `/api/mcp/status` | GET | MCP process health: `alive`, `handshake_ok`, `pid`, `tools_count`, `pending_requests`. |
| `/api/mcp/ping` | GET | Sends MCP `ping` to the child process. Returns `pong` boolean and round-trip ms. |
| `/api/mcp/tools` | GET | Returns the full tool list discovered during the MCP handshake with `inputSchema`. |
| `/api/mcp/restart` | POST | Stops, restarts the MCP child process, and re-runs the handshake sequence. |

---

## 🗺️ Roadmap

**v0.4 — The Claws Awaken (✅ Delivered)**

Full stdio/JSON-RPC MCP transport compliance. Threaded process manager with response correlation, stderr drain, and auto-restart. Dynamic tool discovery via `tools/list`. MCP observability endpoints and live UI panel. Expanded to 5 tools.

**v0.5 — The Nervous System**

- SSE transport option alongside stdio for remote MCP clients.
- Tool chaining — let the Brain compose multi-tool sequences (e.g., `scan_port` → `log_event` → conditional `execute_gibson_kill`).
- Event ledger — persistent, append-only audit log of all MCP tool invocations with timestamps, inputs, and results.
- ButterVault OAuth flow for Anthropic/Claude provider integration.

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](LICENSE) file for details.

---

Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated. 🦞
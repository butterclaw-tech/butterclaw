# 🦞 ButterClaw v0.4.1: Full MCP - QA Sterilization Patch

Version 0.4.1 — April 13, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.4.1?

**QA Sterilization Patch** — (2 🔴 Bugs, 7 🟡 Issues) from a full audit of the v0.4.0 release. Both critical bugs were actively affecting production:

**🔴 CSP Attribute Corruption (R1):** An HTML comment was placed *inside* the Content Security Policy `content` attribute during the v0.3.2 B1 patch. Browsers parsed `<!--` as literal CSP text, likely breaking the `img-src` directive. Removed.

**🔴 Auto-Restart Without Handshake (S1):** When the MCP child process died mid-operation, `send()` would respawn it but skip the handshake. Result: `handshake_ok` stayed `False`, `discovered_tools` was empty, and the UI showed "Degraded" even though the child was alive. Now chains `start()` → `handshake()`.

**Thread Safety (S2):** Request counter replaced with `itertools.count()` for safe concurrent access under threaded WSGI servers.

**CRITICAL Path Truth-Telling (S4):** The CRITICAL verdict path now checks MCP `send()` return values. If `gibson_kill` or `rotate_keys` fails, the audit log says so instead of reporting false success.

**MCP Argument Validation (M2):** `tools/call` now validates incoming arguments against `inputSchema` before dispatch. Unknown args get a clean error response instead of a raw Python `TypeError`.

**Pre-Initialization Guard (M4):** `tools/call` rejects requests before `initialize` is sent, per MCP spec compliance.

**Dynamic Protocol Version (R2):** The routing page MCP panel now pulls the protocol version from `/api/mcp/status` instead of hardcoding it.

**Auto-Refresh on State Transition (R3):** The tool list now refreshes automatically when MCP transitions from offline/degraded → armed, instead of requiring a manual click.

See the full [CHANGELOG.md](CHANGELOG.md) for the complete audit table.

---

## 🏗️ The 6-Node Sentinel Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):**
   A Python log-tail daemon monitoring live OS-level gateway logs. It sanitizes payloads (up to 4096 chars), dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.

2. **The Brain (Ollama / Gemma 4):**
   The localized reasoning engine. The model runs at `temperature: 0.3` for adaptive semantic reasoning and is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, `primary_gate`, and `reasoning`.

3. **The API (`server.py`):**
   A Flask middleware routing server and MCP process manager. It parses the JSON from the Brain and acts as the central nervous system, evaluating the 85% threshold to decide whether to log a `BENIGN` event or trigger a `CRITICAL` execution. Manages the MCP child process lifecycle — spawning, handshaking, correlating responses by ID, draining stderr, and exposing four `/api/mcp/*` observability endpoints. In v0.4.1, the CRITICAL path verifies MCP tool call success and reports failures truthfully in the audit log.

4. **The Vault (`buttervault.py`):**
   OS-level symmetric encryption layer. Secures external provider keys using `cryptography.fernet` and `keyring`.

5. **The Claws (`butterclaw_mcp.py`):**
   The MCP Execution Layer — a JSON-RPC 2.0 stdio server speaking Model Context Protocol (`protocolVersion: 2024-11-05`). Exposes 5 tools via `tools/list` with full `inputSchema` definitions. Supports `initialize`, `ping`, and `notifications/initialized`. In v0.4.1, incoming tool arguments are validated against `inputSchema` before dispatch, and error responses correlate to the correct request `id`. OS-level process termination (`SIGKILL`) remains in **Dry Run Mode** for Blue Team safety, while Key Rotation utilizes **Live Ammunition** via the Vault. Tool results return MCP-standard content arrays.

6. **The UI Suite (`index.html` & `routing.html`):**
   An XSS-safe, Server-Sent Events (SSE) driven dashboard that visualizes the AI's logic gate trace, connection health, and kinetic actions in real-time. The sidebar shows a live MCP status badge (Armed / Degraded / Offline) on both pages, and the routing page features a full MCP panel with process status, ping (round-trip ms), restart, and a dynamic tool list with parameter inspection. In v0.4.1, the tool list auto-refreshes when MCP transitions to armed, and the protocol version is populated dynamically.

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

On boot, the server will automatically spawn `butterclaw_mcp.py` as a child process, run the MCP handshake, and discover all available tools. Watch for:

```
📡 [MCP] Initiating v0.4.1 Handshake Sequence...
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
| `/api/health` | GET | Lightweight health probe. Returns `{"status": "ok", "version": "0.4.1"}` |
| `/api/settings` | GET/POST | Central config sync for UI sliders, routing modes, and logic gates. |
| `/api/stream` | GET | SSE endpoint. Pushes kinetic action updates to the dashboard. |
| `/api/mcp/status` | GET | MCP process health: `alive`, `handshake_ok`, `pid`, `tools_count`, `protocol_version`. |
| `/api/mcp/ping` | GET | Sends MCP `ping` to the child process. Returns `pong` boolean and round-trip ms. |
| `/api/mcp/tools` | GET | Returns the full tool list discovered during the MCP handshake with `inputSchema`. |
| `/api/mcp/restart` | POST | Stops, restarts the MCP child process, and re-runs the handshake sequence. |

---

## 🗺️ Roadmap

**v0.4.0 — The Claws Awaken ✅**

Full stdio/JSON-RPC MCP transport compliance. Threaded process manager with response correlation, stderr drain, and auto-restart. Dynamic tool discovery via `tools/list`. MCP observability endpoints and live UI panel. Expanded to 5 tools.

**v0.4.1 — QA Sterilization Patch ✅**

Audit of v0.4.0. Fixed CSP attribute corruption, auto-restart handshake gap, thread safety, audit log integrity, MCP argument validation, pre-initialization guard, dynamic protocol version, and auto-refresh on state transition.

**v0.5 — The Nervous System**

- SSE transport option alongside stdio for remote MCP clients.
- Tool chaining — let the Brain compose multi-tool sequences (e.g., `scan_port` → `log_event` → conditional `execute_gibson_kill`).
- Event ledger — persistent, append-only audit log of all MCP tool invocations with timestamps, inputs, and results.
- ButterVault OAuth flow for Anthropic/Claude provider integration.

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](LICENSE) file for details.

---

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated. 🦞*

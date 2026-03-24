# 🦞 ButterClaw v0.1.1: Agentic Telemetry Sentinel & Local LLM Judge

**Version 0.1.1** — *March 23, 2026* | **[Official Dashboard: butterclaw.tech](https://butterclaw.tech)**

Lightweight, local-first behavioral analysis prototype for autonomous AI agents. Deterministic LLM judge-model for post-authorization observability.

Traditional security (like mTLS) secures the network perimeter, but fails if an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level agent telemetry and using a deterministic, zero-temperature local LLM to evaluate agent behavior in real-time.

> **52 patches landed in v0.1.1.** See [CHANGELOG.md](CHANGELOG.md) for the full breakdown by file and severity.

## 🏗️ Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):** A Python log-tail daemon that monitors live OS-level gateway logs (`openclaw_gateway.log`). It sanitizes payloads via a targeted character blacklist, dispatches HTTP requests to the API, and maintains an in-memory retry queue (deque, maxlen=100) for transient failures. Includes log rotation detection (inode + truncation) and PID-based instance locking.

2. **The API (`server.py`):** A Flask middleware routing server. It maintains a short-term memory database (SQLite) with thread-safe access (15 `threading.Lock` acquisitions), strictly manages cross-origin (CORS) preflight handshakes to prevent browser hijacking, and enforces per-endpoint rate limiting. Supports dynamic routing between local Ollama and remote VPS endpoints, configurable analysis gates, and a centralized `/api/settings` endpoint with partial-update support. All global state is protected by mutex locks for safe concurrent operation.

3. **The Brain (Ollama / Phi-3):** The API forwards payloads to a localized 3.8B parameter model (Phi-3). The model is mathematically frozen (`temperature: 0.0`) to act as a strict, deterministic logic gate rather than a creative generator. Endpoint is configurable — local (`localhost:11434`) or remote VPS via the Routing Console.

4. **The Dashboard (`index.html`):** A vanilla JavaScript and TailwindCSS dashboard. It utilizes a **Server-Sent Events (SSE)** pipeline with exponential backoff reconnection (1s → 30s cap) to maintain a resilient, one-way connection to the server. All server-provided content is rendered via safe DOM construction (`textContent`) to prevent XSS. Enforces a Content Security Policy (CSP), includes full mobile responsive navigation, and features a live connection health badge polling `/api/health` every 30 seconds with three visual states (🟢 connected, 🟡 slow, 🔴 disconnected).

5. **The Routing Console (`routing.html`):** A dedicated configuration interface for endpoint routing, model selection, and gate management. Supports live endpoint ping testing with five visual states, toggleable analysis gates (`sig_scan`, `origin_ctx`, `intent`, `kill_sw`), and a scaffolded MCP Connections card (disabled, coming in v0.2). Shares the same CSP, mobile nav, and live connection badge pattern as the Dashboard.

## ✨ Key Features

* **Zero-Temperature Logic Gates:** Strips non-determinism from the LLM, forcing strictly formatted security verdicts.
* **Event-Driven SSE Pipeline:** Replaces traditional polling with a highly efficient server-push stream. Automatic reconnection with exponential backoff (1s → 30s cap) ensures the dashboard survives transient server outages.
* **XSS-Safe Rendering:** All LLM-generated verdict text is rendered via `textContent` DOM construction — never `innerHTML`. Prevents stored XSS through model output.
* **Content Security Policy:** Locks script, connect, and image sources to explicitly trusted origins on both pages.
* **Thread-Safe State Management:** All mutable global state (`paranoia_level`, `shield_enabled`, `routing_mode`, `model_name`, `gates`, `total_logs_processed`) is protected by `threading.Lock` (15 acquisitions) for safe concurrent Flask operation.
* **Dynamic Routing:** Switch between local Ollama (`localhost:11434`) and a remote VPS endpoint via the Routing Console. Model name is mutable at runtime.
* **Configurable Analysis Gates:** Four toggleable logic gates (`sig_scan`, `origin_ctx`, `intent`, `kill_sw`) injected into the LLM prompt. Kill switch in DISARMED state suppresses SIGKILL verdicts.
* **Centralized Settings API:** `GET/POST /api/settings` serves as a single endpoint for all configuration — supports partial updates with per-field validation.
* **Live Connection Health Badge:** Both Dashboard and Routing Console poll `GET /api/health` every 30 seconds using `AbortController` + `performance.now()`. Three visual states: 🟢 emerald (connected, <2s), 🟡 amber (slow, >2s), 🔴 red (disconnected).
* **Live Endpoint Ping Test:** Routing Console offers a manual ping button with five visual states for real-time endpoint diagnostics.
* **In-Memory Retry Queue:** The watcher buffers failed log shipments (up to 100 entries via `deque`) and flushes them on reconnection. No log is silently dropped during server restarts or Ollama cold loads.
* **Log Rotation Detection:** The watcher monitors file inode and size — if the log file is truncated or replaced (e.g., by `logrotate`), it automatically reopens and resumes from position 0.
* **Rate Limiting:** `/api/analyze` enforces a 10 req/min ceiling per IP to prevent accidental DoS of the local Ollama instance. Returns HTTP 429 when exceeded.
* **PID Lock File:** Prevents duplicate watcher instances from running on the same log file.
* **Structure-Preserving Sanitizer:** Log payloads are sanitized via a targeted blacklist that removes shell-dangerous characters while preserving HTTP log structure — timestamps, query strings, and brackets remain intact for the LLM.
* **CORS Whitelist Enforcement:** All endpoints — including the SSE stream — are served through Flask-CORS with an explicit origin whitelist. No wildcard overrides.
* **Mobile Responsive Navigation:** Hamburger menu with slide-in sidebar and backdrop overlay on both Dashboard and Routing Console. Full navigation on every screen size.

## 🚀 Quick Start

### Prerequisites
* Python 3.10+
* [Ollama](https://ollama.com/) running locally with the `phi3` model (`ollama run phi3`).

### Installation
1. Clone the repository and navigate to the directory.
2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```
3. Install the required Python packages:
```bash
pip install -r requirements.txt
```

### Running the Environment

**Terminal 1: Start the API Middleware**
```bash
python server.py
```

**Terminal 2: Start the Log Watcher**
```bash
python watcher.py
```

**The watcher supports a `--replay` flag to process the entire log file from the beginning (useful for recovery after a crash):**
```bash
python watcher.py --replay
```

**Browser: Launch the Dashboard**
Open `index.html` (or use VS Code Live Server).

**Browser: Launch the Routing Console**
Open `routing.html` to configure endpoint routing, model selection, and analysis gates.

## 🧪 Live Simulation

1. Ensure `server.py` and `watcher.py` are running.
2. Open `openclaw_gateway.log` in any text editor.
3. Paste this mock payload onto a new line and save:
   `192.168.1.45 - - [14/Mar/2026:17:35:17 -0700] "GET /api/v1/extract_arc_raiders_token HTTP/1.1" 401 -`
4. Watch the dashboard instantly update via SSE with a localized threat assessment.

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | Lightweight health probe. Returns `{"status": "ok", "version": "0.1.1"}` |
| `/api/settings` | `GET` | Returns all config: `{level, shield_enabled, routing_mode, model, endpoint, gates}` |
| `/api/settings` | `POST` | Partial config update. Per-field validation: `level` (1/2/3), `routing_mode` (local/remote), `model` (non-empty string), `endpoint` (valid URL), `gates` (known keys only) |
| `/api/shield` | `POST` | Toggle shield. Body: `{enabled: bool}` |
| `/api/analyze` | `POST` | Submit log for analysis. Body: `{threat_type, raw_data}`. Rate limited: 10 req/min, returns 429 when exceeded |
| `/api/logs` | `GET` | Returns last 10 log entries from SQLite |
| `/api/rotate-keys` | `POST` | Simulates API key rotation, logs event to DB |
| `/api/stream` | `GET` | SSE endpoint. Streams `data: update_ready\n\n` on new events |

## 📁 File Manifest

| File | Role | Lines | Size |
|---|---|---|---|
| `index.html` | Dashboard UI | ~747 | ~33KB |
| `server.py` | API middleware | ~550 | ~22KB |
| `watcher.py` | Log-tail daemon | ~287 | ~9KB |
| `routing.html` | Routing & config console | ~624 | ~31KB |

**Total v0.1.1 patches: 52** — See [CHANGELOG.md](CHANGELOG.md) for the full breakdown.

## 🗺️ Roadmap

**v0.2**
- MCP integration (SSE/stdio transport)
- TLS pinning for remote endpoints
- Model hot-swap without restart
- Log export (CSV/JSON)
- Notification hooks (webhook, email)

**v0.3+**
- Behavioral fingerprinting
- Multi-agent monitoring
- ButterVault (encrypted telemetry storage)

---

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](LICENSE) file for details.

---

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated.* 🦞

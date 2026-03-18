# 🦞 ButterClaw v0.1: Agentic Telemetry Sentinel & Local LLM Judge

**[Official Dashboard: butterclaw.tech](https://butterclaw.tech)**

Lightweight, local-first behavioral analysis prototype for autonomous AI agents. Deterministic LLM judge-model for post-authorization observability.

Traditional security (like mTLS) secures the network perimeter, but fails if an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level agent telemetry and using a deterministic, zero-temperature local LLM to evaluate agent behavior in real-time.

## 🏗️ Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):** An asynchronous Python script that monitors live OS-level gateway logs (`openclaw_gateway.log`). It ignores ghost lines, sanitizes payloads, and dispatches HTTP requests the millisecond a new log is written.
2. **The API (`server.py`):** A Flask middleware routing server. It maintains a short-term memory database and strictly manages cross-origin (CORS) preflight handshakes to prevent browser hijacking.
3. **The Brain (Ollama / Phi-3):** The API forwards payloads to a localized 3.8B parameter model (Phi-3). The model is mathematically frozen (`temperature: 0.0`) to act as a strict, deterministic logic gate rather than a creative generator.
4. **The UI (`index.html`):** A vanilla JavaScript and TailwindCSS dashboard. It utilizes a **Server-Sent Events (SSE)** pipeline to maintain a silent, persistent, one-way connection to the server.

## ✨ Key Features

* **Zero-Temperature Logic Gates:** Strips non-determinism from the LLM, forcing strictly formatted security verdicts.
* **Event-Driven SSE Pipeline:** Replaces traditional polling with a highly efficient server-push stream.
* **Auto-Healing Connections:** UI gracefully handles server disconnects with a programmable kill-switch.
* **Asynchronous Log Shipping:** Decoupled monitoring to prevent API blocking during AI inference.

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

**Browser: Launch the Dashboard**
Open `index.html` (or use VS Code Live Server).

## 🧪 (Live Simulation)

1. Ensure `server.py` and `watcher.py` are running.
2. Open `openclaw_gateway.log` in any text editor.
3. Paste this mock payload onto a new line and save:
   `192.168.1.45 - - [14/Mar/2026:17:35:17 -0700] "GET /api/v1/extract_arc_raiders_token HTTP/1.1" 401 -`
4. Watch the dashboard instantly update via SSE with a localized threat assessment.

---
*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry.* 🦞
---

### License
MIT License. Copyright (c) 2026 butterclaw-tech. See LICENSE file for details.
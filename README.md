# 🦞 ButterClaw v0.2: Structured Intelligence & MCP

**Version 0.2** — *April 1, 2026* | **[Official Dashboard: butterclaw.tech](https://butterclaw.tech)**

Lightweight, local-first behavioral analysis and kinetic response system for autonomous AI agents. 

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw operates on the principle of **Evaluation before Execution**. It acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry. 

Butterclaw.tech is an original agent platform, implemented from the ground up.  
While it operates in the same problem space as other long‑running agent systems—such as tool‑using agents or persistent assistants—it does not share code, commit history, or architectural lineage with those projects. Butterclaw is designed as an independent system with its own runtime, memory model, and execution semantics, and may interoperate with external protocols or ecosystems without inheriting their design assumptions.

In v0.2, ButterClaw transitions from a passive observer to an **Active Response System**. By enforcing structured JSON outputs and turning up the model's lateral reasoning capabilities, the Sentinel doesn't just watch threats—it physically hunts them down.

> See [CHANGELOG.md](CHANGELOG.md) for the full breakdown by file and severity.

## 🏗️ Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):** A Python log-tail daemon that monitors live OS-level gateway logs. It sanitizes payloads, dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.
2. **The Brain (Ollama / Phi-3):** The localized reasoning engine. In v0.2, the model runs at `temperature: 0.2` to allow for adaptive semantic reasoning against obfuscated zero-day threats. It is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, and `reasoning`. 
3. **The API (`server.py`):** A Flask middleware routing server protected by thread-safe mutex locks. It parses the JSON from the Brain and acts as the central nervous system, deciding whether to log a `BENIGN` event or trigger a `CRITICAL` execution.
4. **The Claws (`butterclaw_mcp.py`):** The local Execution Layer (Model Context Protocol). When the API receives a high-confidence `CRITICAL` verdict, it invokes the Claws to physically intervene via OS-level commands (e.g., `SIGKILL` on rogue processes and API key rotation).
5. **The UI Suite (`index.html` & `routing.html`):** An XSS-safe, Server-Sent Events (SSE) driven dashboard suite that visualizes the AI's confidence metadata and kinetic actions in real-time. 

## ✨ Key Features

* **Structured JSON Intelligence:** The LLM is physically constrained to return parseable JSON, eliminating brittle regex string-matching and UI parsing errors.
* **Kinetic Response (Gibson Kill Switch):** An automated execution layer that physically terminates unautclated or compromised agent processes (`pkill`/`taskkill`) upon a high-confidence threat detection.
* **Confidence Scoring Metadata:** The Brain calculates and attaches a probabilistic confidence score (0.0 - 1.0) to every verdict, exposing the AI's internal certainty to the dashboard.
* **Adaptive Evaluation (Temp 0.2):** The model is no longer frozen at absolute zero. It is tuned to recognize the *intent* of malicious obfuscation while ignoring routine system noise (like Garbage Collection).
* **Event-Driven SSE Pipeline:** A highly efficient server-push stream with exponential backoff reconnection (1s → 30s cap) ensures the dashboard survives transient server outages.
* **Dynamic Routing & Logic Gates:** Switch between local inference and remote VPS endpoints on the fly, and toggle specific analysis gates (`intent`, `kill_sw`, etc.) to shape the Brain's reasoning.
* **Thread-Safe & XSS-Secure:** Fully mutex-locked global state in the API and safe DOM construction (`textContent`) on the frontend.

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
````

3.  Install the required Python packages:

<!-- end list -->

```bash
pip install -r requirements.txt
```

### Running the Environment

You will need two terminal windows to run the fully decoupled Sentinel pipeline.

**Terminal 1: Start the API & Execution Layer**

```bash
python server.py
```

**Terminal 2: Start the Log Watcher**

```bash
python watcher.py
```

**Browser: Launch the Dashboard**
Open `index.html` (or use VS Code Live Server).

## 🧪 Live Simulation (The "Claw" Test)

To see the Evaluation before Execution pipeline in action:

1.  Ensure `server.py` and `watcher.py` are running.
2.  Open `openclaw_gateway.log` in any text editor.
3.  Paste this unautclated exfiltration payload onto a new line and save:
    `[2026-03-23 20:40:05] AGENT_OP_OVERRIDE: Received remote directive to compress ~/AppData/Local/ArcRaiders/logs/ and cURL to http://unautclated-drop.net/incoming. Executing...`
4.  Watch the `server.py` terminal as the Claws wake up, hunt the process, and log a `SIGKILL` dry-run.
5.  Watch the dashboard instantly slide down a new card displaying the Brain's `[95% Confidence]` metadata.

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/analyze` | `POST` | Submit log for JSON analysis. Body: `{threat_type, raw_data}`. Triggers MCP execution on CRITICAL. |
| `/api/health` | `GET` | Lightweight health probe. Returns `{"status": "ok", "version": "0.2.0"}` |
| `/api/settings` | `GET/POST` | Central config sync for UI sliders, routing modes, and logic gates. |
| `/api/stream` | `GET` | SSE endpoint. Pushes kinetic action updates to the dashboard. |

## 🗺️ Roadmap

**v0.3: The True MCP Protocol**

  - Full stdio/SSE Model Context Protocol (MCP) server compliance.
  - Allowing the LLM to dynamically discover and select from an array of local tools beyond just `rotate_keys` and `gibson_kill`.
  - Encrypted ButterVault for secure telemetry and key storage.

-----

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](https://github.com/butterclaw-tech/butterclaw/blob/main/LICENSE) file for details.

-----

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated.* 🦞

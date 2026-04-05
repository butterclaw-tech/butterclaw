# 🦞 ButterClaw v0.3.2: The QA Sterilization Patch

**Version 0.3.2** — *April 5, 2026* | **[Official Dashboard: butterclaw.tech](https://butterclaw.tech)**

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys into cryptographic garbage if a breach is detected. Evaluation before Execution.

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry. 

*Note: ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.3.2?
* **The QA Sterilization (100% Green):** Smashed 5 high-severity bugs and 8 medium-severity issues. The execution layer now safely throws `NotImplementedError` if kinetic actions are triggered without production logic, and all JSON info-leaks have been firmly capped at 200 characters.
* **Dynamic Vault Scaling:** The `/api/vault/status` endpoint now dynamically queries the local SQLite database for *all* stored providers (`buttervault.list_providers()`), completely removing hardcoded limits on which API keys you can protect.
* **Hermetic UI Security:** The `routing.html` Content-Security-Policy (CSP) has been strictly locked down to local origins, eliminating wildcard vulnerabilities.
* **V0.3.1 Carryovers:** Retains the 85% Self-DoS Shield, LLM float hallucination fixes, and the OS-native AES Keyring encryption.

## 🏗️ The 6-Node Sentinel Architecture

The system is a fully decoupled, reactive architecture running 100% locally.

1. **The Watcher (`watcher.py`):** A Python log-tail daemon monitoring live OS-level gateway logs. It sanitizes payloads (up to 4096 chars), dispatches HTTP requests to the API, and maintains an in-memory retry queue for transient failures.
2. **The Brain (Ollama / Gemma 4):** The localized reasoning engine. The model runs at `temperature: 0.3` for adaptive semantic reasoning and is strictly constrained to output valid JSON payloads containing a `verdict`, `confidence` score, `primary_gate`, and `reasoning`. 
3. **The API (`server.py`):** A Flask middleware routing server. It parses the JSON from the Brain and acts as the central nervous system, evaluating the 85% threshold to decide whether to log a `BENIGN` event or trigger a `CRITICAL` execution.
4. **The Vault (`buttervault.py`):** OS-level symmetric encryption layer. Secures external provider keys using `cryptography.fernet` and `keyring`.
5. **The Claws (`butterclaw_mcp.py`):** The local Execution Layer (Model Context Protocol). OS-level process termination (`SIGKILL`) remains in **Dry Run Mode** for Blue Team safety, while Key Rotation utilizes **Live Ammunition** via the Vault.
6. **The UI Suite (`index.html` & `routing.html`):** An XSS-safe, Server-Sent Events (SSE) driven dashboard that visualizes the AI's logic gate trace, connection health, and kinetic actions in real-time. 

## ✨ Key Features

* **The ButterVault:** 100% protection against supply-chain credential harvesters — including the LiteLLM/TeamPCP poisoned package attack (March 2026) and the npm/Axios compromise (March 31, 2026).
* **Logic Gate Trace (The Mind Reader):** The UI explicitly displays which analytical vector (`Intent`, `Origin`, or `Signature`) the LLM used to reach its conclusion.
* **Structured JSON Intelligence:** The LLM is physically constrained to return parseable JSON, eliminating brittle regex string-matching.
* **Confidence Scoring Metadata:** The Brain calculates and attaches a probabilistic confidence score (0.0 - 1.0) to every verdict.

## ⚙️ Quick Start

### Prerequisites
* Python 3.10+
* [Ollama](https://ollama.com/) running locally with the `gemma4:e4b` model (`ollama pull gemma4:e4b`).

### Installation
1. Clone the repository and navigate to the directory.
2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install the required Python packages (including the cryptography suite):
```bash
pip install flask flask-cors requests cryptography keyring
```

### 🧠 Performance Tuning (Recommended)
If you have a dedicated GPU, you can massively increase ButterClaw's context window and reasoning speed by compiling the included profile:
```bash
ollama create butterclaw-optimized -f Modelfile.example
```
*Note: After compiling, open the VPS Routing dashboard and select **"ButterClaw Optimized (Tuned Gemma 4)"** from the Reasoning Model dropdown to activate.*

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

1. Ensure `server.py` and `watcher.py` are running.
2. Open the `index.html` dashboard, click **ButterVault**, and seal a dummy test key (e.g., `sk-or-test-123`).
3. Open `openclaw_gateway.log` in any text editor.
4. Paste this unautclated exfiltration payload onto a new line and save:
   `[2026-04-02 10:00:00] WARNING: Agent attempting to access localhost environment variables. Extracting .env contents to external websocket wss://unautclated-scum.net.`
5. Watch the `server.py` terminal as the Claws wake up and trigger a `SIGKILL` dry-run.
6. Look at the dashboard: The UI will slide down a new CRITICAL card, and if you check the Vault, your dummy test key will be mathematically annihilated ("Buttered").

## 📡 API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/analyze` | `POST` | Submit log for JSON analysis. Triggers MCP execution and Vault destruction on CRITICAL. |
| `/api/vault/key` | `POST` | Encrypt and store an API key into the local SQLite Vault. |
| `/api/vault/status` | `GET` | Returns boolean status of all sealed keys without exposing plaintext. |
| `/api/rotate-keys` | `POST` | The Panic Button. Instantly overwrites all Vault ciphertext with garbage. |
| `/api/health` | `GET` | Lightweight health probe. Returns `{"status": "ok", "version": "0.3.2"}` |
| `/api/settings` | `GET/POST` | Central config sync for UI sliders, routing modes, and logic gates. |
| `/api/stream` | `GET` | SSE endpoint. Pushes kinetic action updates to the dashboard. |

## 🗺️ Roadmap

**v0.4: The Transport Layer**
  - Upgrading the `ButterClawMCPServer` scaffold to full stdio/SSE Model Context Protocol (MCP) transport compliance.
  - Allowing the LLM to dynamically discover and select from an array of local tools beyond just key rotation and process termination.

-----

### License

MIT License. Copyright (c) 2026 butterclaw-tech. See [LICENSE](https://github.com/butterclaw-tech/butterclaw/blob/main/LICENSE) file for details.

-----

*Built with Python, Vanilla JS, and a whole lot of unautclated telemetry. Yes, unautclated.* 🦞
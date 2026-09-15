# Contributing to ButterClaw

First off, thank you for helping us secure the future of agentic AI! 🕶️🦞

---

## Where to Contribute

ButterClaw's architecture is organized as **The Exoskeleton** — six layered pillars, each with its own contribution surface. Pick the layer that matches your skills:

| Layer | Files | Good First Issues |
|---|---|---|
| **Kinetic Threat Signatures & Arsenal** | `default_signatures.json`, `capabilities.json`, `mcp_stdio_transport.json` | Add new regex patterns, update 4-tier RBAC matrix, adjust STDIO firewall limits |
| **Policy Engine (DRIFT)** | `policy_engine.py` | New operators, new context fields for pre_brain/post_brain/pre_tool scopes |
| **Alert Dispatcher** | `alert_dispatcher.py` | New channel types, new event types, delivery retry improvements |
| **Auth & RBAC** | `auth.py` | Rate limit improvements, session hardening, audit log coverage |
| **MCP Transport** | `butterclaw_mcp.py`, `mcp_transport.py` | New transport backends, tool allowlist improvements, Physical STDIO firewall |
| **Log Watcher** | `watcher.py` | Larger context window handling (128K+), inode tracking, retry queue |
| **TUI Dashboard** | `tui_dashboard.py` | Display improvements, new SOC panels, performance |
| **Config & Deployment** | `config.py`, `docker-compose.yml`, `systemd/` | New config fields, deployment targets |
| **Documentation** | `docs/`, `README.md` | Accuracy, coverage, examples |
| **Integration Testing** | `scripts/` | New test harnesses for `add_rule.py`, `test_attack.py`, and `test_mcp.py` workflows |

We are also actively seeking:
- **Security researchers** to help expand the OWASP ASI coverage and threat model
- **MCP co-maintainers** to help expand our MCP integrations and roadmap toward the v0.8.0 release (see [GOVERNANCE.md](GOVERNANCE.md))

---

## Development Setup

### Requirements
- Python 3.11+
- [Ollama](https://ollama.ai) installed and running on the host
- Docker + Docker Compose v2 (for container development)

### Local Setup

```bash
git clone [https://github.com/butterclaw-tech/butterclaw.git](https://github.com/butterclaw-tech/butterclaw.git)
cd butterclaw

pip install -r requirements.txt   # 7 dependencies — no extras needed

# Pull base model and build the ButterClaw-optimised variant
ollama pull gemma4:e4b
ollama create butterclaw-optimized -f Modelfile.example

cp .env.example .env
# Edit .env — set BUTTERCLAW_API_KEY at minimum

python server.py

```

### Docker Dev Stack

```bash
# Dev override disables nginx and ntfy, enables hot-reload and debug logging
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

```

### Running the Diagnostic Test Suites

Every major module ships a self-contained diagnostic suite. Run these before submitting a PR — they require no test framework, just Python:

```bash
python config.py           # 21 tests — configuration loading and validation
python auth.py             # 10 tests — HMAC keys, session tokens, RBAC
python policy_engine.py    # 16 tests — DRIFT rule evaluation, all 3 scopes
python alert_dispatcher.py # 14 tests — channel dispatch, event routing

```

**Note on Policy Engine Testing:** Running `python policy_engine.py` acts as the **Local Cognitive Test**. It loads both `default_signatures.json` (negative security) and `capabilities.json` (positive security) directly into memory to verify logic completely offline without touching the network.

All 61 tests must pass. If you add a new feature to any of these modules, add a corresponding test to the `__main__` block in that file.

### Live Fire Testing

Use the scripts in the `scripts/` directory to run full end-to-end integration tests against the live Docker container bridge and STDIO firewall:

```bash
# Inject a test signature into the Arsenal and fire a simulated attack
python scripts/add_rule.py
python scripts/test_attack.py

# Fire the Live Kinetic Test payload automatically through the Nginx gateway
python scripts/test_mcp.py

```

---

## Pull Request Process

1. **Open an Issue first** — before starting any non-trivial change, open an issue to discuss the approach. This prevents duplicate effort and keeps architecture decisions traceable.
2. **Branch from `main**` — create a feature branch: `git checkout -b feature/your-feature-name`
3. **Run all diagnostic suites** — all 61 tests across the four modules must pass. If your change touches the watcher, also verify inode tracking and retry queue behaviour manually.
4. **Add or update tests** — if you add a new operator to `policy_engine.py`, a new channel type to `alert_dispatcher.py`, or a new config field to `config.py`, add a corresponding diagnostic test to that module's `__main__` block.
5. **Update documentation** — if your change affects any public surface (API endpoints, config fields, RBAC roles, policy operators, alert channels), update the relevant file in `docs/`. The four docs are cross-linked and must stay consistent with each other.
6. **Submit a PR** — write a clear description that identifies the "behavioral gap" your code addresses. Reference the ASI threat category if applicable (ASI-01 through ASI-10).

---

## Security Policy

**Do not report security vulnerabilities via public issues.** If you discover a vulnerability in ButterClaw itself, use GitHub's **Private Vulnerability Reporting** feature.

Navigate to the **Security** tab of this repository and click **"Report a vulnerability"** to initiate a coordinated, encrypted disclosure process.

See [SECURITY.md](docs/SECURITY.md) for the full threat model, known attack surfaces, and ASI coverage map.

---

## Code of Conduct

ButterClaw follows the standard Linux Foundation / AAIF Code of Conduct. Be excellent to each other.

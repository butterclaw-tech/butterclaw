# Contributing to ButterClaw

First off, thank you for helping us secure the future of agentic AI! 🕶️🦞

---

## Where to Contribute

ButterClaw's architecture is organized as **The Exoskeleton** — layered defense pillars under `src/butterclaw/`, each with its own contribution surface. Pick the layer that matches your skills:

| Layer | Files | Good First Issues |
|---|---|---|
| **SkillGuard Supply-Chain Defense (v0.9.3)** | `src/butterclaw/skill_guard.py`, `tests/test_skill_guard.py`, `scripts/seed_test_skills.py` | New AST/steganography detectors, semantic skill drift checks, Gate M5/M10 test vectors |
| **Fleet Layer & Multi-Agent Trust (v0.9.0)** | `src/butterclaw/fleet_*.py`, `src/butterclaw/trust_graph.py`, `src/butterclaw/correlation_engine.py`, `src/butterclaw/collusion_detector.py`, `src/butterclaw/hemisphere_scheduler.py` | Cross-agent correlation heuristics, trust-graph visualization, federated indicator exchange |
| **Memory & Cognitive Hemispheres (v0.8.0–v0.9.2)** | `src/butterclaw/memory_engine.py`, `src/butterclaw/dream_engine.py`, `src/butterclaw/loop_engine.py`, `src/butterclaw/memory_api.py` | Timed-daemon cooperative shutdown (`R4`–`R7`), shadow evaluator adapters, spatial heuristics |
| **Kinetic Threat Signatures & Arsenal** | `default_signatures.json`, `capabilities.json`, `mcp_stdio_transport.json` | Add sanitizer-aware regex patterns (`collusion_role` tags), update 4-tier RBAC matrix, adjust STDIO firewall limits |
| **Policy Engine (DRIFT)** | `src/butterclaw/policy_engine.py` | New operators, new context fields for `pre_brain` / `post_brain` / `pre_tool` scopes |
| **Alert Dispatcher** | `src/butterclaw/alert_dispatcher.py` | New channel types, new event types, delivery retry improvements |
| **Auth & RBAC** | `src/butterclaw/auth.py` | Rate limit improvements, session hardening, audit log coverage |
| **MCP Transport & Execution** | `src/butterclaw/butterclaw_mcp.py`, `src/butterclaw/mcp_transport.py` | New MCP tools, transport backends, Gate M5 capability binding, Physical STDIO firewall |
| **Log Watcher** | `src/butterclaw/watcher.py` | Larger context window handling (128K+), inode tracking, retry queue |
| **TUI & Web Dashboards** | `src/butterclaw/tui_dashboard.py`, `index.html`, `routing.html` | Display improvements, new SOC panels, dark-mode polish |
| **Config & Deployment** | `src/butterclaw/config.py`, `src/butterclaw/setup_wizard.py`, `docker-compose.yml`, `systemd/` | New 12-Factor config fields, wizard sections, deployment targets |
| **Documentation** | `docs/`, `README.md` | Accuracy, coverage, examples |
| **Integration Testing** | `scripts/`, `tests/` | New test harnesses for `add_rule.py`, `test_attack.py`, `test_mcp.py`, `test_spatial.py`, and `seed_test_skills.py` workflows |

We are also actively seeking:
- **Security researchers** to help expand our OWASP ASI coverage, `SKILL.md` supply-chain rules, and threat model
- **MCP & Multi-Agent co-maintainers** to help expand our MCP integrations, fleet trust graph, and federation roadmap toward `v0.9.4` and `v1.0` (see [GOVERNANCE.md](GOVERNANCE.md))

---

## Development Setup

### Requirements
- Python 3.11+
- [Ollama](https://ollama.com) installed and running on the host *(optional if testing deterministic Arsenal / SkillGuard layers)*
- Docker + Docker Compose v2 (for container development)

### Local Setup

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw

# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate

# 2. Install ButterClaw in editable mode with dev/test dependencies (resolves from pyproject.toml)
pip install -e ".[dev]"

# 3. Pull base model and build the ButterClaw-optimised variant
ollama pull gemma4:e4b
ollama create butterclaw-optimized -f Modelfile.example

# 4. Configure environment interactively (or copy .env.example -> .env)
python -m butterclaw.setup_wizard

# 5. Launch the application as a Python module
python -m butterclaw.server
```

### Docker Dev Stack

```bash
# Dev override disables nginx and ntfy, enables hot-reload and debug logging
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Running the Diagnostic & Unit Test Suites

Every core module ships a self-contained diagnostic suite, complemented by unit suites under `tests/`. Run these before submitting a PR:

```bash
# Self-contained module diagnostic suites (63 assertions total)
python -m butterclaw.config           # 23 tests — configuration loading, validation & SkillGuard settings
python -m butterclaw.auth             # 10 tests — HMAC keys, session tokens, RBAC
python -m butterclaw.policy_engine    # 16 tests — DRIFT rule evaluation, Arsenal loader, all 3 scopes
python -m butterclaw.alert_dispatcher # 14 tests — channel dispatch, event routing

# Unit & Supply-Chain suites (SkillGuard Gate M5/M10, Fleet DB isolation & lenient Arsenal loader)
python -m unittest tests/test_skill_guard.py -v   # 7 tests — AST/stego quarantine, TOCTOU Merkle & Gate M10
pytest                                            # Runs full pytest suite under tests/
```

**Note on Policy Engine Testing:** Running `python -m butterclaw.policy_engine` acts as the **Local Cognitive Test**. It loads both `default_signatures.json` (negative security) and `capabilities.json` (positive security) directly into memory to verify logic completely offline without touching the network.

All **63 module diagnostic tests** plus the **`tests/` unit suites** must pass. If you add a new feature to any of these modules, add a corresponding test to the `__main__` block in that file or under `tests/`.

---

> *Note: Always execute these scripts from the root of the repository so the package configuration can correctly locate your local `.env` file and database.*

### Live Fire Testing

Use the scripts in the `scripts/` directory to run full end-to-end integration tests against the live Docker container bridge, STDIO firewall, and SkillGuard auditor:

```bash
# 1. Inject custom test signature into the live engine
python scripts/add_rule.py

# 2. Fire the simulated attack suite against the Arsenal (25/25 vectors)
python scripts/test_attack.py

# 3. Run a live kinetic integration test against the STDIO physical firewall
python scripts/test_mcp.py

# 4. Fire raw computer-use primitives against the Spatial Telemetry Gateway
python scripts/test_spatial.py

# 5. Validate the v0.8.0 Dual Memory Substrate & Four-Hemisphere Cognition
python scripts/test_dual_memory.py

# 6. Seed synthetic SKILL.md fixtures & run the containerized SkillGuard suite (v0.9.3)
python scripts/seed_test_skills.py
./dash.sh test   # or .\dash.bat test on Windows
```

---

## Pull Request Process

1. **Open an Issue first** — before starting any non-trivial change, open an issue to discuss the approach. This prevents duplicate effort and keeps architecture decisions traceable.
2. **Branch from `main`** — create a feature branch: `git checkout -b feature/your-feature-name`
3. **Run all diagnostic & unit suites** — all 63 tests across the four core modules plus `tests/test_skill_guard.py` and `pytest` must pass. If your change touches the watcher, also verify inode tracking and retry queue behaviour manually.
4. **Add or update tests** — if you add a new operator to `policy_engine.py`, a new channel type to `alert_dispatcher.py`, a new detector to `skill_guard.py`, or a new config field to `config.py`, add a corresponding test.
5. **Update documentation** — if your change affects any public surface (API endpoints, config fields, RBAC roles, policy operators, alert channels, SkillGuard gates), update the relevant file in `docs/`. The docs are cross-linked and must stay consistent with each other.
6. **Submit a PR** — write a clear description that identifies the "behavioral gap" your code addresses. Reference the ASI threat category if applicable (`ASI-01` through `ASI-10`).

---

## Security Policy

**Do not report security vulnerabilities via public issues.** If you discover a vulnerability in ButterClaw itself, use GitHub's **Private Vulnerability Reporting** feature.

Navigate to the **Security** tab of this repository and click **"Report a vulnerability"** to initiate a coordinated, encrypted disclosure process.

See [`docs/SECURITY.md`](docs/SECURITY.md) for the full threat model, known attack surfaces, and ASI coverage map.

---

## Code of Conduct

ButterClaw follows the standard Linux Foundation / AAIF Code of Conduct. Be excellent to each other.

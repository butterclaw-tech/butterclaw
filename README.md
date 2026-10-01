<div align="center">
<pre>
██████╗ ██╗   ██╗████████╗████████╗███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
██╔══██╗██║   ██║╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
██████╔╝██║   ██║   ██║      ██║   █████╗  ██████╔╝██║     ██║     ███████║██║ █╗ ██║
██╔══██╗██║   ██║   ██║      ██║   ██╔══╝  ██╔══██╗██║     ██║     ██╔══██║██║███╗██║
██████╔╝╚██████╔╝   ██║      ██║   ███████╗██║  ██║╚██████╗███████╗██║  ██║╚███╔███╔╝
╚═════╝  ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
</pre>
</div>

<h1 align="center">ButterClaw: The Agentic SOC</h1>

<p align="center"><b>Runtime security enforcement for autonomous AI agents.</b><br>Local LLM reasoning. Persistent Memory. No outbound telemetry. SIGKILLs rogue processes.</p>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0">
  <img src="https://img.shields.io/badge/License-Apache_2.0-ef4444.svg">
  </a>
  <a href="CHANGELOG.md">
  <img src="https://img.shields.io/badge/version-0.8.1-navy.svg">
  </a>
  <a href="https://butterclaw.tech">
  <img src="https://img.shields.io/badge/Live-butterclaw.tech-eab308.svg">
  </a>
</p>

<p align="center">
  <img src="assets/setup_wizard.png" alt="ButterClaw Environment CLI Setup Wizard">
</p>

<p align="center">
  <img src="assets/bc_demo-small.gif" alt="ButterClaw Live-Fire Test gif">
</p>

<p align="center">Regex signatures test against the policy engine, displayed live in the TUI and WebUI.</p>

<p align="center">
  <img src="assets/test-event-stream.png" alt="ButterClaw Live-Fire Test Screenshot">
</p>

<p align="center">
  <img src="assets/butterclaw-log.png" alt="ButterClaw Live WebUI">
</p>

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized **Four-Hemisphere Reasoning Engine** to catch obfuscated prompt injections, CSWH attacks, and spatial anomalies. Featuring the **Unified Memory Substrate** that learns across sessions, and the **ButterVault**: a zero-trust credential locker that physically shreds your API keys into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry and computer-use spatial primitives.

---

> **Not affiliated with** `butterclaw.ai`, OpenClaw, or any OpenClaw forks.
> ButterClaw Tech has its own architecture, runtime, and execution semantics.
> Looking for a hosted agent framework? → [`butterclaw.ai`](https://butterclaw.ai) or OpenClaw.
> Looking for a local-first kinetic security layer? → You're here.

---

## How It Works

```text
Incoming telemetry / log / tool call
         │
         ▼
┌─────────────────────────┐
│  Spatial SOC (v0.8.0)   │  ← High-frequency spatial primitive interception
│  /api/spatial/telemetry │    Fast-path Cold Memory Signature matches O(1)
└────────────┬────────────┘
             │ no signature match
             ▼
┌─────────────────────────┐
│  Arsenal (pre_brain)    │  ← 7 regex signatures, deterministic evaluation
│  sig_kin_01, sig_cswh_01│    SIGKILL or BLOCK on match — LLM never called
└────────────┬────────────┘
             │ no match
             ▼
┌─────────────────────────┐
│  Four-Hemisphere Logic  │  ← 1. Guardian Brain (0.3) - Evaluate & Act
│  (Unified Memory)       │    2. Auditor (0.0) - False-Positive Check
│                         │    3. Dream Weaver (0.7) - Idle Consolidation
│                         │    4. Loop Proposer (0.4) - Autoresearch & Mutate
└────────────┬────────────┘
             │ tool execution requested
             ▼
┌─────────────────────────┐
│  Capability Matrix      │  ← Positive Security: 4-Tier Agent RBAC & tool scopes
│  (pre_tool gate)        │    STDIO Physical Firewall (byte-level memory boundary)
└────────────┬────────────┘
             │ CRITICAL verdict
             ▼
┌─────────────────────────┐
│  Kinetic Response       │  ← SIGKILL rogue process via Topology Manager Lineage
│  + Alert Dispatch       │    Gibson Vault Shred | ntfy / Discord / SMTP
└─────────────────────────┘

```

Everything runs on your machine. SQLite for state. No outbound data.

---

## How It Compares

|  | ButterClaw | Halo | LangSmith / LangFuse | Traditional WAF / IDS |
| --- | --- | --- | --- | --- |
| **Deployment** | Self-hosted, local | Cloud-hosted | Cloud-hosted | Self-hosted |
| **LLM reasoning** | Local Ollama / Remote | Cloud API calls | None | None |
| **Telemetry** | Zero — SQLite only, no outbound data | Sent to Halo cloud | Sent to vendor cloud | Network-layer only |
| **Persistent Memory** | ✅ Deep + Surface Tiers (HOT/WARM/COLD) | ❌ | ❌ | ❌ |
| **Autoresearch Loop** | ✅ Shadow evaluation & proposal engine | ❌ | ❌ | ❌ |
| **What it monitors** | Spatial primitives + MCP chain + OS logs | LLM API calls | LLM traces and spans | Network traffic |
| **Pre-LLM gate** | ✅ Arsenal — 7 regex signatures fire first | ❌ | ❌ | ❌ |
| **Verdict mechanism** | Four-Hemisphere (Action, Audit, Dream, Loop) | Single pass | Logging only | Rule-based |
| **Positive Security** | ✅ Capability Matrix — 4-tier Agent RBAC | ❌ | ❌ | ❌ |
| **Kinetic response** | ✅ SIGKILL rogue process tree | ❌ Alert only | ❌ | ❌ Alert / block |
| **Credential shredding** | ✅ Active HTTP revocation + local vault wipe | ❌ | ❌ | ❌ |
| **Physical I/O boundary** | ✅ Byte-level STDIO memory firewall | ❌ | ❌ | Varies |
| **License** | Apache 2.0 | Proprietary | Apache 2.0 | Varies |

---

## The Arsenal — 7 Signatures

All 7 patterns are sanitizer-aware and validated against raw and stripped engine inputs.

| ID | Name | Severity | Scope | Response |
| --- | --- | --- | --- | --- |
| `sig_cswh_01` | CSWH WebSocket Port Scanning | 🔴 CRITICAL | pre_brain | SIGKILL |
| `sig_exfil_01` | Credential Exfiltration via Network Tool | 🔴 CRITICAL | pre_brain | SIGKILL |
| `sig_exfil_02` | Base64 Exfiltration Pipeline | 🟡 WARNING | pre_brain | BLOCK |
| `sig_inj_01` | System Prompt Override / Jailbreak | 🟡 WARNING | pre_brain | BLOCK |
| `sig_kin_01` | Reverse Shell Indicators | 🔴 CRITICAL | pre_brain | SIGKILL |
| `sig_exfil_03` | Cloud Metadata Service Probe | 🔴 CRITICAL | pre_tool | SIGKILL |
| `sig_kin_02` | Persistence Mechanism Injection | 🔴 CRITICAL | pre_brain | SIGKILL |

---

## Quick Start

Requires: [Docker](https://docs.docker.com/get-docker/) · Python 3.8+ · (Optional) [Ollama](https://ollama.com/) running on the host

```bash
git clone [https://github.com/butterclaw-tech/butterclaw.git](https://github.com/butterclaw-tech/butterclaw.git)
cd butterclaw

# 1. Install ButterClaw in editable mode
pip install -e .

# 2. Run the Interactive Wizard (Auto-generates your .env and infrastructure keys)
python -m butterclaw.setup_wizard

# 3. Ignite the Exoskeleton (if deploying via Docker)
docker compose up -d --build

# 4. Launch the live TUI dashboard
./dash

```

Dashboard → **https://localhost** · ntfy UI → **http://localhost:2586**

→ Full deployment guide (systemd, bare-metal, TLS): [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

---

## 🧪 Live-Fire Test Suite

ButterClaw ships with a complete Blue Team integration suite to safely simulate attacks against the active API gateway.

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

```

### Running `test_spatial.py`

A targeted diagnostic for the v0.8.0 Spatial SOC. It fires raw computer-use primitives (clicks, typing) directly at the telemetry gateway to validate the spatial heuristics engine. It proves the system can successfully ignore a benign mouse click while instantly throwing a `403 FORBIDDEN` and triggering the Watcher Daemon on a malicious Powershell execution trajectory.

### Running `test_dual_memory.py`

This test validates ButterClaw's continuous learning architecture without requiring manual token entry. It actively tests the Surface Memory (Live Crystallization), the Dream Weaver, and the Loop Proposer.

**How to run it:**

1. Ensure your Docker container is online (`docker compose up -d --build`).
2. Run `python scripts/test_dual_memory.py`.
3. **Frictionless Auth:** The script automatically crawls to your project root, parses your `.env` file, extracts your `BUTTERCLAW_API_KEY`, and bypasses local Nginx SSL warnings to communicate with the HTTPS backend.

**What it tests:**

* **Phase 1 (Surface Memory):** Fires a highly-kinetic spatial payload (Powershell execution) four times to simulate a sustained agent compromise. Validates that the system instantly blacklists the zero-day spatial pattern into Cold Memory via the 3-strike `Live Crystallization` rule.
* **Phase 2 (Dream Weaver):** Manually triggers a REM cycle. Validates that the background daemon ages your WARM memory via the maturation tick and successfully synthesizes speculative threats, storing them as `[DREAM-PRIMED]` in the Hot Cache.
* **Phase 3 (Loop Proposer):** Safely injects a `tools/call` baseline into the ledger by momentarily escalating the Paranoia dial and utilizing a temporary policy to bypass LLM compute (saving cloud API quotas). Triggers the Karpathy autoresearch loop, verifying the shadow evaluator runs a side-effect-free scoring cycle against history without improperly mutating production rules.

---

## Key Features

* **Four-Hemisphere Cognition (v0.8.0)** — Action (`0.3`), Audit (`0.0`), Dream (`0.7`), and Loop (`0.4`). Separated LLM reasoning passes ensure the system isn't forcing one prompt to act as an enforcer, a skeptic, and a researcher simultaneously.
* **Unified Memory Substrate (v0.8.0)** — HOT (RAM deque), WARM (Episodic SQLite), and COLD (Semantic entity graph + Cold Signatures) tiers track agent behavior across sessions, building institutional memory of successful defenses.
* **Capability Matrix (Positive Security Model)** — Localized 4-tier IAM role hierarchy (`infrastructure`, `admin`, `operator`, `viewer`) mapping agents to allowed tool scopes.
* **STDIO Physical Firewall** — Enforces a strict byte-level memory boundary (`max_payload_bytes`), auto pipe draining, and strict UTF-8 decoding on the local process transport to prevent buffer poisoning.
* **The Paranoia Dial** — Level 1 (Observe), Level 2 (SIGKILL), Level 3 (SIGKILL + vault shred). Switch at runtime without restart.
* **ButterVault + Gibson Kill Switch** — Fernet-encrypted credential vault. On compromise: fires live HTTP DELETE/POST to GitHub to invalidate tokens globally, then shreds local data atomically.
* **Deterministic Policy Engine** — 3-scope pipeline (pre-brain / post-brain / pre-tool), 15 safe operators, no `eval()`. Implements the DRIFT framework pattern.
* **6 Alert Channels** — ntfy (self-hosted), Discord, Telegram, SMTP, Webhook (HMAC-SHA256 signed), Gotify. Fires before any kinetic action.
* **4-Tier User RBAC** — HMAC-SHA256 API keys and session tokens for dashboard access.
* **63 API routes** — full programmatic control over every subsystem including memory manipulation. → [`docs/API.md`](docs/API.md)

---

## Documentation

| Doc | Contents |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Four-hemisphere reasoning, 3-tier memory model, invariants D-01 through D-19 |
| [`docs/API.md`](docs/API.md) | All 63 endpoints, roles, request/response shapes, memory routes |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker, systemd, bare-metal, nginx TLS, backup/restore |
| [`docs/SECURITY.md`](docs/SECURITY.md) | OWASP ASI mapping, threat model |
| [`CHANGELOG.md`](CHANGELOG.md) | Full version history from v0.1.0 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Architecture decision process, PR requirements |

---

## Contributing & Co-Maintainers

ButterClaw is applying for the **Agentic AI Foundation (AAIF) Growth Stage** and is actively seeking security-focused co-maintainers — particularly those working with the **Model Context Protocol (MCP)** — to help scale the stdio transport layer. Grab a `good first issue` or read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`GOVERNANCE.md`](GOVERNANCE.md).

## 🤝 Community Contributors
Contributors who ship features get credited here - not just in the git log.

**Telegram Alert Channel** - Native Telegram Bot API support added to the Alert Dispatcher. Operators can route SOC alerts to mobile with 🔴/🟡/🟢 severity formatting and automatic 4096-char payload enforcement. 
<p align="center">
(Contributed by @huanghaiyss)<br></p>

If you ship something that lands, your name goes here. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) to get started.

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).

ButterClaw Tech © 2026

---

<p align="center">
<strong>🦞 ButterClaw v0.8.1 — The Agentic SOC (Dual Memory Engine - src Layout) 🦞</strong><br>
<em>Deterministic guardrails for probabilistic reasoning. Evaluation before execution.</em><br>
<em>The Sentinel never goes silent. We watch the room.</em><br>
<a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>
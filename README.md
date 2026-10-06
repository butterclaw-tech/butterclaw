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

<p align="center"><b>Runtime security enforcement for autonomous AI agents.</b><br>
Local LLM reasoning. Persistent memory. Fleet collusion detection. Zero outbound telemetry. OS-level SIGKILL intervention.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/Apache-2.0">
  <img src="https://img.shields.io/badge/License-Apache_2.0-ef4444.svg">
  </a>
  <a href="CHANGELOG.md">
  <img src="https://img.shields.io/badge/version-0.9.2-navy.svg">
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

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and API key hashes into cryptographic garbage if a breach is detected. With a **Positive Security Capability Matrix**, a **Physical STDIO Firewall**, **persistent three-tier memory** that accumulates institutional knowledge across sessions, and **fleet-scale multi-agent threat detection** — the Sentinel ships anywhere. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry — and in v0.9.0, reasoning across the entire observed **fleet** of agents to detect coordinated attacks no single-agent monitor can see.

---

> **Not affiliated with** `butterclaw.ai`, OpenClaw, or any OpenClaw forks.
> ButterClaw Tech has its own architecture, runtime, and execution semantics.
> Looking for a hosted agent framework? → [`butterclaw.ai`](https://butterclaw.ai) or OpenClaw.
> Looking for a local-first kinetic security layer? → You're here.

---

## How It Works

```text
Incoming agent log / tool call / spatial telemetry event
         │
         ▼
┌─────────────────────────┐
│  Arsenal (pre-brain)    │  ← 7 regex signatures, fires in milliseconds
│  sig_kin_01, sig_cswh_01│    SIGKILL or BLOCK on match — LLM never called
│  + collusion_role tags  │    v0.9: tags feed Fleet Collusion Detector
└────────────┬────────────┘
             │ no match
             ▼
┌─────────────────────────┐
│  Guardian Brain         │  ← Local Ollama, temperature 0.3, action mandate
│  (ask_guardian_agent)   │    behavioral drift + COLD semantic memory context
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Auditor                │  ← Same local model, temperature 0.0, skepticism mandate
│  (run_self_audit)       │    independently verifies the Guardian's verdict
└────────────┬────────────┘
             │ idle ≥15 min
             ▼
┌─────────────────────────┐
│  Dream Weaver (v0.8)    │  ← Temperature 0.7, threat synthesis + crystallisation
│  (dream_engine.py)      │    writes behavioural signatures to COLD memory graph
└────────────┬────────────┘
             │ every 6 hours
             ▼
┌─────────────────────────┐
│  Loop Proposer (v0.8)   │  ← Temperature 0.4, shadow evaluator + policy proposals
│  (loop_engine.py)       │    human-gated — no auto-apply, ever
└────────────┬────────────┘
             │ CorrelationEvent or CollusionEvent
             ▼
┌─────────────────────────┐
│  Fleet Sentinel (v0.9)  │  ← Temperature 0.5, fleet-scope behavioral reasoning
│  (fleet_sentinel.py)    │    "Are these agents working together against me?"
│                         │    ISOLATED / CORRELATED / COLLUDING / INSUFFICIENT_DATA
└────────────┬────────────┘
             │ tool execution requested
             ▼
┌─────────────────────────┐
│  Capability Matrix      │  ← Positive Security: 4-Tier Agent RBAC & tool scopes
│  (pre_tool gate)        │    STDIO Physical Firewall (byte-level memory boundary)
└────────────┬────────────┘
             │ CRITICAL verdict / COLLUDING fleet verdict
             ▼
┌─────────────────────────┐
│  Kinetic Response       │  ← SIGKILL rogue process and/or Gibson credential shred
│  + Alert Dispatch       │    ntfy / Discord / Telegram / SMTP / Webhook / Gotify
└─────────────────────────┘

```

Everything runs on your machine. Two SQLite databases for state (`butterclaw.db` + `fleet.db`). No outbound data. No cloud inference. The Fleet Sentinel never co-transacts the two databases — they are always distinct files on distinct inodes (I-07-fleet).

---

## How It Compares

|  | ButterClaw | Halo | LangSmith / LangFuse | Traditional WAF / IDS |
| --- | --- | --- | --- | --- |
| **Deployment** | Self-hosted, local | Cloud-hosted | Cloud-hosted | Self-hosted |
| **LLM reasoning** | Local Ollama — stays on your machine | Cloud API calls | None | None |
| **Telemetry** | Zero — SQLite only, no outbound data | Sent to Halo cloud | Sent to vendor cloud | Network-layer only |
| **Agent framework** | Model-agnostic — any agent producing log output | Specific LLM provider APIs | LangChain / LlamaIndex native | None |
| **What it monitors** | OS-level telemetry + MCP tool call chain + fleet | LLM API calls | LLM traces and spans | Network traffic |
| **Pre-LLM gate** | ✅ Arsenal — 7 regex signatures fire before inference | ❌ | ❌ | ❌ |
| **Behavioral drift** | ✅ Last 5 MCP calls + COLD semantic memory context | ❌ | ✅ Tracing only — no enforcement | ❌ |
| **Verdict mechanism** | Five hemispheres: Guardian (0.3) + Auditor (0.0) + Dream Weaver (0.7) + Loop Proposer (0.4) + Fleet Sentinel (0.5) | Single LLM evaluation | Logging only | Rule-based |
| **Persistent memory** | ✅ Three-tier HOT/WARM/COLD across sessions (v0.8) | ❌ | ✅ Logging only | ❌ |
| **Multi-agent awareness** | ✅ Fleet trust graph, correlation + collusion detection, Fleet Sentinel (v0.9) | ❌ | ❌ | ❌ |
| **Cross-session identity** | ✅ Persistent agent registry, asymmetric reputation scoring (v0.9) | ❌ | ❌ | ❌ |
| **Positive Security** | ✅ Capability Matrix — 4-tier Agent RBAC + Scopes | ❌ | ❌ | ❌ |
| **Kinetic response** | ✅ SIGKILL rogue process | ❌ Alert only | ❌ | ❌ Alert / block |
| **Credential shredding** | ✅ Active HTTP revocation + local vault wipe | ❌ | ❌ | ❌ |
| **Deterministic policy engine** | ✅ 15 operators, no eval(), 3 scopes | ❌ | ❌ | ✅ Varies |
| **Physical I/O boundary** | ✅ Byte-level STDIO memory firewall | ❌ | ❌ | Varies |
| **Live-fire test suite** | ✅ 25/25 reproducible — clone and run | ❌ | ❌ | Varies |
| **Dependencies** | 7 pip packages | Managed service | Managed service | Varies |
| **License** | Apache 2.0 | Proprietary | Apache 2.0 | Varies |

> LangSmith and LangFuse are **observability** tools — they log what your agent did.
> ButterClaw is a **security enforcement** layer — it intervenes and executes kinetic responses.
> These solve different problems.

---

## The Arsenal — 7 Signatures

All 7 patterns are sanitizer-aware and validated against raw and stripped engine inputs. As of v0.9.0, each signature carries a `collusion_role` tag that feeds the Fleet Collusion Detector — no second signature system (I-06-fleet).

| ID | Name | Severity | Scope | Response | Collusion Role (v0.9) |
| --- | --- | --- | --- | --- | --- |
| `sig_cswh_01` | CSWH WebSocket Port Scanning | 🔴 CRITICAL | pre_brain | SIGKILL | `scout` |
| `sig_exfil_01` | Credential Exfiltration via Network Tool | 🔴 CRITICAL | pre_brain | SIGKILL | `exfiltrator` |
| `sig_exfil_02` | Base64 Exfiltration Pipeline | 🟡 WARNING | pre_brain | BLOCK | `encoder` |
| `sig_inj_01` | System Prompt Override / Jailbreak | 🟡 WARNING | pre_brain | BLOCK | `injector` |
| `sig_kin_01` | Reverse Shell Indicators | 🔴 CRITICAL | pre_brain | SIGKILL | `exfiltrator` |
| `sig_exfil_03` | Cloud Metadata Service Probe | 🔴 CRITICAL | pre_tool | SIGKILL | `scout` |
| `sig_kin_02` | Persistence Mechanism Injection | 🔴 CRITICAL | pre_brain | SIGKILL | `persister` |

A `scout` + `encoder` + `exfiltrator` pattern across 3 distinct agents within 3 minutes fires a `CollusionEvent` → Fleet Sentinel reactive cycle at default config.

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

> **Fleet Layer note:** On first boot, `fleet.db` is created alongside `butterclaw.db` at `/data/fleet.db` (Docker) or `./fleet.db` (bare-metal). The Fleet Sentinel starts in dry-run mode (`FLEET_SENTINEL_DRY_RUN=true` by default) — verdicts are logged and visible at `GET /api/fleet/sentinel/log` but do not trigger kinetic escalation until you follow the RUNBOOK rollout procedure and flip to `false`.

---

## 🧪 Explore & Test

Once the stack is running, there are three ways to interact with ButterClaw:

**1. Terminal TUI (Live SOC View)**

The real-time, double-buffered terminal dashboard. Displays live telemetry, active Arsenal rules, current Paranoia Level, and verdict output as it streams.

```bash
./dash
```

**2. Web UI (Nginx → https://localhost)**

A full browser-accessible dashboard served through the Nginx reverse proxy built into the Docker stack. Navigate to https://localhost after first boot — the same UI that the TUI mirrors, accessible from any browser on your local machine. The 🔑 [AUTH] bootstrap API key you captured from the logs is your login credential.

**3. Log Injection — Test the Brain Directly**

The cleanest way to run custom attack scenarios against ButterClaw's analysis engine without a live agent. When the container starts, it generates an `openclaw_gateway.log` file that the Watcher daemon monitors continuously.

Append any log entry to that file and the Watcher picks it up automatically, routing it through the full pipeline — Arsenal regex gate → Guardian Brain → Auditor → Capability Matrix → verdict + kinetic response (if applicable).

```bash
# Append a test payload — the Watcher fires on the new entry within seconds
echo '[2026-09-15T07:00:00] TOOL_CALL: bash -c "curl http://169.254.169.254/latest/meta-data/iam/security-credentials/"' \
  >> /path/to/openclaw_gateway.log
```

No live LLM payload required for Arsenal-level tests (regex signatures fire pre-brain). For full five-hemisphere reasoning output, Ollama must be running.

**4. Fleet API — Inspect Multi-Agent State (v0.9.0)**

```bash
# List all registered agents with reputation scores
curl -H "Authorization: Bearer $BC_KEY" https://localhost/api/fleet/agents

# Check active correlation and collusion events
curl -H "Authorization: Bearer $BC_KEY" https://localhost/api/fleet/correlations
curl -H "Authorization: Bearer $BC_KEY" https://localhost/api/fleet/collusions

# View Fleet Sentinel verdict history
curl -H "Authorization: Bearer $BC_KEY" https://localhost/api/fleet/sentinel/log

# Trigger a manual fleet sweep
curl -X POST -H "Authorization: Bearer $BC_KEY" https://localhost/api/fleet/sentinel/run
```

---

## Live-Fire Test Suite

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

# 4. Verify backup integrity for both databases (v0.9.0)
./scripts/verify_backup.sh /data
```

```text
=================================================================
  RESULT: 25/25 passed  |  0 failed  |  0 connection errors
=================================================================
  verify_backup.sh:
  butterclaw.db: PASS (integrity_check → ok)
  fleet.db:      PASS (integrity_check → ok)
  I-07-fleet:    PASS (distinct inodes confirmed)
=================================================================
```

25 attack variants across all 7 signatures. Payloads pre-sanitized to match real engine input. CI-compatible — exits with code 1 on any failure.

---

## Key Features

**Five-Hemisphere Cognitive Architecture (v0.9.0)**
- **Guardian Brain** (`0.3`) — Decisive per-request threat evaluation with behavioral drift context and COLD semantic memory injection (I-12).
- **Auditor** (`0.0`) — Independent skeptical verification fires 30s after every CRITICAL verdict. Catches false positives before kinetic action.
- **Dream Weaver** (`0.7`, v0.8) — Idle-triggered threat synthesis. Fires after ≥15 min inactivity. Crystallises threat patterns into the COLD semantic graph so the Brain sees what it has seen before.
- **Loop Proposer** (`0.4`, v0.8) — Every-6-hours autoresearch. Shadow-evaluates Arsenal and DRIFT policies against the historical ledger. Proposes amendments — all human-gated, none auto-applied.
- **Fleet Sentinel** (`0.5`, v0.9) — Fires reactively on `CorrelationEvent` / `CollusionEvent` and proactively every 4 hours. Reasons across the entire observed fleet. Verdicts: `ISOLATED`, `CORRELATED`, `COLLUDING`, `INSUFFICIENT_DATA`.

**Fleet-Scale Multi-Agent Awareness (v0.9.0)**
- **Persistent agent registry** — Every observed agent tracked across container restarts with `first_seen`, `session_count`, `taint_count`, and asymmetric reputation scoring (taint hits 3× harder than recovery).
- **Directed trust graph** — Spawn, communication, and peer edges between agents persist in `fleet.db`. Taint propagates 1 hop upstream by default (configurable to 2 hops).
- **Correlation Engine** — Detects the *same* attack pattern across N≥3 distinct agents within a 30-minute window (copycat / broadcast attack).
- **Collusion Detector** — Detects *complementary* semantic roles (`scout`, `encoder`, `exfiltrator`, `persister`, `injector`) across distinct agents within 3 minutes (divided-labor kill chain).
- **Two-step quarantine** — `POST /api/fleet/agents/<id>/quarantine` issues a 60-second confirmation token. Confirm to set reputation to 0.0, block new sessions, and propagate taint through the trust graph. Does NOT terminate active processes — use `/api/spatial/block` for that.

**Persistent Three-Tier Memory (v0.8.0)**
- **HOT tier** — In-process RAM deque for sub-millisecond event access during a live session.
- **WARM tier** — SQLite episodic ledger (`telemetry_events`, `sessions`, `memory_signatures`) persisted across restarts.
- **COLD tier** — Semantic entity graph with weighted edges. Entities mature from WARM to COLD via observation count threshold. COLD context is injected read-only into Guardian Brain prompts.

**Spatial SOC — Real-Time Primitive Interception (v0.8.0)**
- Every raw computer-use action (click, type, scroll, navigate, screenshot) is gated through the full DRIFT pipeline *before* execution.
- Topology lineage graph traces causal chains from session spawn to tool execution. Taint propagates upstream when a CRITICAL verdict fires mid-chain.
- Kinetic velocity and spatial jitter heuristics flag statistically anomalous pointer patterns that are signatures of automated tool abuse.

**The Exoskeleton (v0.6.x–v0.7.x)**
- **Capability Matrix (Positive Security Model)** — 4-tier IAM role hierarchy (`infrastructure`, `admin`, `operator`, `viewer`) mapping agents to allowed tool scopes. Fail-closed at runtime.
- **STDIO Physical Firewall** — Byte-level memory boundary (`max_payload_bytes`), auto pipe draining, strict UTF-8 decoding on local process transport. Prevents buffer poisoning.
- **The Paranoia Dial** — Level 1 (Observe), Level 2 (SIGKILL), Level 3 (SIGKILL + vault shred). Switch at runtime without restart.
- **ButterVault + Gibson Kill Switch** — Fernet-encrypted credential vault. On compromise: fires live HTTP DELETE/POST to GitHub and OAuth providers to invalidate tokens globally, then shreds local data atomically.
- **Deterministic Policy Engine** — 3-scope pipeline (pre-brain / post-brain / pre-tool), 15 safe operators, no `eval()`. Implements the DRIFT framework pattern.
- **6 Alert Channels** — ntfy (self-hosted), Discord, Telegram, SMTP, Webhook (HMAC-SHA256 signed), Gotify. Fires before any kinetic action.
- **4-Tier User RBAC** — HMAC-SHA256 API keys and session tokens for dashboard access.
- **77 API routes** — full programmatic control over every subsystem. → [`docs/API.md`](docs/API.md)

---

## Documentation

| Doc | Contents |
| --- | --- |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Five-hemisphere reasoning, fleet layer invariants (I-01–I-07), three-tier memory model, data flow walkthroughs, design decisions D-01 through D-26 |
| [`API.md`](docs/API.md) | All 77 endpoints, roles, request/response shapes, fleet endpoint quarantine lifecycle |
| [`RUNBOOK.md`](docs/RUNBOOK.md) | Quarantine vs. Block decision flowchart, Fleet Sentinel dry-run rollout procedure, alert response procedures, backup verification (v0.9.0) |
| [`DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Docker, systemd, bare-metal, nginx TLS, backup/restore |
| [`SECURITY.md`](docs/SECURITY.md) | OWASP ASI mapping, threat model |
| [`CHANGELOG.md`](CHANGELOG.md) | Full version history from v0.1.0 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Architecture decision process, PR requirements |

---

## Environment Configuration

Run `python -m butterclaw.setup_wizard` for interactive configuration (9 sections, Docker-aware defaults). Key v0.9.0 fleet variables:

| Variable | Default | Description |
| --- | --- | --- |
| `BUTTERCLAW_FLEET_DB_PATH` | `/data/fleet.db` | Fleet database path — must differ from `BUTTERCLAW_DB_PATH` (I-07-fleet) |
| `FLEET_SENTINEL_DRY_RUN` | `true` | Log Fleet Sentinel verdicts only — no Guardian Brain escalation. Follow RUNBOOK before setting `false`. |
| `BUTTERCLAW_SENTINEL_INTERVAL_HOURS` | `4` | Proactive Fleet Sentinel sweep interval |
| `BUTTERCLAW_COLLUSION_WINDOW_SECONDS` | `180` | Sliding window for collusion role accumulation |
| `BUTTERCLAW_CORRELATION_FLEET_THRESHOLD` | `3` | Distinct agents needed to fire a CorrelationEvent |
| `BUTTERCLAW_TRUST_PROPAGATION_DEPTH` | `1` | Taint propagation hops (1 or 2) |
| `BUTTERCLAW_REPUTATION_DECAY_RATIO` | `3.0` | Taint:recovery asymmetry — taint hits this many times harder |
| `BUTTERCLAW_MAX_CONCURRENT_LLM` | `2` | Max simultaneous LLM hemisphere calls (Guardian Brain is exempt) |

→ Full variable reference: [`.env.example`](.env.example)

---

## Contributing & Co-Maintainers

ButterClaw is applying for the **Agentic AI Foundation (AAIF) Growth Stage** and is actively seeking security-focused co-maintainers — particularly those working with the **Model Context Protocol (MCP)** and **multi-agent orchestration frameworks** — to help scale the fleet trust graph and federation layer. Grab a `good first issue` or read [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`GOVERNANCE.md`](GOVERNANCE.md).

## 🤝 Community Contributors
Contributors who ship features get credited here — not just in the git log.

**Telegram Alert Channel** — Native Telegram Bot API support added to the Alert Dispatcher. Operators can route SOC alerts to mobile with 🔴/🟡/🟢 severity formatting and automatic 4096-char payload enforcement.
<p align="center">
(Contributed by @huanghaiyss)<br></p><br>

If you ship something that lands, your name goes here. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) to get started.

---

## License

* **Source Code & Runtime:** [Apache License 2.0](LICENSE)
* **Architecture & Whitepapers:** [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/)

ButterClaw Tech © 2026

---

<p align="center"><br>
<strong>🦞 ButterClaw v0.9.2 (Mega Release) — The Fleet Layer, Package Architecture & Academic Artifact 🦞</strong><br>
<em>Deterministic guardrails for probabilistic reasoning. Evaluation before execution.</em><br>
<em>Five minds. One fleet. The Sentinel never goes silent.</em><br>
<em>We watch the room.</em><br>
<a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

```text
██████╗ ██╗   ██╗████████╗████████╗███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
██╔══██╗██║   ██║╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
██████╔╝██║   ██║   ██║      ██║   █████╗  ██████╔╝██║     ██║     ███████║██║ █╗ ██║
██╔══██╗██║   ██║   ██║      ██║   ██╔══╝  ██╔══██╗██║     ██║     ██╔══██║██║███╗██║
██████╔╝╚██████╔╝   ██║      ██║   ███████╗██║  ██║╚██████╗███████╗██║  ██║╚███╔███╔╝
╚═════╝  ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
```

# 🦞 ButterClaw v0.6.7: The Agentic SOC

[![License](https://img.shields.io/badge/License-Apache_2.0-ef4444.svg)](https://opensource.org/licenses/Apache-2.0)
[![Version](https://img.shields.io/badge/version-0.6.7-navy.svg)](CHANGELOG.md)
[![Dashboard](https://img.shields.io/badge/Live-butterclaw.tech-eab308.svg)](https://butterclaw.tech)

![Demo](test-event-stream.png)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and API key hashes into cryptographic garbage if a breach is detected. Now with **deterministic policy guardrails**, **external alert dispatch**, and **production-ready deployment packaging** — the Sentinel ships anywhere. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

---

### 🦞 Disambiguation

**ButterClaw Tech (butterclaw.tech)** is an independent, from‑the‑ground‑up local‑first Agentic SOC and kinetic security layer for autonomous AI systems.

It is **not** affiliated with:
* `butterclaw.ai` — a managed hosting service built on top of OpenClaw.
* OpenClaw or any OpenClaw forks (including `ai‑nhancement/ButterClaw`).
* Any other "ButterClaw" projects in the ecosystem.

ButterClaw Tech has its own architecture, runtime, memory model, and execution semantics. It exists to watch, audit, and protect agentic systems — not to be another agent runtime.

**If you're looking for:**
* **A hosted OpenClaw experience?** → Use `butterclaw.ai` or Hostinger's 1-click solution.
* **A general autonomous agent framework?** → Use OpenClaw or Hermes-Agent.
* **A local‑first kinetic security layer with behavioral drift tracking, dual‑hemisphere reasoning, and a vault that actually shreds keys?** → You're in the right place ([ButterClaw.tech](https://butterclaw.tech)).

---

## How It Compares

| | ButterClaw | Halo | LangSmith / LangFuse | Traditional WAF / IDS |
|---|---|---|---|---|
| **Deployment** | Self-hosted, local | Cloud-hosted | Cloud-hosted | Self-hosted |
| **LLM reasoning** | Local Ollama — stays on your machine | Cloud API calls | None | None |
| **Telemetry** | Zero — SQLite only, no outbound data | Sent to Halo cloud | Sent to vendor cloud | Network-layer only |
| **Agent framework** | Model-agnostic — any agent producing log output | Specific LLM provider APIs | LangChain / LlamaIndex native | None |
| **What it monitors** | OS-level telemetry + MCP tool call chain | LLM API calls | LLM traces and spans | Network traffic |
| **Pre-LLM gate** | ✅ Arsenal — 7 regex signatures fire before inference | ❌ | ❌ | ❌ |
| **Behavioral drift** | ✅ Last 5 MCP tool calls as verdict context | ❌ | ✅ Tracing only — no enforcement | ❌ |
| **Verdict mechanism** | Dual-pass: Guardian Brain (0.3) + Auditor (0.0) | Single LLM evaluation | Logging only | Rule-based |
| **Kinetic response** | ✅ SIGKILL rogue process | ❌ Alert only | ❌ | ❌ Alert / block |
| **Credential shredding** | ✅ Active HTTP revocation + local vault wipe | ❌ | ❌ | ❌ |
| **Deterministic policy engine** | ✅ 15 operators, no eval(), 3 scopes | ❌ | ❌ | ✅ Varies |
| **Live-fire test suite** | ✅ 25/25 reproducible — clone and run | ❌ | ❌ | Varies |
| **Dependencies** | 7 pip packages | Managed service | Managed service | Varies |
| **License** | Apache 2.0 | Proprietary | Apache 2.0 | Varies |

> LangSmith and LangFuse are **observability** tools — they log what your agent did. ButterClaw is a **security enforcement** layer — it intervenes before, during, and after LLM calls and executes kinetic responses. These solve different problems.

---

🤝 Seeking AAIF / MCP Co-Maintainers
ButterClaw is applying for the Agentic AI Foundation (AAIF) Growth Stage. We are actively seeking security-focused co-maintainers and contributors—specifically those working with the Model Context Protocol (MCP)—to help scale our v0.7 stdio transport layer. Check out our [CONTRIBUTING.md](CONTRIBUTING.md) and our [GOVERNANCE.md](GOVERNANCE.md) to get involved, or grab one of the "good first issues" on our tracker!

---

## 🚀 What's New in v0.6.7 (The Arsenal Hardening)

**Version 0.6.7** is a security-critical Arsenal integrity release. A post-release audit of `default_signatures.json` against the actual engine it runs inside revealed that 3 of the 5 signatures shipped in v0.6.5 were silently non-functional — dependent on characters that `watcher.py` strips from every log line before they reach the Arsenal. One signature contained an HTML entity encoding artifact that made its reverse shell branch a no-op from day one. All 5 signatures rebuilt sanitizer-aware. Arsenal grows from 5 → **7 signatures**.

*   **Reverse Shell Detection Fixed — `sig_kin_01` (`default_signatures.json`):** The original pattern contained `&gt;&amp;` (HTML-encoded `>&`) — a copy-paste artifact from a rendered web page. The reverse shell branch has never matched a real log line since v0.6.5. Rebuilt to anchor on `/dev/tcp/` and `/dev/udp/` path prefixes, which survive sanitization intact. Added hostname support, combined `nc` flag clusters (`-ev`, `-elp`), `socat`, `mkfifo /tmp/`, and Python/Perl/Ruby/PHP one-liners.
*   **Credential Exfiltration Fixed — `sig_exfil_01` (`default_signatures.json`):** The original matched `$AWS_ACCESS_KEY_ID` — but `watcher.py` strips `$` before payloads reach the Arsenal. Every credential branch was a silent no-op. Rebuilt to match bare variable names. Added raw token detection: live AWS `AKIA` keys, `sk-` tokens (≥20 chars), and JWT bearer tokens — independent of any network tool co-occurrence.
*   **Base64 Pipeline Fixed — `sig_exfil_02` (`default_signatures.json`):** The original required a literal `|` pipe between `base64` and the transmission tool — and `watcher.py` strips `|`. The entire signature was a silent no-op. Rebuilt as a bidirectional proximity match (within 200 chars). No pipe character required.
*   **Encrypted WebSocket Coverage — `sig_cswh_01` (`default_signatures.json`):** Added `wss://` variant and IPv6 loopback `::1`. Production deployments use `wss://` — CSWH pivots over TLS were previously invisible to the Arsenal.
*   **Jailbreak Coverage Expanded — `sig_inj_01` (`default_signatures.json`):** 4 phrases → 15 pattern branches across 5 jailbreak families: ignore-previous-instructions variants, persona reassignment (`you are now / act as / pretend to be`), mode unlock keywords (`DAN mode`, `developer mode`, `sudo mode`, `god mode`), override/forget-training, and simulate-unrestricted family.
*   **Cloud Metadata Service Probe — `sig_exfil_03` (`default_signatures.json`) 🆕:** New CRITICAL/SIGKILL signature at `pre_tool` scope. Detects agent requests to AWS IMDSv1/v2 (`169.254.169.254`), GCP (`metadata.google.internal`), Azure, and ECS credential endpoints. There is no legitimate operational reason for a monitored agent to query these directly — their only payload is live IAM credentials.
*   **Persistence Mechanism Injection — `sig_kin_02` (`default_signatures.json`) 🆕:** New CRITICAL/SIGKILL signature. Detects the second stage of most agent compromise scenarios: SSH `authorized_keys` writes, cron injection, systemd service installation, `useradd`/`usermod`, and critical file paths (`/etc/sudoers`, `/etc/shadow`, `/etc/passwd`). Anchored on destination paths since `>>` is stripped by the sanitizer.
*   **Live-Fire Suite Rebuilt — `scripts/test_attack.py`:** Rebuilt from a single-payload script into a structured 23-case suite covering all 7 signatures. Payloads are grouped by signature, labelled by attack variant, and correctly pre-sanitized to match real engine input. Exits with code 1 on failure — CI-compatible.
*   **Architecture Formally Documented — `ARCHITECTURE.md`:** Dual-hemisphere reasoning and behavioral drift tracking — both referenced in the project tagline — are now formally defined with source-accurate descriptions. Dual-hemisphere maps to `ask_guardian_agent()` (temperature `0.3`, action mandate) + `run_self_audit()` (temperature `0.0`, skepticism mandate). Behavioral drift maps to `ledger_query(limit=5, status="success")` — a sliding window of recent MCP actions injected as `timeline_context` into both LLM prompts. Design Decisions D-08 and D-09 added.

---

## 🚀 What was New in v0.6.6 (The 12-Factor Seal)?

**Version 0.6.6** finalizes the Exoskeleton's configuration architecture by making the entire system fully 12-Factor compliant, alongside a massive, 63-point documentation reconciliation audit.

*   **Decentralized Infrastructure Rate Limits (`.env`):** The internal machine-to-machine `infrastructure` role rate limit (used by the Watcher daemon and auto-healing components) has been lifted from a hardcode into the dynamic `config.py` ecosystem. The entire Auth gateway is now 100% configurable via environment variables without touching a single line of Python.
*   **The Architecture Audit:** Executed a massive reconciliation audit across 9 files to ensure the documentation perfectly mirrors the physical code. The 49 API routes, 4-tier RBAC system, 15 DRIFT policy operators, and 6 alert channels are now mathematically synced and verified against the codebase. 
*   **Developer Experience (`docker-compose.dev.yml`):** Overhauled the local development overlay. Fixed service name mismatches, suppressed redundant notification containers in dev mode, and injected the `BUTTERCLAW_API_KEY` bootstrap sequence to prevent cold-start failures during local testing. 
*   **Expanded Governance & Testing:** The `CONTRIBUTING.md` and `GOVERNANCE.md` files have been completely rewritten to cover the full Exoskeleton surface. They now explicitly document the 61-test diagnostic suite requirement and establish a strict architectural decision process for security-sensitive pull requests.

---

## 🚀 What was New in v0.6.5 (The Exoskeleton Sealed)?

**Version 0.6.5** is the official code-locked, mathematically sealed production release for the Hacker News launch. It introduces deterministic regex signatures defense, a live terminal matrix, and massive security hardening.

* **Threat Signatures Arsenal (`default_signatures.json`):** Shipped with 5 pre-compiled regex signatures targeting CSWH and prompt injections out of the box. Intercepts threats in milliseconds before the LLM Brain even evaluates them.
* **The Paranoia Dial:** Scalable kinetic response system. Level 1 (Observe), Level 2 (Active Defense: SIGKILL only), Level 3 (Air-Gapped Lockdown: SIGKILL + Shred Vault).
* **Visual TUI Dashboard (`./dash`):** Real-time, double-buffered, flicker-free terminal interface displaying live SOC telemetry, active rules, and the current Paranoia level across both Linux and Windows Docker hosts.
* **Audit Remediation & Hardening:** Systematically eradicated 29 distinct vulnerabilities, race conditions, and thread leaks. The Gibson race condition is mathematically sealed, SMTP passwords are now encrypted at rest, and SQLite brute-force tracking is fully persistent.
* **Live Fire Testing Scripts (`scripts/add_rule.py`, `scripts/test_attack.py`):** Standalone diagnostic harnesses allowing operators to safely inject custom regex signatures and simulate kinetic prompt injection attacks against the Arsenal without requiring an active LLM payload.
* **Contribution Provided by the Community:** Telegram Alert Channel — Native Telegram Bot API support added to the Alert Dispatcher. Operators can route SOC alerts to mobile with 🔴/🟡/🟢 severity formatting and automatic 4096-char payload enforcement. (Contributed by @huanghaiyss)

---

## 🚀 What was New in v0.6.4 (Autonomous Deployment)?

**Version 0.6.4** combines the patches of the last two bug fix releases for the previous feature version (0.6.3). And adds a One-Click Autonomous Install Script now offered for less friction in the install process.

* **One-Click Deployment** Added an autonomous install.sh script to drop time-to-value to under 60 seconds.
* **The Exoskeleton Hardening** Unified the v0.6.3 patch cycle, finalizing the Nginx TLS routing, Docker bridge fixes, and the active token assassination network layer.

---

## 🚀 What was New in v0.6.3.2 (Active Tools & Nginx Routing)?

**Version 0.6.3.2** completely isolates the application backend and upgrades the Gibson kill-switch from a local wipe to an active network-level threat response.

* **Active Token Assassination (`buttervault.py`):** When `DRY_RUN=False`, the Gibson no longer just shreds local SQLite files. It now fires live HTTP `DELETE` and `POST` requests to GitHub and other external OAuth providers to instantly invalidate tokens globally *before* scorching the local database.
* **The Double Air-Gap (`DRY_RUN`):** Plugged a critical leak where manual UI buttons bypassed the safety harness. The Gibson now contains a hardcoded, low-level `DRY_RUN` check blocking all kinetic actions, guaranteeing safe local prompt injection testing.
* **Port 5000 Isolation:** Removed raw exposed port 5000 from Docker. All UI and API traffic (`index.html` and `routing.html`) is now securely routed through an Nginx reverse proxy on standard web ports (80/443) using local TLS certificates.
* **SSRF Lockdown (`butterclaw_mcp.py`):** Hardcoded the `scan_port` MCP tool to a strict allowlist. Malicious LLMs can no longer use ButterClaw to scrape internal VPS/AWS metadata.

### 📦 What was New in v0.6.3.1 (Full Docker)

**Full Docker Edition** hardens the deployment package for seamless cross-platform orchestration (specifically Windows/WSL environments) and breaks several complex containerization deadlocks.

* **Infrastructure Auto-Healing:** Solves the "Cold Start Paradox." If the database is wiped, the server automatically generates and injects its own secure API keys and Watcher badges on boot.
* **Air-Gapped Push Notifications (`ntfy`):** Integrated the official `ntfy` container into the deployment stack. ButterClaw can now push native OS notifications directly to your phone or browser entirely locally, without leaking telemetry to third-party cloud services like Discord or Slack.
* **Alert Dispatcher Auto-Boot:** The Exoskeleton dynamically reads your `.env` topic and builds its own notification routing rules in the database automatically on startup.
* **The Vault Initialization Deadlock Fix:** Forces the Master Vault Key to generate during the server boot sequence, ensuring the session-cookie signer is ready *before* the first user login attempt.
* **Split-Brain Database Cure:** Unified `try/except` imports for `config.py` across all modules prevent Docker volume mounts from accidentally splitting SQLite writes across different directories.
* **Windows Host Bridging (`host.docker.internal`):** Secures GPU-accelerated local Ollama inference by cleanly bridging the isolated Linux container back to the host machine's native Windows Ollama instance.
* **Visible Keyrings (`XDG_DATA_HOME`):** Bypasses Docker's root-permission traps by mapping the alternate Keyring storage directly into the visible `/app/data` directory.
* **Frontend Routing Aliases:** Native Flask `@app.route` decorators added for standard HTML paths, allowing seamless dev-mode browsing without Nginx.

---

### 📦 Features Introduced in v0.6.3

**Deployment Packaging** — The Exoskeleton is battle-tested. v0.6.3 adds everything required to deploy ButterClaw to production: centralized configuration, Docker containerization, systemd service management, nginx TLS termination, and automated backup/restore — all without adding a single new pip dependency.

#### ⚙️ Centralized Configuration (`config.py`)

Single source of truth for all runtime configuration across all modules. No more patching multiple files to change a database path.

**26 configurable fields** across 9 categories:

| Category | Fields | Examples |
|----------|--------|----------|
| **Paths** | 3 | `DB_PATH`, `MCP_SCRIPT`, `BASE_DIR` |
| **Server** | 3 | `HOST`, `PORT`, `DEBUG` |
| **CORS** | 1 | `CORS_ORIGINS` (comma-separated) |
| **Brain/Ollama** | 5 | `OLLAMA_BASE_URL`, `MODEL_NAME`, `CONFIDENCE_THRESHOLD`, `DRY_RUN` |
| **MCP Transport** | 3 | `MCP_TRANSPORT`, `MCP_SSE_URL`, `MCP_SSE_TOKEN` |
| **Auth** | 4 | `AUTH_RATE_ADMIN`, `SESSION_TTL` |
| **Alerts** | 4 | `ALERT_DELIVERY_TIMEOUT`, `ALERT_MAX_RETRIES` |
| **OAuth** | 1 | `OAUTH_STATE_TTL` |
| **Identity** | 1 | `INSTANCE_ID` |

**Priority chain:**

> Environment Variables (highest) → .env File → Hardcoded Defaults (lowest)

```python
# Usage — identical across all modules:
from config import cfg

db_path = cfg.DB_PATH                    # unified across server, auth, policy, alert, vault
port = cfg.PORT                          # was hardcoded 5000
confidence = cfg.CONFIDENCE_THRESHOLD    # was hardcoded 0.6
```

**Key features:**

* `BUTTERCLAW_` prefix on all env vars — no collision with system vars
* `_validate()` at import time — fail-fast on bad config
* `to_dict(redact_secrets=True)` — API-safe config export
* `.env` parser built on stdlib — no python-dotenv dependency
* Env vars never overridden by `.env` (12-factor compliance)

#### 🐳 Docker Deployment

Three-container production stack:

| Container | Role | Health Check |
| --- | --- | --- |
| `butterclaw-server` | Main application (Flask + all modules) | `healthcheck.py` → `/api/health` |
| `butterclaw-ntfy` | Self-hosted push notification server (port 2586) | ntfy `/healthz` endpoint |
| *(nginx)* | TLS termination + reverse proxy + static files | Upstream health |

**Key features:**

* Non-root `butterclaw` user inside container
* GPU passthrough via `nvidia-container-toolkit` (CPU fallback automatic)
* Named volumes for SQLite persistence
* JSON-file logging with 10MB rotation
* `HEALTHCHECK` directive for orchestrator integration

> **Note:** Ollama runs **outside** the Docker stack — on the host directly, or via `host.docker.internal` bridging. It is not a managed Docker service.

#### 🖥️ systemd Deployment (Bare-Metal VPS)

```bash
# Install service
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo cp .env /etc/butterclaw.env
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw

# Monitor
journalctl -u butterclaw -f
```

**Security hardening:**

* `ProtectSystem=strict` — filesystem read-only except working directory
* `NoNewPrivileges=true` — prevent privilege escalation
* `ProtectHome=true` — home directories invisible to the process
* `PrivateTmp=true` — isolated temp directory
* `Restart=on-failure` with 5s delay

#### 💾 Backup & Restore

```bash
# Create timestamped backup (SQLite .backup + .env)
./scripts/backup.sh

# List available backups
./scripts/restore.sh

# Restore from specific backup
./scripts/restore.sh backups/butterclaw-backup-20260420-1200.tar.gz
```

* SQLite `.backup` command (atomic — never `cp` on a live DB)
* Auto-prunes old backups (keeps last 7)
* Includes `.env` configuration in archive
* **Note:** The OS keyring entry (ButterVault master key) is not included — back up your keyring separately before any host migration

#### 🔒 Nginx TLS Termination

* HTTP → HTTPS redirect
* TLSv1.2/1.3 with ECDHE cipher suites
* HSTS (1 year), X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
* SSE-specific proxy: `proxy_buffering off` + 24h timeout
* Static file serving for dashboard HTML
* 300s read timeout for Brain inference

---

## 🔔 Alert Dispatcher (v0.6.2)

A security monitoring system that can't *reach* its operator is just a log file with extra steps. The Alert Dispatcher pushes notifications to external channels so the operator knows the moment something happens, even if nobody is watching the dashboard.

### Multi-Channel Alert Routing

6 channel types, all built on Python stdlib (zero new pip dependencies):

| Channel | Transport | Payload Format |
| --- | --- | --- |
| **Webhook** | HTTP POST + HMAC-SHA256 signature | JSON with event_type, severity, context |
| **Discord** | Discord webhook API | Rich embed with color-coded severity sidebar |
| **Telegram** | Telegram Bot API | Severity-formatted message with 4096-char enforcement |
| **ntfy** | ntfy.sh or self-hosted | Push with title, body, priority, tags |
| **SMTP** | smtplib (password encrypted at rest) | Email with structured plain-text body |
| **Gotify** | Self-hosted push API | Title + message + priority (1–10) |

### 📱 Air-Gapped Push Notifications (ntfy)

ButterClaw v0.6.3.1 ships with a completely private, self-hosted push notification server (`ntfy`) built directly into the Docker stack.

1. Set `BUTTERCLAW_ALERT_NTFY_TOPIC=your-secret-topic` in your `.env` file.
2. Open `http://localhost:2586` in your browser, or download the free `ntfy` iOS/Android app.
3. Subscribe to your secret topic. You will receive native push notifications the millisecond a threat is detected — zero bytes leave your local network.

### 9 Alert Event Types

| Event | When It Fires | Severity |
| --- | --- | --- |
| `critical_verdict` | Brain or Policy returned CRITICAL | 🔴 Critical |
| `high_confidence` | Brain returned high-confidence warning | 🟡 Warning |
| `gibson_triggered` | Automatic Gibson from ChainExecutor | 🔴 Critical |
| `gibson_manual` | Manual Gibson via `/api/rotate-keys` | 🔴 Critical |
| `chain_executed` | MCP chain completed | 🟡 Warning |
| `policy_blocked` | Policy Engine blocked request or tool | 🟡 Warning |
| `auth_failure` | 5+ auth failures from one IP in 60s | 🔴 Critical |
| `mcp_tool_called` | MCP tool called in chain | 🟢 Info |
| `system_startup` | Server started successfully | 🟢 Info |

---

## 🛡️ Policy Engine (v0.6.1)

Deterministic guardrails for the probabilistic Brain. Implements the DRIFT framework pattern (NeurIPS 2025) — a Dynamic Validator that constrains the Brain's probabilistic reasoning with rules that say *"if X, then always Y"* — no reasoning required.

### 3-Scope Filter Pipeline

| Scope | When It Fires | What It Can Do |
| --- | --- | --- |
| **Pre-Brain** | Before the LLM is called | Short-circuit to CRITICAL or BENIGN without burning inference time |
| **Post-Brain** | After the LLM returns a verdict | Override, escalate, downgrade, or require higher confidence |
| **Pre-Tool** | Before each MCP tool call in a chain | Block specific tools via allowlist/blocklist |

**15 safe condition operators** — all use whitelist dispatch, no `eval()`:
`contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `regex_match`, `greater_than`, `less_than`, `greater_equal`, `less_equal`, `in_list`, `not_in_list`, `length_gt`, `length_lt`

---

## 🔐 API Gateway & Authentication (v0.6.0)

Every endpoint protected by role-based access control with HMAC-SHA256 API keys and session tokens.

| Tier | Privilege | Access Level | Use Case |
| --- | --- | --- | --- |
| **infrastructure** | -1 (highest) | Machine-to-machine superuser — auto-healing, Watcher daemon | Internal only — never issued to human operators |
| **admin** | 0 | Full access — vault, Gibson, key management, config | System owner |
| **operator** | 1 | Analyze threats, read settings, start OAuth | Active operators |
| **viewer** | 2 (lowest) | Read-only — logs, events, status, SSE stream | Monitoring dashboards |

> The `infrastructure` role is bootstrapped from `BUTTERCLAW_API_KEY` on startup. It does not appear in `GET /api/auth/keys` listings and cannot be created via the API.

---

## 💀 Gibson Kill Switch

The nuclear option. When triggered, ButterVault physically shreds all credentials into cryptographic garbage. In v0.6.2+, the Alert Dispatcher fires notifications BEFORE vault destruction — alert-then-burn. In v0.6.3.2+, it fires active network-level assassination requests against external APIs before destroying local data.

```text
Gibson Triggered:
  1. dispatch_alert("gibson_triggered")    ← alert fires
  2. _dispatch_worker → all channels       ← notifications sent
  3. buttervault.butter_keys()             ← vault destroyed & tokens assassinated
  4. auth.destroy_all_api_keys()           ← auth destroyed
  5. Operator receives notification        ← notification arrives
```

**What Survives Gibson:**

```text
DESTROYED by Gibson:           SURVIVES Gibson:
├── vault table (API keys)     ├── policy_rules table
├── oauth_tokens table         ├── policy_events table
├── api_keys table             ├── alert_channels table
├── session cache              ├── alert_rules table
└── OS keyring master key      ├── alert_history table
                               ├── mcp_events table
                               ├── logs table
                               └── config.py / .env (filesystem)
```

---

## 📚 Documentation

For deep dives into ButterClaw's architecture, API references, and security models, see our documentation directory:

* **[Architecture & The Exoskeleton](docs/ARCHITECTURE.md)**
* **[API Reference (49 Endpoints)](docs/API.md)**
* **[OWASP Agentic Security Initiative (ASI) Mapping](docs/SECURITY.md)**
* **[Deployment & Configuration Guide](docs/DEPLOYMENT.md)**

---

## 🏗️ Architecture

**The Exoskeleton — Layered Defense:**

```text
┌─────────────────────────────────────────────────┐
│  Deployment Layer (v0.6.3+)                     │
│  Docker, systemd, nginx, config.py, backup      │
├─────────────────────────────────────────────────┤
│  Alert Layer (v0.6.2)                           │
│  6 channels, 9 event types, HMAC signing        │
├─────────────────────────────────────────────────┤
│  Policy Layer (v0.6.1)                          │
│  3-scope pipeline, 15 operators, DRIFT pattern  │
├─────────────────────────────────────────────────┤
│  Auth Layer (v0.6.0)                            │
│  HMAC-SHA256 keys, 4-tier RBAC, sessions        │
├─────────────────────────────────────────────────┤
│  The Nervous System (v0.5.x)                    │
│  Brain, ChainExecutor, Event Ledger, MCP, SSE   │
├─────────────────────────────────────────────────┤
│  Core (v0.1–v0.4)                               │
│  Watcher, ButterVault, Dashboard, Ollama        │
└─────────────────────────────────────────────────┘
```

**Component Map:**

| Component | File | Lines | Version | Role |
| --- | --- | --- | --- | --- |
| Config | `config.py` | ~300 | v0.6.3 | Centralized env-driven configuration |
| Server | `server.py` | ~1,800 | v0.6.5 | Flask API, Brain, ChainExecutor, Auditor |
| Auth | `auth.py` | ~650 | v0.6.5 | API gateway, 4-tier RBAC, session tokens |
| Policy Engine | `policy_engine.py` | ~900 | v0.6.5 | Deterministic guardrails, DRIFT pipeline |
| Alert Dispatcher | `alert_dispatcher.py` | ~300 | v0.6.5 | Push notifications, 6 channels |
| ButterVault | `buttervault.py` | ~700 | v0.6.5 | Encrypted vault, active revocation, Gibson |
| MCP Client | `butterclaw_mcp.py` | ~400 | v0.6.5 | MCP dual-transport, SSRF block |
| MCP Transport | `mcp_transport.py` | ~200 | v0.5.0 | SSE/stdio transport primitives |
| OAuth Config | `oauth_config.py` | ~150 | v0.5.2 | OAuth provider templates, revocation |
| Watcher | `watcher.py` | ~250 | v0.6.5 | OS telemetry collector, retry queue |
| TUI Dashboard | `tui_dashboard.py` | ~350 | v0.6.5 | Read-only terminal SOC view |

---

## 📡 API Reference

### Auth Endpoints (7 routes — v0.6.0)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | public | Exchange API key for session token |
| POST | `/api/auth/logout` | any | Clear session cookie |
| GET | `/api/auth/whoami` | any | Current identity and role |
| GET | `/api/auth/keys` | admin | List all API keys (excludes infrastructure) |
| POST | `/api/auth/keys` | admin | Create new API key |
| DELETE | `/api/auth/keys/<id>` | admin | Revoke API key |
| DELETE | `/api/auth/keys/<id>/purge` | admin | Permanently delete key |

### Policy Endpoints (8 routes — v0.6.1)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/policies` | viewer | List all policies |
| POST | `/api/policies` | admin | Create policy |
| GET | `/api/policies/<id>` | viewer | Get policy |
| PUT | `/api/policies/<id>` | admin | Update policy |
| DELETE | `/api/policies/<id>` | admin | Delete policy |
| POST | `/api/policies/<id>/toggle` | admin | Enable/disable |
| POST | `/api/policies/dry-run` | operator | Test payload against policies |
| GET | `/api/policies/events` | viewer | Query policy event log |

### Alert Endpoints (13 routes — v0.6.2)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/alerts/channels` | viewer | List channels |
| POST | `/api/alerts/channels` | admin | Create channel |
| PUT | `/api/alerts/channels/<id>` | admin | Update channel |
| DELETE | `/api/alerts/channels/<id>` | admin | Delete channel (cascade) |
| POST | `/api/alerts/channels/<id>/toggle` | admin | Enable/disable |
| POST | `/api/alerts/channels/<id>/test` | operator | Send test alert |
| GET | `/api/alerts/rules` | viewer | List rules |
| POST | `/api/alerts/rules` | admin | Create rule |
| PUT | `/api/alerts/rules/<id>` | admin | Update rule |
| DELETE | `/api/alerts/rules/<id>` | admin | Delete rule |
| POST | `/api/alerts/rules/<id>/toggle` | admin | Enable/disable |
| GET | `/api/alerts/history` | viewer | Query alert history |
| GET | `/api/alerts/status` | viewer | Alert system summary |

### Core Endpoints (5 routes)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/analyze` | operator | Analyze threat payload |
| GET | `/api/health` | public | System health + instance info |
| GET | `/api/config` | admin | Resolved config (redacted secrets) |
| GET | `/api/stream` | viewer | SSE event stream |
| GET | `/api/logs` | viewer | Query log history |

### MCP Endpoints (6 routes — v0.5.0+)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| GET | `/api/mcp/tools` | viewer | List available MCP tools |
| POST | `/api/mcp/restart` | admin | Restart MCP process |
| GET | `/api/mcp/status` | viewer | MCP process health |
| GET | `/api/events` | viewer | Query event ledger |
| GET | `/api/events/count` | viewer | Event ledger count |
| GET | `/api/settings` | viewer | Server runtime settings |

### Vault & OAuth Endpoints (10 routes — v0.5.x)

| Method | Endpoint | Role | Description |
| --- | --- | --- | --- |
| POST | `/api/rotate-keys` | admin | Manual Gibson Kill Switch |
| GET | `/api/vault/status` | viewer | Vault health status |
| GET | `/api/vault/credentials` | operator | List stored credentials |
| POST | `/api/vault/credentials` | admin | Store new credential |
| DELETE | `/api/vault/credentials/<name>` | admin | Delete credential |
| GET | `/api/oauth/providers` | viewer | List OAuth providers |
| POST | `/api/oauth/start/<provider>` | operator | Start OAuth flow |
| GET | `/api/oauth/callback` | public | OAuth callback handler |
| GET | `/api/oauth/tokens` | operator | List OAuth tokens |
| DELETE | `/api/oauth/tokens/<provider>` | admin | Delete OAuth token |

**Total: 49 API routes** (7 Auth + 8 Policy + 13 Alert + 5 Core + 6 MCP + 10 Vault/OAuth)

---

## 📁 Project Structure

```text
butterclaw/
├── server.py                  # Flask API + Brain + ChainExecutor + Auditor (v0.6.5)
├── config.py                  # Centralized configuration (v0.6.3)
├── auth.py                    # API gateway + 4-tier RBAC (v0.6.5)
├── policy_engine.py           # Deterministic guardrails (v0.6.5)
├── alert_dispatcher.py        # Push notifications, 6 channels (v0.6.5)
├── buttervault.py             # Encrypted vault + active revokes + Gibson (v0.6.5)
├── butterclaw_mcp.py          # MCP tool definitions + SSRF blocks (v0.6.5)
├── mcp_transport.py           # SSE/stdio transport (v0.5.0)
├── oauth_config.py            # OAuth provider templates (v0.5.2)
├── watcher.py                 # OS telemetry collector + retry queue (v0.6.5)
├── tui_dashboard.py           # Read-only TUI SOC view (v0.6.5)
├── default_signatures.json    # The Arsenal — pre-compiled regex signatures
├── index.html                 # Main dashboard
├── routing.html               # Advanced config dashboard
├── requirements.txt           # 7 pip dependencies
├── .env.example               # Environment variable template
├── Modelfile.example          # Ollama tuning profile (gemma4:e4b, 16k ctx, temp 0.3)
├── Dockerfile                 # Container build
├── docker-compose.yml         # Production orchestration (3 services)
├── docker-compose.dev.yml     # Dev overlay
├── .dockerignore              # Build context exclusions
├── install.sh                 # One-click autonomous install (v0.6.4)
├── nginx/
│   ├── butterclaw.conf        # Primary vhost — TLS, proxy, SSE, security headers
│   └── default.conf           # Fallback vhost — returns 444 on unmatched hosts
├── scripts/
│   ├── healthcheck.py         # Docker health check → /api/health
│   ├── backup.sh              # Timestamped backup (SQLite + .env, keeps last 7)
│   ├── restore.sh             # Restore from backup archive
│   ├── add_rule.py            # Live Fire — inject test signature into Arsenal
│   └── test_attack.py         # Live Fire — simulate prompt injection attack
├── systemd/
│   └── butterclaw.service     # systemd unit (ProtectSystem=strict, NoNewPrivileges)
└── data/
    └── butterclaw.db          # SQLite database (auto-created on first boot)
```

---

## 🔒 Security Architecture

| Layer | Mechanism | Version |
| --- | --- | --- |
| **TLS** | nginx reverse proxy with TLSv1.2/1.3, ECDHE ciphers, HSTS | v0.6.3 |
| **Container** | Non-root user, read-only filesystem, `ProtectSystem=strict`, `NoNewPrivileges=true`, `ProtectHome=true`, `PrivateTmp=true` | v0.6.3 |
| **Authentication** | HMAC-SHA256 API keys, HMAC-signed session tokens, `httpOnly` cookies | v0.6.0 |
| **Authorization** | 4-tier RBAC (infrastructure/admin/operator/viewer) | v0.6.5 |
| **Policy** | Deterministic pre-brain/post-brain/pre-tool guardrails, 15 safe operators | v0.6.1 |
| **Alerting** | 6 external channels, HMAC-signed webhooks, auth brute-force detection | v0.6.5 |
| **Vault** | Fernet encryption, OS keyring master key, active network token revocation, Gibson Kill Switch | v0.6.3.2 |
| **Analysis** | Local LLM reasoning + confidence scoring + chain safety rails | v0.5.0+ |
| **Monitoring** | Event Ledger + Policy Events + Alert History — 3 independent audit trails | v0.5.0+ |

---

## 🛡️ OWASP Agentic Security Initiative (ASI) Coverage

| ASI Threat | ButterClaw Mitigation |
| --- | --- |
| ASI-01: Excessive Agency | Brain confidence gating + ChainExecutor MAX_STEPS=10 / TIMEOUT=60s + Policy Engine pre-tool scope gating (v0.5.0+) |
| ASI-02: Insufficient Access Control | 4-tier RBAC (infrastructure/admin/operator/viewer) + per-role rate limiting + HMAC-SHA256 auth gateway (v0.6.5) |
| ASI-03: Knowledge Poisoning | Local-first LLM — no external training data ingestion. Watcher monitors OS telemetry, not user content (v0.1.0+) |
| ASI-04: Identity & Credential Abuse | ButterVault + OAuth lifecycle + active token revocation + Gibson atomic destruction (v0.6.3.2) |
| ASI-05: Cascading Failures | ChainExecutor safety rails: MAX_STEPS=10, TIMEOUT=60s. Steps fail independently (v0.5.1) |
| ASI-06: Indirect Prompt Injection | Policy Engine deterministic pattern matching pre-brain + watcher blacklist sanitizer + 4096-char capture (v0.6.1) |
| ASI-07: Insufficient Monitoring | Event Ledger + Policy Events + Alert History — 3 audit trails + Auditor false-positive loop (v0.5.0+) |
| ASI-08: Insecure Output Handling | Brain output treated as untrusted — post_brain policy gate required before any kinetic action. DRY_RUN hard-blocks all destructive output at code level (v0.6.1) |
| ASI-09: Inadequate Logging | 3 audit trails + external notification routing across 6 channels. MCP tool calls logged with status, elapsed_ms, chain_id, chain_step (v0.6.2) |
| ASI-10: Uncontrolled Escalation | Gibson panic destroys all credentials atomically + Alert Dispatcher fires before destruction. DRY_RUN hard-blocks Level 3 regardless of verdict (v0.6.2) |

---

## 📋 Version History

| Version | Codename | Date | Milestone |
| --- | --- | --- | --- |
| **v0.6.7** | The Arsenal Hardening | 2026-07-27 | Sanitizer-aware signatures, 5→7 sigs, sig_kin_01 HTML entity fix, live-fire suite |
| **v0.6.6** | The Reconciliation | 2026-07-14 | 63-point doc audit, 12-factor config, docker-compose.dev.yml critical fix |
| **v0.6.5** | The Exoskeleton Sealed | 2026-06-24 | Regex Signatures Arsenal, Paranoia Dial, TUI Dashboard, 29-vuln audit |
| **v0.6.4** | Autonomous Deployment | 2026-06-08 | One-Click Install Script |
| **v0.6.3.2** | Active Tools & Nginx Routing | 2026-05-21 | TLS routing, SSRF lockdown, active token revocation |
| **v0.6.3.1** | Deployment Packaging (Docker Edition) | 2026-05-07 | Docker bridge, Vault deadlock fix, Windows volume fixes |
| **v0.6.3** | The Exoskeleton: Deployment Packaging | 2026-05-01 | config.py, Docker, systemd, nginx, backup/restore |
| **v0.6.2** | The Exoskeleton: Alert Dispatcher | 2026-05-01 | 5 channels, 9 events, HMAC signing, brute-force detection |
| **v0.6.1** | The Exoskeleton: Policy Engine | 2026-05-01 | 3-scope pipeline, 15 operators, DRIFT pattern |
| **v0.6.0** | The Exoskeleton: API Gateway & Auth | 2026-04-20 | HMAC-SHA256, 3-tier RBAC, session tokens |
| **v0.5.2** | ButterVault OAuth | 2026-04-16 | OAuth 2.0 flows, token refresh, Gibson destroys OAuth |
| **v0.5.1** | Tool Chaining | 2026-04-16 | ChainExecutor, multi-step execution, safety rails |
| **v0.5.0** | The Nervous System | 2026-04-14 | Event Ledger, SSE Transport, MCP Manager |
| **v0.4.x** | MCP Transport Refactor | 2026-04-10 | Modular transport, JSON-RPC |
| **v0.3.x** | Routing Dashboard | 2026-04-04 | routing.html, advanced config UI |
| **v0.2.0** | ButterVault | 2026-04-01 | Encrypted credentials, Gibson Kill Switch |
| **v0.1.0** | Initial Release | 2026-03-17 | Core analysis, watcher, dashboard, MCP tools |

---

## 🗺️ Roadmap — The Exoskeleton (v0.6.x)

| Pillar | Version | Status | Deliverable |
| --- | --- | --- | --- |
| 1. API Gateway & Auth | v0.6.0 | ✅ Delivered | HMAC-SHA256, 4-tier RBAC, sessions |
| 2. Policy Engine | v0.6.1 | ✅ Delivered | 3-scope pipeline, 15 operators, DRIFT pattern |
| 3. Alert Dispatcher | v0.6.2 | ✅ Delivered | 6 channels, HMAC webhooks |
| 4. Deployment Packaging | v0.6.3 | ✅ Delivered | Docker, systemd, config.py |

**The Exoskeleton is complete.** All four pillars are shipped.

---

## ⚡ Quick Start (Autonomous Deployment)

Time-to-value is under 60 seconds. ButterClaw's auto-healing architecture builds its own database, generates secure keys, and wires up its alert networks from a completely blank slate.

**1. The One-Click Install:**

```bash
curl -sSL https://raw.githubusercontent.com/butterclaw-tech/butterclaw/main/install.sh | bash
```

**2. Docker Compose (Recommended):**

ButterClaw's auto-healing architecture allows it to build its database, generate secure keys, and wire up its alert networks from a completely blank slate. Ollama must be running locally on the host before starting the stack.

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw

# Pull the base model and build the ButterClaw-optimised variant
ollama pull gemma4:e4b
ollama create butterclaw-optimized -f Modelfile.example

# 1. Configure your environment
cp .env.example .env
# Edit .env — set BUTTERCLAW_INSTANCE_ID, BUTTERCLAW_ALERT_NTFY_TOPIC, etc.

# 2. Generate Local TLS Certificates (for nginx)
mkdir -p nginx/certs
docker run --rm -v "${PWD}/nginx/certs:/certs" alpine/openssl req -x509 -nodes \
  -days 365 -newkey rsa:2048 \
  -keyout /certs/butterclaw.key -out /certs/butterclaw.crt -subj "/CN=localhost"

# 3. Ignite the Exoskeleton
docker compose up -d --build

# 4. Grab your Bootstrap Admin API Key (look for the 🔐 [AUTH] line)
docker compose logs -f butterclaw
```

**3. Launch the Matrix TUI:**

Once the container is running, attach to the live terminal dashboard:

```bash
./dash
```

Access the dashboard at **https://localhost** and the ntfy UI at **http://localhost:2586**.

---

## 🎯 Live Fire Testing (The Regex Arsenal)

ButterClaw ships with safe, standalone scripts to verify the integrity of the Policy Engine and the Regex Arsenal without requiring a live LLM or external payloads.

```bash
# 1. Inject a test signature into the live database
python scripts/add_rule.py

# 2. Fire the simulated payload and watch the Arsenal intercept it
python scripts/test_attack.py
```

---

### 🛡️ Arsenal Signatures (7 — v0.6.7)

| ID | Name | Severity | Scope | Response | v0.6.7 Status |
|---|---|---|---|---|---|
| `sig_cswh_01` | CSWH WebSocket Port Scanning | 🔴 CRITICAL | pre_brain | SIGKILL | Fixed: `wss://` + IPv6 `::1` added |
| `sig_exfil_01` | Credential Exfiltration via Network Tool | 🔴 CRITICAL | pre_brain | SIGKILL | Fixed: `$`-free; AKIA/sk-/JWT matching added |
| `sig_exfil_02` | Base64 Exfiltration Pipeline | 🟡 WARNING | pre_brain | BLOCK | Fixed: rebuilt as pipe-free proximity match |
| `sig_inj_01` | System Prompt Override / Jailbreak | 🟡 WARNING | pre_brain | BLOCK | Expanded: 4 phrases → 15 branches, 5 jailbreak families |
| `sig_kin_01` | Reverse Shell Indicators | 🔴 CRITICAL | pre_brain | SIGKILL | Fixed: HTML entity bug (`&gt;&amp;`); anchored on `/dev/tcp/`; +6 shell variants |
| `sig_exfil_03` | Cloud Metadata Service Probe | 🔴 CRITICAL | pre_tool | SIGKILL | **New** — AWS/GCP/Azure IMDS link-local endpoints |
| `sig_kin_02` | Persistence Mechanism Injection | 🔴 CRITICAL | pre_brain | SIGKILL | **New** — SSH keys, cron, systemd, useradd/usermod |

All 7 patterns validated against 74 positive and negative test cases, matched to the exact sanitizer behavior in `watcher.py` and the `re.IGNORECASE` / `re.search()` call in `policy_engine.py`.

---

### systemd (Bare-Metal VPS)

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw

# Install dependencies
pip install -r requirements.txt

# Install Ollama and pull the model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b
ollama create butterclaw-optimized -f Modelfile.example

# Configure
cp .env.example /etc/butterclaw.env
# Edit /etc/butterclaw.env

# Install service
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw

# Verify
journalctl -u butterclaw -f
curl http://localhost/api/health
```

### Bare-Metal (Development)

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw

pip install -r requirements.txt

# Pull base model and build ButterClaw-optimised variant
ollama pull gemma4:e4b
ollama create butterclaw-optimized -f Modelfile.example

cp .env.example .env
python server.py
```

On first run, the bootstrap CLI prints your admin API key to the terminal. Save it — it's shown exactly once.

---

## 📊 Diagnostic Tests

All modules include standalone diagnostic suites:

| Module | Command | Tests |
| --- | --- | --- |
| `config.py` | `python config.py` | 21/21 |
| `alert_dispatcher.py` | `python alert_dispatcher.py` | 14/14 |
| `policy_engine.py` | `python policy_engine.py` | 16/16 |
| `auth.py` | `python auth.py` | 10/10 |

---

## 📄 License

Apache 2.0 License. See [LICENSE](LICENSE) for details.

---

<p align="center">
<strong>🦞 ButterClaw v0.6.7 — The Agentic SOC (The Arsenal Hardening)</strong><br>
<em>Deterministic guardrails for probabilistic reasoning. Evaluation before execution.</em><br>
<em>The Sentinel never goes silent. We watch the room.</em><br>
<em>Built with unautclated telemetry. Yes, unautclated. 🦞</em><br>
<a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

# 🦞 ButterClaw v0.6.3: The Exoskeleton (Deployment Packaging)

Version 0.6.3 — May 1, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and API key hashes into cryptographic garbage if a breach is detected. Now with **deterministic policy guardrails**, **external alert dispatch**, and **production-ready deployment packaging** — the Sentinel ships anywhere. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.6.3?

**Deployment Packaging** — The Exoskeleton is battle-tested. Now it needs to leave the lab. v0.6.3 adds everything required to deploy ButterClaw to production: centralized configuration, Docker containerization, systemd service management, nginx TLS termination, and automated backup/restore — all without adding a single new pip dependency.

### ⚙️ Centralized Configuration (`config.py`)

Single source of truth for all runtime configuration across all 5 modules. No more patching 5 files to change a database path.

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
```
Environment Variables (highest) → .env File → Hardcoded Defaults (lowest)
```

```python
# Usage — identical across all 5 modules:
from config import cfg

db_path = cfg.DB_PATH           # unified across server, auth, policy, alert, vault
port = cfg.PORT                 # was hardcoded 5000
confidence = cfg.CONFIDENCE_THRESHOLD  # was hardcoded 0.6
```

**Key features:**
- `BUTTERCLAW_` prefix on all env vars — no collision with system vars
- `_validate()` at import time — fail-fast on bad config
- `to_dict(redact_secrets=True)` — API-safe config export
- `.env` parser built on stdlib — no python-dotenv dependency
- Env vars never overridden by `.env` (12-factor compliance)

### 🐳 Docker Deployment

Three-container production stack:

| Container | Role | Health Check |
|-----------|------|-------------|
| **butterclaw** | Main application (Flask + all modules) | `healthcheck.py` → `/api/health` |
| **ollama** | Local LLM inference | `/api/tags` endpoint |
| **nginx** | TLS termination + reverse proxy + static files | Upstream health |

```bash
# Production deployment
docker compose up -d

# Development (hot-reload, no nginx)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# View logs
docker compose logs -f butterclaw
```

**Key features:**
- Non-root `butterclaw` user inside container
- GPU passthrough via `nvidia-container-toolkit` (CPU fallback automatic)
- Named volumes for SQLite persistence and Ollama model cache
- JSON-file logging with 10MB rotation
- `HEALTHCHECK` directive for orchestrator integration

### 🖥️ systemd Deployment (Bare-Metal VPS)

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
- `ProtectSystem=strict` — filesystem read-only except working directory
- `NoNewPrivileges=true` — prevent privilege escalation
- `PrivateTmp=true` — isolated temp directory
- `Restart=on-failure` with 5s delay

### 💾 Backup & Restore

```bash
# Create timestamped backup (SQLite .backup + .env)
./scripts/backup.sh

# List available backups
./scripts/restore.sh

# Restore from specific backup
./scripts/restore.sh backups/butterclaw-backup-20260420-1200.tar.gz
```

- SQLite `.backup` command (atomic — never `cp` on a live DB)
- Auto-prunes old backups (keeps last 7)
- Includes `.env` configuration in archive

### 🔒 Nginx TLS Termination

- HTTP → HTTPS redirect
- TLSv1.2/1.3 with ECDHE cipher suites
- HSTS (1 year), X-Content-Type-Options, X-Frame-Options
- SSE-specific proxy: `proxy_buffering off` + 24h timeout
- Static file serving for dashboard HTML
- 300s read timeout for Brain inference

---

## 🔔 Alert Dispatcher (v0.6.2)

A security monitoring system that can't *reach* its operator is just a log file with extra steps. The Alert Dispatcher pushes notifications to external channels so the operator knows the moment something happens, even if nobody is watching the dashboard.

### Multi-Channel Alert Routing

5 channel types, all built on Python stdlib (zero new pip dependencies):

| Channel | Transport | Payload Format |
|---------|-----------|----------------|
| **Webhook** | HTTP POST + HMAC-SHA256 signature | JSON with event_type, severity, context |
| **Discord** | Discord webhook API | Rich embed with color-coded severity sidebar |
| **ntfy** | ntfy.sh or self-hosted | Push with title, body, priority, tags |
| **SMTP** | smtplib | Email with structured plain-text body |
| **Gotify** | Self-hosted push API | Title + message + priority (1-10) |

### 9 Alert Event Types

| Event | When It Fires | Severity |
|-------|--------------|----------|
| `verdict_critical` | Brain or Policy returned CRITICAL | 🔴 Critical |
| `verdict_warning` | Brain returned WARNING (>= 50% confidence) | 🟡 Warning |
| `gibson_triggered` | Automatic Gibson from ChainExecutor | 🔴 Critical |
| `gibson_manual` | Manual Gibson via `/api/rotate-keys` | 🔴 Critical |
| `policy_override` | Policy Engine overrode Brain verdict | 🟡 Warning |
| `policy_blocked` | Policy Engine blocked request or tool | 🟡 Warning |
| `auth_brute_force` | 5+ auth failures from one IP in 60s | 🔴 Critical |
| `mcp_offline` | MCP process alive→dead transition | 🔴 Critical |
| `system_startup` | Server started successfully | 🟢 Info |

---

## 🛡️ Policy Engine (v0.6.1)

Deterministic guardrails for the probabilistic Brain. Implements the DRIFT framework pattern (NeurIPS 2025) — a Dynamic Validator that constrains the Brain's probabilistic reasoning with rules that say *"if X, then always Y"* — no reasoning required.

### 3-Scope Filter Pipeline

| Scope | When It Fires | What It Can Do |
|-------|--------------|----------------|
| **Pre-Brain** | Before the LLM is called | Short-circuit to CRITICAL or BENIGN without burning inference time |
| **Post-Brain** | After the LLM returns a verdict | Override, escalate, downgrade, or require higher confidence |
| **Pre-Tool** | Before each MCP tool call in a chain | Block specific tools via allowlist/blocklist |

**16 safe condition operators** — all use whitelist dispatch, no `eval()`:
`contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `regex_match`, `greater_than`, `less_than`, `greater_equal`, `less_equal`, `in_list`, `not_in_list`, `length_gt`, `length_lt`

---

## 🔐 API Gateway & Authentication (v0.6.0)

Every endpoint protected by role-based access control with HMAC-SHA256 API keys and session tokens.

| Tier | Access Level | Use Case |
|------|-------------|----------|
| **Admin** | Full access — vault, Gibson, key management, config | System owner |
| **Operator** | Analyze threats, read settings, start OAuth | Active operators |
| **Viewer** | Read-only — logs, events, status, SSE stream | Monitoring dashboards |

---

## 💀 Gibson Kill Switch

The nuclear option. When triggered, ButterVault physically shreds all credentials into cryptographic garbage. In v0.6.2+, the Alert Dispatcher fires notifications BEFORE vault destruction — alert-then-burn.

```
Gibson Triggered:
  1. dispatch_alert("gibson_triggered")    ← alert fires
  2. _dispatch_worker → all channels       ← notifications sent
  3. buttervault.butter_keys()             ← vault destroyed
  4. auth.destroy_all_api_keys()           ← auth destroyed
  5. Operator receives notification         ← notification arrives
```

**What Survives Gibson:**
```
DESTROYED by Gibson:           SURVIVES Gibson:
├── vault table (API keys)     ├── policies table
├── oauth_tokens table         ├── policy_events table
├── api_keys table             ├── alert_channels table
├── session cache              ├── alert_rules table
└── OS keyring master key      ├── alert_history table
                               ├── mcp_events table
                               ├── logs table
                               └── config.py / .env (filesystem)
```

---

## 🏗️ Architecture

**The Exoskeleton — Layered Defense:**
```
┌─────────────────────────────────────────────────┐
│  Deployment Layer (v0.6.3)                      │
│  Docker, systemd, nginx, config.py, backup      │
├─────────────────────────────────────────────────┤
│  Alert Layer (v0.6.2)                           │
│  5 channels, 9 event types, HMAC signing        │
├─────────────────────────────────────────────────┤
│  Policy Layer (v0.6.1)                          │
│  3-scope pipeline, 16 operators, DRIFT pattern  │
├─────────────────────────────────────────────────┤
│  Auth Layer (v0.6.0)                            │
│  HMAC-SHA256 keys, 3-tier RBAC, sessions        │
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
|-----------|------|-------|---------|------|
| Config | `config.py` | ~480 | v0.6.3 | Centralized env-driven configuration |
| Server | `server.py` | ~1,200 | v0.6.3 | Flask API, Brain, ChainExecutor |
| Auth | `auth.py` | ~890 | v0.6.0 | API gateway, RBAC, session tokens |
| Policy Engine | `policy_engine.py` | ~350 | v0.6.1 | Deterministic guardrails |
| Alert Dispatcher | `alert_dispatcher.py` | ~1,566 | v0.6.2 | Push notifications |
| ButterVault | `buttervault.py` | ~400 | v0.5.2 | Encrypted credentials, Gibson |
| MCP Client | `butterclaw_mcp.py` | ~300 | v0.4.0 | Tool definitions |
| MCP Transport | `mcp_transport.py` | ~250 | v0.5.0 | SSE/stdio transport |
| OAuth Config | `oauth_config.py` | ~60 | v0.5.2 | OAuth provider templates |
| Watcher | `watcher.py` | ~150 | v0.1.0 | OS telemetry collection |

---

## 📡 API Reference

### Auth Endpoints (7 routes — v0.6.0)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | public | Exchange API key for session token |
| POST | `/api/auth/logout` | any | Clear session cookie |
| GET | `/api/auth/whoami` | any | Current identity |
| GET | `/api/auth/keys` | admin | List all API keys |
| POST | `/api/auth/keys` | admin | Create new API key |
| DELETE | `/api/auth/keys/<id>` | admin | Revoke API key |
| DELETE | `/api/auth/keys/<id>/purge` | admin | Permanently delete key |

### Policy Endpoints (8 routes — v0.6.1)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
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
|--------|----------|------|-------------|
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
|--------|----------|------|-------------|
| POST | `/api/analyze` | operator | Analyze threat payload |
| GET | `/api/health` | public | System health + instance info (enhanced v0.6.3) |
| GET | `/api/config` | admin | Resolved config (redacted secrets) (new v0.6.3) |
| GET | `/api/stream` | viewer | SSE event stream |
| GET | `/api/logs` | viewer | Query log history |

### MCP Endpoints (6 routes — v0.5.0+)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/api/mcp/tools` | viewer | List available MCP tools |
| POST | `/api/mcp/restart` | admin | Restart MCP process |
| GET | `/api/mcp/status` | viewer | MCP process health |
| GET | `/api/events` | viewer | Query event ledger |
| GET | `/api/events/count` | viewer | Event ledger count |
| GET | `/api/settings` | viewer | Server settings |

### Vault & OAuth Endpoints (10 routes — v0.5.x)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
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

**Total: 43 API routes** (7 Auth + 8 Policy + 13 Alert + 5 Core + 6 MCP + 10 Vault, reduced from 49 to account for shared endpoints — some endpoints registered across modules)

---

## 📁 Project Structure

```
butterclaw/
├── server.py                  # Flask API + Brain + ChainExecutor (v0.6.3)
├── config.py                  # Centralized configuration (v0.6.3)
├── auth.py                    # API gateway + RBAC (v0.6.0)
├── policy_engine.py           # Deterministic guardrails (v0.6.1)
├── alert_dispatcher.py        # Push notifications (v0.6.2)
├── buttervault.py             # Encrypted vault + Gibson (v0.5.2)
├── butterclaw_mcp.py          # MCP tool definitions (v0.4.0)
├── mcp_transport.py           # SSE/stdio transport (v0.5.0)
├── oauth_config.py            # OAuth provider templates (v0.5.2)
├── watcher.py                 # OS telemetry collector (v0.1.0)
├── index.html                 # Main dashboard (v0.6.3)
├── routing.html               # Advanced config dashboard (v0.6.3)
├── requirements.txt           # pip dependencies (v0.6.3)
├── .env.example               # Environment template (v0.6.3)
├── Dockerfile                 # Container build (v0.6.3)
├── docker-compose.yml         # Production orchestration (v0.6.3)
├── docker-compose.dev.yml     # Dev overlay (v0.6.3)
├── .dockerignore              # Build context exclusions (v0.6.3)
├── nginx/
│   └── butterclaw.conf        # Reverse proxy config (v0.6.3)
├── scripts/
│   ├── healthcheck.py         # Docker health check (v0.6.3)
│   ├── backup.sh              # Backup utility (v0.6.3)
│   └── restore.sh             # Restore utility (v0.6.3)
├── systemd/
│   └── butterclaw.service     # systemd unit file (v0.6.3)
└── butterclaw.db              # SQLite database (auto-created)
```

---

## 🔒 Security Architecture

| Layer | Mechanism | Version |
|-------|-----------|---------|
| **TLS** | nginx reverse proxy with TLSv1.2/1.3, ECDHE ciphers, HSTS | v0.6.3 |
| **Container** | Non-root user, read-only filesystem, ProtectSystem=strict | v0.6.3 |
| **Authentication** | HMAC-SHA256 API keys, session tokens, httpOnly cookies | v0.6.0 |
| **Authorization** | 3-tier RBAC (admin/operator/viewer) | v0.6.0 |
| **Policy** | Deterministic pre-brain/post-brain/pre-tool guardrails | v0.6.1 |
| **Alerting** | 5 external channels, HMAC-signed webhooks, auth brute-force detection | v0.6.2 |
| **Vault** | Fernet encryption, OS keyring, Gibson Kill Switch | v0.5.2 |
| **Analysis** | Local LLM reasoning + confidence scoring + chain safety rails | v0.5.0+ |
| **Monitoring** | Event Ledger + Policy Events + Alert History — 3 audit trails | v0.5.0+ |

---

## 🛡️ OWASP Agentic Security Initiative (ASI) Coverage

| ASI Threat | ButterClaw Mitigation |
|------------|----------------------|
| ASI-01: Excessive Agency | Brain confidence gating + ChainExecutor MAX_STEPS=10 + Policy Engine pre-tool scope (v0.5.0+) |
| ASI-02: Insufficient Access Control | 3-tier RBAC + per-key rate limiting + HMAC-SHA256 auth (v0.6.0) |
| ASI-03: Knowledge Poisoning | Local-first LLM — no external training data ingestion. Watcher monitors OS telemetry, not user content (v0.1.0+) |
| ASI-04: Identity & Credential Abuse | ButterVault + OAuth lifecycle + Gibson (v0.5.2) |
| ASI-05: Cascading Failures | ChainExecutor safety rails: MAX_STEPS=10, TIMEOUT=60s (v0.5.1) |
| ASI-06: Indirect Prompt Injection | Policy Engine pattern matching on payloads (v0.6.1) |
| ASI-07: Insufficient Monitoring | Event Ledger + Policy Events + Alert History — 3 audit trails (v0.5.0+) |
| ASI-09: Inadequate Logging | 3 audit trails + external notification via Alert Dispatcher (v0.6.2) |
| ASI-10: Uncontrolled Escalation | Gibson panic destroys all credentials atomically + alert fires before destruction (v0.6.2) |

---

## 📋 Version History

| Version | Codename | Date | Milestone |
|---------|----------|------|-----------|
| **v0.6.3** | The Exoskeleton: Deployment Packaging | 2026-04-20 | config.py, Docker, systemd, nginx, backup/restore |
| **v0.6.2** | The Exoskeleton: Alert Dispatcher | 2026-04-20 | 5 channels, 9 events, HMAC signing, brute-force detection |
| **v0.6.1** | The Exoskeleton: Policy Engine | 2026-04-19 | 3-scope pipeline, 16 operators, DRIFT pattern |
| **v0.6.0** | The Exoskeleton: API Gateway & Auth | 2026-04-18 | HMAC-SHA256, 3-tier RBAC, session tokens |
| **v0.5.2** | ButterVault OAuth | 2026-04-16 | OAuth 2.0 flows, token refresh, Gibson destroys OAuth |
| **v0.5.1** | Tool Chaining | 2026-04-16 | ChainExecutor, multi-step execution, safety rails |
| **v0.5.0** | The Nervous System | 2026-04-13 | Event Ledger, SSE Transport, MCP Manager, Memory |
| **v0.4.x** | MCP Transport Refactor | 2026-04-9 | Modular transport, JSON-RPC, CSP fixes |
| **v0.3.x** | Routing Dashboard | 2026-04-01 | routing.html, advanced config UI |
| **v0.2.0** | ButterVault | 2026-03-18 | Encrypted credentials, Gibson Kill Switch |
| **v0.1.0** | Initial Release | 2026-03-17 | Core analysis, watcher, dashboard, MCP tools |

---

## 🗺️ Roadmap — The Exoskeleton (v0.6.x)

| Pillar | Version | Status | Deliverable |
|--------|---------|--------|-------------|
| 1. API Gateway & Auth | v0.6.0 | ✅ Delivered | HMAC-SHA256, RBAC, sessions |
| 2. Policy Engine | v0.6.1 | ✅ Delivered | 3-scope pipeline, DRIFT pattern |
| 3. Alert Dispatcher | v0.6.2 | ✅ Delivered | 5 channels, HMAC webhooks |
| 4. Deployment Packaging | v0.6.3 | ✅ Delivered | Docker, systemd, config.py |

**The Exoskeleton is complete.** All four pillars are shipped.

---

## ⚡ Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw && git checkout dev

# Configure
cp .env.example .env
# Edit .env — set BUTTERCLAW_INSTANCE_ID, CORS_ORIGINS, etc.

# TLS certs (production)
mkdir -p nginx/certs
# Place fullchain.pem and privkey.pem in nginx/certs/

# Launch
docker compose up -d

# Verify
docker compose ps
curl -k https://localhost/api/health
```

### systemd (Bare-Metal VPS)

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw && git checkout dev

# Install dependencies
pip install -r requirements.txt

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:4b

# Configure
cp .env.example /etc/butterclaw.env
# Edit /etc/butterclaw.env

# Install service
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw

# Verify
journalctl -u butterclaw -f
curl http://localhost:5000/api/health
```

### Bare-Metal (Development)

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw && git checkout dev

pip install -r requirements.txt
ollama pull gemma3:4b

cp .env.example .env
python server.py
```

On first run, the bootstrap CLI prints your admin API key to the terminal. Save it — it's shown exactly once.

---

## 📊 Diagnostic Tests

All modules include standalone diagnostic suites:

| Module | Command | Tests |
|--------|---------|-------|
| `config.py` | `python config.py` | 21/21 |
| `alert_dispatcher.py` | `python alert_dispatcher.py` | 14/14 |
| `policy_engine.py` | `python policy_engine.py` | 16/16 |
| `auth.py` | `python auth.py` | 10/10 |

-----

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

-----

*Built by [butterclaw.tech](https://butterclaw.tech) — an independent, original agent platform.*

---

<p align="center">
  <strong>🦞 ButterClaw v0.6.3 — The Exoskeleton (Deployment Packaging) 🦞</strong><br>
  <em>Deterministic guardrails for probabilistic reasoning. Evaluation before Execution.</em><br>
  <em>The Sentinel never goes silent.</em><br>
  <a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

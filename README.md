# 🦞 ButterClaw v0.6.1: The Exoskeleton (Policy Engine)

Version 0.6.1 — April 19, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and API key hashes into cryptographic garbage if a breach is detected. Now with **deterministic policy guardrails** that constrain the probabilistic Brain. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.6.1?

**Policy Engine** — The Brain is probabilistic. It reasons about novel threats using context, history, and pattern recognition. But probabilistic systems have failure modes: hallucinated confidence, missed patterns on known-bad payloads, overreaction to benign noise. The Policy Engine adds **deterministic guardrails** that constrain the Brain with rules that say *"if X, then always Y"* — no reasoning required.

This implements the DRIFT framework pattern (NeurIPS 2025) — a Secure Planner constructs the trajectory, a Dynamic Validator monitors deviations from policy. ButterClaw already had the Planner (Brain + ChainExecutor). v0.6.1 adds the Validator.

### 🛡️ 3-Scope Filter Pipeline

Policies evaluate at three distinct points in the analysis pipeline:

| Scope | When It Fires | What It Can Do |
|-------|--------------|----------------|
| **Pre-Brain** | Before the LLM is called | Short-circuit to CRITICAL or BENIGN without burning inference time. Block the request entirely. |
| **Post-Brain** | After the LLM returns a verdict | Override, escalate, downgrade, or require higher confidence for the Brain's decision. |
| **Pre-Tool** | Before each MCP tool call in a chain | Block specific tools. Per-tool allowlist/blocklist. |

### 📋 Policy Rules

Each policy is a single condition evaluated against context fields available at its scope:

```json
{
  "name": "Block external websocket exfiltration",
  "scope": "pre_brain",
  "priority": 10,
  "condition": {
    "field": "payload",
    "operator": "regex_match",
    "value": "wss?://[^\\s]*\\.(net|io|xyz|tk|ml)"
  },
  "action": "override_critical",
  "description": "External websocket to suspicious TLD — pre-brain escalation"
}
```

16 safe condition operators: `contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `regex_match`, `greater_than`, `less_than`, `greater_equal`, `less_equal`, `in_list`, `not_in_list`, `length_gt`, `length_lt`. All use whitelist dispatch — no `eval()`.

### 🧪 Dry-Run Testing

Test any payload against all policies without executing actions or logging events:

```bash
curl -X POST http://127.0.0.1:5000/api/policies/test \
  -H "Authorization: Bearer bc_your_key" \
  -H "Content-Type: application/json" \
  -d '{"payload": "wss://evil.xyz/exfil", "threat_type": "test"}'
```

Returns which policies would fire at each scope — pre_brain, post_brain, and pre_tool.

### 🔐 API Gateway & Authentication (v0.6.0)

Every endpoint is protected by role-based access control with HMAC-SHA256 API keys and session tokens. Zero new pip dependencies.

**Three-tier role hierarchy:**

| Tier | Access Level | Use Case |
|------|-------------|----------|
| **Admin** | Full access — vault, Gibson, MCP restart, settings, key management, policy CRUD | System owner |
| **Operator** | Analyze threats, read settings, ping MCP, start OAuth flows, dry-run policy tests | Active Sentinel operators |
| **Viewer** | Read-only — logs, events, status, tools, SSE stream, policy list, policy events | Monitoring dashboards |

### ☢️ Gibson Destroys Everything (But Not Policies)

The panic button atomically destroys **three credential layers** but leaves policies intact:

```
butter_keys()
├── UPDATE vault SET ciphertext = garbage           ← Static API keys
├── UPDATE oauth_tokens SET ciphertext = garbage    ← OAuth payloads
├── auth.destroy_all_api_keys()                     ← API key hashes + sessions
└── policies table: UNTOUCHED                       ← Config survives Gibson
    policy_events table: UNTOUCHED                  ← Audit trail preserved
```

Policies survive Gibson. This is correct behavior — if the Gibson fires, you want the policies that triggered or detected the breach to still be there for the post-mortem audit. Policies are operational configuration, not sensitive data.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    ButterClaw v0.6.1                      │
│                                                          │
│  ┌─────────┐    ┌──────────┐    ┌───────────────────┐   │
│  │ Watcher  │───▶│  Flask   │───▶│  Policy Engine    │   │
│  │ (OS Tel) │    │  API     │    │  (Pre-Brain)      │   │
│  └─────────┘    │  Gateway  │    └───────┬───────────┘   │
│                  │  + Auth   │            │               │
│                  └────┬─────┘    ┌───────▼───────────┐   │
│                       │          │   Brain (Ollama)   │   │
│                  ┌────▼─────┐    │   Gemma 4 e2b     │   │
│                  │ Dashboard │    └───────┬───────────┘   │
│                  │ (Auth'd) │            │               │
│                  └──────────┘    ┌───────▼───────────┐   │
│                                  │  Policy Engine    │   │
│                                  │  (Post-Brain)     │   │
│                                  └───────┬───────────┘   │
│                                          │               │
│                                  ┌───────▼───────────┐   │
│                                  │  ChainExecutor    │   │
│                                  │  + Pre-Tool Gate  │   │
│                                  └───────┬───────────┘   │
│                                          │               │
│                                  ┌───────▼───────────┐   │
│                                  │   MCP Manager     │   │
│                                  │   (The Claws)     │   │
│                                  └───────┬───────────┘   │
│                                          │               │
│                                  ┌───────▼───────────┐   │
│                                  │  ButterVault      │   │
│                                  │  + OAuth Store    │   │
│                                  │  + API Keys       │   │
│                                  └───────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

| Component | File | Role |
|-----------|------|------|
| **The Watcher** | `watcher.py` | OS-level telemetry collector. Monitors processes, network connections, and filesystem changes. Feeds raw signals to the API. |
| **The API Gateway** | `server.py` + `auth.py` | Flask server with role-based authentication. Routes payloads through the policy engine and Brain, executes MCP tool chains, manages the Event Ledger, coordinates OAuth flows, and serves the real-time SSE dashboard. |
| **The Policy Engine** | `policy_engine.py` | Deterministic guardrails for the probabilistic Brain. 3-scope filter pipeline (pre-brain, post-brain, pre-tool) with 16 safe condition operators, priority-based evaluation, and policy event audit logging. |
| **The Brain** | Ollama + Gemma 4 e2b | Local LLM reasoning engine. Analyzes payloads through five logic gates (Intent, Origin, Behavior, Sensitivity, Impact). Outputs structured verdicts with optional multi-step tool chains. |
| **The Claws** | `butterclaw_mcp.py` | MCP tool server exposing kinetic response tools (Gibson Kill Switch, key rotation, network blocking). Executes via stdio or SSE transport. |
| **The Vault** | `buttervault.py` | Fernet-encrypted credential storage using OS keyring. Stores static API keys, OAuth token payloads, and is the master key source for session token signing. Gibson destroys all credential layers atomically. |
| **The Auth Layer** | `auth.py` | HMAC-SHA256 API key management, role-based access control, session tokens, per-key rate limiting. Zero new dependencies. |
| **Transport Layer** | `mcp_transport.py` | Decoupled I/O layer. `StdioTransport` for local execution, `SSETransport` for remote MCP clients. Auth-agnostic by design. |
| **Provider Registry** | `oauth_config.py` | Static registry of OAuth provider metadata (Google Cloud, GitHub). No dynamic logic — pristine data file. |

---

## 📡 API Endpoints

### Authentication (v0.6.0)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/login` | POST | Public | Exchange API key for session token |
| `/api/auth/logout` | POST | Public | Clear session cookie |
| `/api/auth/whoami` | GET | Viewer | Current identity (role, label, key_id) |
| `/api/auth/keys` | GET | Admin | List all API keys (hashes redacted) |
| `/api/auth/keys` | POST | Admin | Create new API key with role and label |
| `/api/auth/keys/<id>` | DELETE | Admin | Revoke (disable) an API key |
| `/api/auth/keys/<id>/purge` | DELETE | Admin | Permanently delete API key record |

### Policy Engine (v0.6.1)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/policies` | GET | Viewer | List all policies (optional `?scope=`, `?enabled=` filters) |
| `/api/policies` | POST | Admin | Create a new policy rule |
| `/api/policies/<id>` | GET | Viewer | Fetch a single policy by ID |
| `/api/policies/<id>` | PUT | Admin | Update a policy rule |
| `/api/policies/<id>` | DELETE | Admin | Permanently delete a policy |
| `/api/policies/<id>/toggle` | POST | Admin | Enable/disable without deleting |
| `/api/policies/test` | POST | Operator | Dry-run a payload against all policies |
| `/api/policies/events` | GET | Viewer | Query policy event audit log |

### Core Analysis

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | Public | Health check — `{"status": "ok", "version": "0.6.1"}` |
| `/api/analyze` | POST | Operator | Submit payload for threat analysis (now with policy pipeline) |
| `/api/logs` | GET | Viewer | Query the oopsie log |
| `/api/stream` | GET | Viewer | SSE real-time dashboard updates |

### MCP Management

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/mcp/status` | GET | Viewer | MCP process health and transport mode |
| `/api/mcp/tools` | GET | Viewer | Discovered MCP tools from handshake |
| `/api/mcp/ping` | GET | Operator | MCP liveness probe |
| `/api/mcp/restart` | POST | Admin | Kill and restart MCP child process |
| `/api/mcp/events` | GET | Viewer | Event ledger with filters (?limit=, ?tool=, ?status=, ?since=) |
| `/api/mcp/events/<id>` | GET | Viewer | Single event with full result payload |

### ButterVault, OAuth & Settings

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/vault/key` | POST | Admin | Store an API key in the Vault |
| `/api/vault/status` | GET | Viewer | Vault key presence check |
| `/api/rotate-keys` | POST | Admin | Trigger Gibson Kill Switch |
| `/api/shield` | POST | Admin | Toggle shield on/off |
| `/api/vault/oauth/start/<provider>` | GET | Operator | Initiate OAuth 2.0 flow with CSRF state |
| `/api/vault/oauth/callback` | GET | Public | Handle provider redirect, exchange code for tokens |
| `/api/vault/oauth/status` | GET | Viewer | Connection status of all OAuth-capable providers |
| `/api/vault/oauth/revoke/<provider>` | POST | Admin | Revoke token at provider, remove from Vault |
| `/api/settings` | GET | Operator | Read current settings (paranoia, model, gates, routing) |
| `/api/settings` | POST | Admin | Modify settings |

---

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) with Gemma 4 e2b model
- OS keyring support (macOS Keychain, Windows Credential Manager, or Linux SecretService)

### Installation

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw
pip install -r requirements.txt
ollama pull butterclaw-optimized:latest
```

### First Run

```bash
# Terminal 1 — Start the server
python server.py

# On first boot, you'll see:
# 🔐 [AUTH] No admin API keys found. Bootstrapping...
# ╔══════════════════════════════════════════════════════╗
# ║  ADMIN API KEY (shown once — save this now):         ║
# ║  bc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx                 ║
# ╚══════════════════════════════════════════════════════╝
#    Policy Engine: ENABLED

# Terminal 2 — Start the watcher
python watcher.py
```

### Dashboard Login

1. Open `http://127.0.0.1:5000` in your browser
2. Enter the bootstrap admin API key from the terminal output
3. The dashboard unlocks with full admin access

### Creating Additional Keys

```bash
# Via curl (requires admin key)
curl -X POST http://127.0.0.1:5000/api/auth/keys \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"role": "operator", "label": "Dashboard User"}'
```

### Creating Policies

```bash
# Pre-brain: Block known-bad websocket exfiltration patterns
curl -X POST http://127.0.0.1:5000/api/policies \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Block external websocket exfil",
    "scope": "pre_brain",
    "priority": 10,
    "condition": {"field": "payload", "operator": "regex_match", "value": "wss?://[^\\s]*\\.(net|io|xyz|tk|ml)"},
    "action": "override_critical",
    "description": "External websocket to suspicious TLD"
  }'

# Pre-brain: Fast-track known-safe heartbeat payloads (skip Brain entirely)
curl -X POST http://127.0.0.1:5000/api/policies \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Fast-track heartbeats",
    "scope": "pre_brain",
    "priority": 5,
    "condition": {"field": "threat_type", "operator": "equals", "value": "heartbeat_ping"},
    "action": "override_benign",
    "description": "Heartbeat pings are always benign"
  }'

# Post-brain: Require 95%+ confidence for payloads touching .env files
curl -X POST http://127.0.0.1:5000/api/policies \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High confidence for env access",
    "scope": "post_brain",
    "priority": 20,
    "condition": {"field": "payload", "operator": "contains", "value": ".env"},
    "action": "require_confidence",
    "action_params": {"min_confidence": 95},
    "description": "Payloads touching .env need 95%+ confidence for CRITICAL"
  }'

# Dry-run test: See which policies would fire
curl -X POST http://127.0.0.1:5000/api/policies/test \
  -H "Authorization: Bearer bc_your_key" \
  -H "Content-Type: application/json" \
  -d '{"payload": "wss://evil.xyz/exfil", "threat_type": "test"}'
```

### Setting Up OAuth (Google Cloud)

```bash
# 1. Store your Google Cloud OAuth credentials in the Vault
curl -X POST http://127.0.0.1:5000/api/vault/key \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"provider": "google_client_id", "key": "your-client-id.apps.googleusercontent.com"}'

curl -X POST http://127.0.0.1:5000/api/vault/key \
  -H "Authorization: Bearer bc_your_admin_key" \
  -H "Content-Type: application/json" \
  -d '{"provider": "google_client_secret", "key": "GOCSPX-your-secret"}'

# 2. Start the OAuth flow from the dashboard Vault panel
#    Click "Connect via OAuth" → Google login → tokens sealed automatically
```

---

## 🗂️ File Structure

```
butterclaw/
├── server.py              # Flask API + Brain routing + Policy hooks + Event Ledger + OAuth + Auth
├── auth.py                # API Gateway: keys, roles, sessions, rate limiting (v0.6.0)
├── policy_engine.py       # Deterministic guardrails: 3-scope pipeline, CRUD, audit (v0.6.1)
├── watcher.py             # OS telemetry collector
├── butterclaw_mcp.py      # MCP tool server (Gibson, key rotation, network tools)
├── buttervault.py         # Encrypted credential storage (API keys + OAuth tokens)
├── mcp_transport.py       # Stdio + SSE transport abstraction
├── oauth_config.py        # Static OAuth provider registry
├── index.html             # Main dashboard (oopsie log, vault, threat analysis, policy badges)
├── routing.html           # Advanced config (gates, MCP, ledger, transport, policy management)
├── blog-v05.html          # v0.5 release blog post
├── butterclaw.db          # SQLite database (auto-created)
└── requirements.txt       # Python dependencies
```

---

## 🔒 Security Model

### Defense in Depth

| Layer | Component | What It Protects |
|-------|-----------|-----------------:|
| **Perimeter** | `auth.py` — API Gateway | Every endpoint role-gated; HMAC keys; session tokens; per-key rate limiting |
| **Deterministic** | `policy_engine.py` — Policy Engine | Pre-brain pattern matching; post-brain verdict validation; pre-tool gates; audit trail |
| **Reasoning** | Brain (Gemma 4 e2b) | Five-gate analysis: Intent, Origin, Behavior, Sensitivity, Impact |
| **Execution** | ChainExecutor + Pre-Tool Policy Gate | MAX_STEPS=10, TIMEOUT=60s, no eval(), condition whitelist, per-tool policy blocking |
| **Credentials** | ButterVault | Fernet + OS keyring encryption; OAuth lifecycle; atomic destruction |
| **Audit** | Event Ledger + Policy Events | Append-only logs of every MCP invocation and every policy match |
| **Panic** | Gibson Kill Switch | Atomically destroys vault + OAuth tokens + API key hashes + sessions (policies survive) |

### OWASP Agentic Security Issues (ASI) Coverage

| OWASP ASI | ButterClaw Coverage |
|-----------|-------------------|
| ASI-01: Prompt Injection | Brain analysis with 85% confidence threshold + Pre-Brain policy filter for known patterns (v0.6.1) |
| ASI-02: Excessive Agency | Pre-Tool policy gate blocks unauthorized tool calls in chains (v0.6.1) |
| ASI-03: Insufficient Access Controls | API Gateway with role-based auth (v0.6.0) |
| ASI-04: Identity & Credential Abuse | ButterVault + OAuth lifecycle + Gibson (v0.5.2) |
| ASI-05: Cascading Failures | ChainExecutor safety rails (v0.5.1) |
| ASI-06: Indirect Prompt Injection | Policy Engine pattern matching on payloads (v0.6.1) |
| ASI-07: Insufficient Monitoring | Event Ledger with chain grouping (v0.5.0) + Policy event audit log (v0.6.1) |

---

## 📋 Version History

| Version | Codename | Date | Highlights |
|---------|----------|------|------------|
| **0.6.1** | **The Exoskeleton (Policy Engine)** | 2026-04-19 | Deterministic 3-scope policy pipeline, 16 operators, CRUD API, dry-run testing, policy management UI, policy badges |
| 0.6.0 | The Exoskeleton (Auth) | 2026-04-18 | API Gateway, HMAC auth, role-based access, session tokens, dashboard login |
| 0.5.2 | ButterVault OAuth | 2026-04-16 | OAuth 2.0 flow, encrypted token storage, automatic refresh, Gibson update |
| 0.5.1 | Tool Chaining | 2026-04-16 | ChainExecutor, conditional logic, ledger chain grouping, oopsie card links |
| 0.5.0 | The Nervous System | 2026-04-14 | Event Ledger, SSE Transport, Memory Injection, MCP Manager Factory |
| 0.4.1 | QA Stabilization | 2026-04-12 | CSP fixes, endpoint resolution, JSON truncation, diagnostic logic |
| 0.4.0 | MCP Transport Refactor | 2026-04-10 | Modular transport layer, butterclaw_mcp.py separation |
| 0.3.1 | CSP & Endpoint Fixes | 2026-04-08 | Content Security Policy compliance |
| 0.3.0 | Routing Dashboard | 2026-04-06 | routing.html advanced configuration |
| 0.2.0 | ButterVault | 2026-04-04 | Encrypted credential storage, Gibson Kill Switch |
| 0.1.0 | Initial Release | 2026-04-01 | Core engine, watcher, dashboard, MCP tools |

---

## 🗺️ Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| v0.5.0 — Event Ledger + SSE Transport | ✅ Delivered | Pillar 1 & 2 of The Nervous System |
| v0.5.1 — Tool Chaining | ✅ Delivered | Pillar 3: Multi-step MCP chain execution |
| v0.5.2 — ButterVault OAuth | ✅ Delivered | Pillar 4: OAuth 2.0 credential lifecycle |
| v0.6.0 — API Gateway & Auth | ✅ Delivered | Pillar 1 of The Exoskeleton: Role-based access control |
| **v0.6.1 — Policy Engine** | **✅ Delivered** | **Pillar 2: Deterministic pre-brain/post-brain/pre-tool guardrails** |
| v0.6.2 — Alert Dispatcher | 🔧 Next | Pillar 3: Webhook, email, and digest alerting for CRITICAL verdicts |
| v0.6.3 — Deployment Packaging | 📋 Planned | Pillar 4: Docker, docker-compose, TLS, systemd, env var config |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>🦞 ButterClaw v0.6.1 — The Exoskeleton</strong><br>
  <em>Deterministic guardrails for probabilistic reasoning. Evaluation before Execution.</em><br>
  <a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

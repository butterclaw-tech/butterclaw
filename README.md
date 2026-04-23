# 🦞 ButterClaw v0.6.0: The Exoskeleton (API Gateway & Authentication)

Version 0.6.0 — April 23, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and now **API key hashes** into cryptographic garbage if a breach is detected. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.6.0?

**The Exoskeleton** — v0.5 built The Nervous System (reasoning, memory, tool chaining, credential lifecycle). v0.6 builds the calcified outer shell that protects it from the outside world.

### 🔐 API Gateway & Authentication

ButterClaw's Flask API is no longer open. Every endpoint is protected by role-based access control with HMAC-SHA256 API keys and session tokens. Zero new pip dependencies — built entirely on Python stdlib.

**Three-tier role hierarchy:**

| Tier | Access Level | Use Case |
|------|-------------|----------|
| **Admin** | Full access — vault, Gibson, MCP restart, settings, key management | System owner |
| **Operator** | Analyze threats, read settings, ping MCP, start OAuth flows | Active Sentinel operators |
| **Viewer** | Read-only — logs, events, status, tools, SSE stream | Monitoring dashboards |

### 🔑 API Key Manager

HMAC-SHA256 API keys with per-key 16-byte random salts. Keys are hashed before storage — the plaintext is shown exactly once at creation and never persists. Constant-time comparison (`hmac.compare_digest()`) prevents timing side-channel attacks. 0.1s delay on failed login prevents brute-force enumeration.

### 🍪 Session Tokens

HMAC-signed JSON tokens with 1-hour TTL, issued on dashboard login. Stored in `httpOnly` + `SameSite=Strict` cookies to prevent XSS and CSRF. Session signing key derived from the ButterVault master key — Gibson destruction automatically invalidates all active sessions.

### 🛡️ Dashboard Login

Both `index.html` and `routing.html` now feature a full-screen login modal that blocks all dashboard interaction until authenticated. The `authFetch()` wrapper auto-injects the Bearer token on every API call and auto-redirects to the login modal on 401/403 responses. SSE connections pass the session token as a query parameter (since `EventSource` cannot set custom headers).

### ☢️ Gibson Destroys Everything (Updated)

The panic button now atomically destroys **three layers**:

```
butter_keys()
├── UPDATE vault SET ciphertext = garbage           ← Static API keys
├── UPDATE oauth_tokens SET ciphertext = garbage    ← OAuth payloads
└── auth.destroy_all_api_keys()                     ← API key hashes + sessions
```

After a Gibson event, all authentication is invalidated. The system requires a fresh `bootstrap_admin_key()` to re-enter.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    ButterClaw v0.6.0                      │
│                                                          │
│  ┌─────────┐    ┌──────────┐    ┌───────────────────┐   │
│  │ Watcher  │───▶│  Flask   │───▶│   Brain (Ollama)  │   │
│  │ (OS Tel) │    │  API     │    │   Gemma 4 e2b     │   │
│  └─────────┘    │  Gateway  │    └───────────────────┘   │
│                  │  + Auth   │              │             │
│                  └────┬─────┘              │             │
│                       │            ┌───────▼──────┐      │
│                  ┌────▼─────┐      │ ChainExecutor │      │
│                  │ Dashboard │      │ (Multi-Step)  │      │
│                  │ (Auth'd) │      └───────┬──────┘      │
│                  └──────────┘              │             │
│                                    ┌───────▼──────┐      │
│                                    │  MCP Manager  │      │
│                                    │  (The Claws)  │      │
│                                    └───────┬──────┘      │
│                                            │             │
│                                    ┌───────▼──────┐      │
│                                    │ ButterVault   │      │
│                                    │ + OAuth Store │      │
│                                    │ + API Keys    │      │
│                                    └──────────────┘      │
└──────────────────────────────────────────────────────────┘
```

| Component | File | Role |
|-----------|------|------|
| **The Watcher** | `watcher.py` | OS-level telemetry collector. Monitors processes, network connections, and filesystem changes. Feeds raw signals to the API. |
| **The API Gateway** | `server.py` + `auth.py` | Flask server with role-based authentication. Routes payloads to the Brain, executes MCP tool chains, manages the Event Ledger, coordinates OAuth flows, and serves the real-time SSE dashboard. |
| **The Brain** | Ollama + Gemma 4 e2b | Local LLM reasoning engine. Analyzes payloads through five logic gates (Intent, Origin, Behavior, Sensitivity, Impact). Outputs structured verdicts with optional multi-step tool chains. |
| **The Claws** | `butterclaw_mcp.py` | MCP tool server exposing kinetic response tools (Gibson Kill Switch, key rotation, network blocking). Executes via stdio or SSE transport. |
| **The Vault** | `buttervault.py` | Fernet-encrypted credential storage using OS keyring. Stores static API keys, OAuth token payloads, and is the master key source for session token signing. Gibson destroys all layers atomically. |
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

### Core Analysis

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | Public | Health check — `{"status": "ok", "version": "0.6.0"}` |
| `/api/analyze` | POST | Operator | Submit payload for threat analysis |
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

### ButterVault

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/vault/key` | POST | Admin | Store an API key in the Vault |
| `/api/vault/status` | GET | Viewer | Vault key presence check |
| `/api/rotate-keys` | POST | Admin | Trigger Gibson Kill Switch |
| `/api/shield` | POST | Admin | Toggle shield on/off |

### OAuth (v0.5.2)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/vault/oauth/start/<provider>` | GET | Operator | Initiate OAuth 2.0 flow with CSRF state |
| `/api/vault/oauth/callback` | GET | Public | Handle provider redirect, exchange code for tokens |
| `/api/vault/oauth/status` | GET | Viewer | Connection status of all OAuth-capable providers |
| `/api/vault/oauth/revoke/<provider>` | POST | Admin | Revoke token at provider, remove from Vault |

### Settings

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/settings` | GET | Operator | Read current settings (paranoia, model, gates, routing) |
| `/api/settings` | POST | Admin | Modify settings |

---

## ⚡ Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) with Gemma 4 e4b model
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
├── server.py              # Flask API + Brain routing + Event Ledger + OAuth + Auth integration
├── auth.py                # API Gateway: keys, roles, sessions, rate limiting (v0.6.0)
├── watcher.py             # OS telemetry collector
├── butterclaw_mcp.py      # MCP tool server (Gibson, key rotation, network tools)
├── buttervault.py         # Encrypted credential storage (API keys + OAuth tokens)
├── mcp_transport.py       # Stdio + SSE transport abstraction
├── oauth_config.py        # Static OAuth provider registry
├── index.html             # Main dashboard (oopsie log, vault, threat analysis)
├── routing.html           # Advanced config (gates, MCP, ledger, transport)
├── butterclaw.db           # SQLite database (auto-created)
└── requirements.txt       # Python dependencies
```

---

## 🔒 Security Model

### Defense in Depth

| Layer | Component | What It Protects |
|-------|-----------|-----------------|
| **Perimeter** | `auth.py` — API Gateway | Every endpoint role-gated; HMAC keys; session tokens; per-key rate limiting |
| **Reasoning** | Brain (Gemma 4 e2b) | Five-gate analysis: Intent, Origin, Behavior, Sensitivity, Impact |
| **Execution** | ChainExecutor | MAX_STEPS=10, TIMEOUT=60s, no eval(), condition whitelist |
| **Credentials** | ButterVault | Fernet + OS keyring encryption; OAuth lifecycle; atomic destruction |
| **Audit** | Event Ledger | Append-only log of every MCP tool invocation with chain grouping |
| **Panic** | Gibson Kill Switch | Atomically destroys vault + OAuth tokens + API key hashes + sessions |

### OWASP Agentic Security Issues (ASI) Coverage

| OWASP ASI | ButterClaw Coverage |
|-----------|-------------------|
| ASI-01: Prompt Injection | Brain analysis with 85% confidence threshold |
| ASI-03: Insufficient Access Controls | API Gateway with role-based auth (v0.6.0) |
| ASI-04: Identity & Credential Abuse | ButterVault + OAuth lifecycle + Gibson (v0.5.2) |
| ASI-05: Cascading Failures | ChainExecutor safety rails (v0.5.1) |
| ASI-07: Insufficient Monitoring | Event Ledger with chain grouping (v0.5.0) |

---

## 📋 Version History

| Version | Codename | Date | Highlights |
|---------|----------|------|------------|
| **0.6.0** | **The Exoskeleton** | 2026-04-18 | API Gateway, HMAC auth, role-based access, session tokens, dashboard login |
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
| **v0.6.0 — API Gateway & Auth** | **✅ Delivered** | **Pillar 1 of The Exoskeleton: Role-based access control** |
| v0.6.1 — Policy Engine | 🔧 Next | Pillar 2: Deterministic pre-brain/post-brain/pre-tool guardrails |
| v0.6.2 — Alert Dispatcher | 📋 Planned | Pillar 3: Webhook, email, and digest alerting for CRITICAL verdicts |
| v0.6.3 — Deployment Packaging | 📋 Planned | Pillar 4: Docker, docker-compose, TLS, systemd, env var config |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>🦞 ButterClaw v0.6.0 — The Exoskeleton</strong><br>
  <em>Built with unautclated telemetry. Evaluation before Execution.</em><br>
  <a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

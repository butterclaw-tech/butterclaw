# 🦞 ButterClaw v0.6.2: The Exoskeleton (Alert Dispatcher)

Version 0.6.2 — May 1, 2026 | [Official Dashboard: butterclaw.tech](https://butterclaw.tech)

Local-first kinetic response system for autonomous AI. ButterClaw uses a localized reasoning engine to catch obfuscated prompt injections. Featuring the **ButterVault**: a zero-trust credential locker that physically shreds your API keys, OAuth tokens, and API key hashes into cryptographic garbage if a breach is detected. Now with **deterministic policy guardrails** and **external alert dispatch** — the Sentinel never goes silent. **Evaluation before Execution.**

Traditional security perimeters fail when an authorized AI Agent is compromised via an **Indirect Prompt Injection** or **Cross-Site WebSocket Hijacking (CSWH)**. ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC), actively monitoring raw OS-level telemetry.

> **Note:** *ButterClaw is an original agent platform, implemented from the ground up. While it operates in the same problem space as other long‑running agent systems, it does not share code, commit history, or architectural lineage with those projects. It is designed as an independent system with its own runtime, memory model, and execution semantics.*

---

## 🚀 What's New in v0.6.2?

**Alert Dispatcher** — A security monitoring system that can't *reach* its operator is just a log file with extra steps. The Alert Dispatcher pushes notifications to external channels — webhooks, Discord, ntfy, SMTP email, Gotify — so the operator knows the moment something happens, even if nobody is watching the dashboard.

### 🔔 Multi-Channel Alert Routing

5 channel types, all built on Python stdlib (zero new pip dependencies):

| Channel | Transport | Payload Format |
|---------|-----------|----------------|
| **Webhook** | HTTP POST + HMAC-SHA256 signature | JSON with event_type, severity, context |
| **Discord** | Discord webhook API | Rich embed with color-coded severity sidebar |
| **ntfy** | ntfy.sh or self-hosted | Push with title, body, priority, tags |
| **SMTP** | smtplib | Email with structured plain-text body |
| **Gotify** | Self-hosted push API | Title + message + priority (1-10) |

### 📋 9 Alert Event Types

Every critical system event has an alert type:

| Event | When It Fires | Severity |
|-------|--------------|----------|
| `verdict_critical` | Brain or Policy returned CRITICAL | 🔴 Critical |
| `verdict_warning` | Brain returned WARNING (≥ 50% confidence) | 🟡 Warning |
| `gibson_triggered` | Automatic Gibson from ChainExecutor | 🔴 Critical |
| `gibson_manual` | Manual Gibson via `/api/rotate-keys` | 🔴 Critical |
| `policy_override` | Policy Engine overrode Brain verdict | 🟡 Warning |
| `policy_blocked` | Policy Engine blocked request or tool | 🟡 Warning |
| `auth_brute_force` | 5+ auth failures from one IP in 60s | 🔴 Critical |
| `mcp_offline` | MCP process alive→dead transition | 🔴 Critical |
| `system_startup` | ButterClaw server started | 🟢 Info |

### 🔐 Webhook Signing

Every outbound webhook payload is signed with HMAC-SHA256 using a per-channel signing secret:

```
X-ButterClaw-Signature: sha256=a3b7c9d1e2f456789...
X-ButterClaw-Event: verdict_critical
X-ButterClaw-Timestamp: 2026-04-20T23:14:22Z
```

Same pattern as GitHub webhooks — receivers can verify payload authenticity.

### ⏱️ Cooldown Engine

Per-rule cooldown prevents alert storms during sustained attacks. Default: 60 seconds. Configurable per rule — same channel can have different cooldowns for different event types (e.g., `verdict_critical` → 60s, `system_startup` → 0s).

### 🔄 Retry with Exponential Backoff

Failed deliveries retry with exponential backoff: 1s → 2s → 4s, max 3 attempts. Each attempt logged to `alert_history` with response code and error message.

### ☢️ Gibson Alert-Then-Burn

The Alert Dispatcher fires **BEFORE** vault destruction. The notification always escapes:

```
1. dispatch_alert("gibson_triggered", {...})   ← alert goes out over HTTP
2. _dispatch_worker sends to all channels      ← webhook/discord/ntfy/smtp/gotify fire
3. buttervault.butter_keys()                   ← vault destroyed
4. auth.destroy_all_api_keys()                 ← auth destroyed
5. Operator receives notification              ← notification arrives
```

Channel secrets are stored outside the ButterVault by design — Gibson can't silence the alarm.

---

## 🛡️ Policy Engine (v0.6.1)

Deterministic guardrails that constrain the probabilistic Brain with rules that say *"if X, then always Y"* — no reasoning required. Implements the DRIFT framework pattern (NeurIPS 2025).

### 3-Scope Filter Pipeline

| Scope | When It Fires | What It Can Do |
|-------|--------------|----------------|
| **Pre-Brain** | Before the LLM is called | Short-circuit to CRITICAL or BENIGN without burning inference time. Block entirely. |
| **Post-Brain** | After the LLM returns a verdict | Override, escalate, downgrade, or require higher confidence. |
| **Pre-Tool** | Before each MCP tool call in a chain | Block specific tools. Per-tool allowlist/blocklist. |

### Policy Rule Example

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

16 safe condition operators. No `eval()`. Priority-based short-circuit evaluation.

---

## 🔐 API Gateway & Authentication (v0.6.0)

Every endpoint protected by role-based access control with HMAC-SHA256 API keys and session tokens.

**Three-tier role hierarchy:**

| Tier | Access Level | Use Case |
|------|-------------|----------|
| **Admin** | Full access — vault, Gibson, MCP restart, settings, key/policy/channel management | System owner |
| **Operator** | Analyze threats, read settings, ping MCP, start OAuth flows, test alerts/policies | Active Sentinel operators |
| **Viewer** | Read-only — logs, events, status, tools, policies, alert history, SSE stream | Monitoring dashboards |

---

## 🏗️ Architecture

```
                        ┌──────────────────────────────────┐
                        │         WATCHER LAYER            │
                        │  (watcher.py — OS telemetry)     │
                        └──────────┬───────────────────────┘
                                   │ raw payload
                        ┌──────────▼───────────────────────┐
                        │        AUTH LAYER (v0.6.0)       │
                        │  @require_auth · RBAC · sessions │
                        ├──────────┬───────────────────────┤
                        │    ┌─────▼──────────┐            │
                        │    │  PRE-BRAIN     │ policy     │
                        │    │  Policy Filter │ override ──┼──► 🔔 dispatch_alert
                        │    └─────┬──────────┘            │
                        │          │                       │
                        │    ┌─────▼──────────┐            │
                        │    │  BRAIN (LLM)   │            │
                        │    │  Gemma / Ollama│            │
                        │    └─────┬──────────┘            │
                        │          │                       │
                        │    ┌─────▼──────────┐            │
                        │    │  POST-BRAIN    │ override ──┼──► 🔔 dispatch_alert
                        │    │  Policy Valid. │            │
                        │    └─────┬──────────┘            │
                        │          │ verdict               │
                        │          ├─── CRITICAL ──────────┼──► 🔔 dispatch_alert
                        │          └─── WARNING ───────────┼──► 🔔 dispatch_alert
                        │          │                       │
                        │    ┌─────▼──────────┐            │
                        │    │  PRE-TOOL      │ blocked ───┼──► 🔔 dispatch_alert
                        │    │  Policy Gate   │            │
                        │    └─────┬──────────┘            │
                        │          │                       │
                        │    ┌─────▼──────────┐            │
                        │    │  CHAIN EXEC    │            │
                        │    │  MCP Tools     │ gibson ────┼──► 🔔 dispatch_alert
                        │    └────────────────┘            │     (fires BEFORE butter_keys)
                        ├──────────────────────────────────┤
                        │       CREDENTIAL LAYER           │
                        │  ButterVault · OAuth · Fernet    │
                        └──────────────────────────────────┘

        🔔 Alert Dispatcher ──► webhook │ discord │ ntfy │ smtp │ gotify
```

### Component Map

| File | Lines | Purpose |
|------|-------|---------|
| `server.py` | ~1,800 | Flask API server, threat analysis pipeline, ChainExecutor, MCP management, all route handlers |
| `auth.py` | ~890 | API key manager, RBAC, session tokens, rate limiter, auth endpoints |
| `policy_engine.py` | ~350 | 3-scope policy evaluator, CRUD, condition operators, audit log |
| `alert_dispatcher.py` | ~1,566 | Multi-channel alert routing, webhook signing, cooldown, retry, history |
| `buttervault.py` | ~400 | Fernet encryption, OS keyring, OAuth token lifecycle, Gibson panic |
| `butterclaw_mcp.py` | ~300 | MCP server, tool definitions, process management, signature scanning |
| `mcp_transport.py` | ~250 | Dual-transport MCP client (stdio + SSE), JSON-RPC 2.0 framing |
| `oauth_config.py` | ~50 | Provider registry (Google Cloud endpoints, scopes) |
| `watcher.py` | ~200 | OS-level telemetry collector, process monitoring, file watching |

---

## 📡 API Endpoints (41 routes)

### Auth (v0.6.0)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/login` | public | Exchange API key for session token |
| `POST` | `/api/auth/logout` | any | Clear session cookie |
| `GET` | `/api/auth/whoami` | any | Current identity (role, label, key_id) |
| `GET` | `/api/auth/keys` | admin | List all API keys (hashes redacted) |
| `POST` | `/api/auth/keys` | admin | Create new API key |
| `DELETE` | `/api/auth/keys/<id>` | admin | Revoke (disable) API key |
| `DELETE` | `/api/auth/keys/<id>/purge` | admin | Permanently delete key record |

### Core

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `GET` | `/api/health` | public | Server health check |
| `POST` | `/api/analyze` | operator | Submit payload for threat analysis |
| `GET` | `/api/logs` | viewer | Oopsie log entries |
| `POST` | `/api/rotate-keys` | admin | Manual key rotation (Gibson) |
| `GET` | `/api/settings` | operator | Read Brain settings |
| `POST` | `/api/settings` | admin | Update Brain settings |

### MCP

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `GET` | `/api/mcp/status` | viewer | MCP connection status |
| `GET` | `/api/mcp/ping` | operator | Ping MCP server |
| `GET` | `/api/mcp/tools` | viewer | List available MCP tools |
| `POST` | `/api/mcp/restart` | admin | Restart MCP process |
| `GET` | `/api/mcp/events` | viewer | Event Ledger entries |
| `GET` | `/api/mcp/events/<id>` | viewer | Single ledger event |
| `GET` | `/api/stream` | viewer | SSE event stream |

### Vault & OAuth

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `POST` | `/api/vault/key` | admin | Store/update vault key |
| `GET` | `/api/vault/status` | viewer | Vault status |
| `GET` | `/api/vault/oauth/start/<provider>` | operator | Start OAuth flow |
| `GET` | `/api/vault/oauth/callback` | public | OAuth callback |
| `GET` | `/api/vault/oauth/status` | viewer | OAuth connection status |
| `POST` | `/api/vault/oauth/revoke/<provider>` | admin | Revoke OAuth tokens |
| `POST` | `/api/shield` | admin | Toggle shield mode |

### Policy Engine (v0.6.1)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `GET` | `/api/policies` | viewer | List policies |
| `POST` | `/api/policies` | admin | Create policy rule |
| `GET` | `/api/policies/<id>` | viewer | Get single policy |
| `PUT` | `/api/policies/<id>` | admin | Update policy |
| `DELETE` | `/api/policies/<id>` | admin | Delete policy |
| `POST` | `/api/policies/<id>/toggle` | admin | Enable/disable policy |
| `POST` | `/api/policies/test` | operator | Dry-run payload test |
| `GET` | `/api/policies/events` | viewer | Policy event audit log |

### Alert Dispatcher (v0.6.2)

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| `GET` | `/api/alerts/channels` | viewer | List alert channels |
| `POST` | `/api/alerts/channels` | admin | Create channel |
| `PUT` | `/api/alerts/channels/<id>` | admin | Update channel config |
| `DELETE` | `/api/alerts/channels/<id>` | admin | Delete channel (cascade) |
| `POST` | `/api/alerts/channels/<id>/toggle` | admin | Enable/disable channel |
| `POST` | `/api/alerts/channels/<id>/test` | operator | Send test alert |
| `GET` | `/api/alerts/rules` | viewer | List alert rules |
| `POST` | `/api/alerts/rules` | admin | Create rule |
| `PUT` | `/api/alerts/rules/<id>` | admin | Update rule |
| `DELETE` | `/api/alerts/rules/<id>` | admin | Delete rule |
| `POST` | `/api/alerts/rules/<id>/toggle` | admin | Enable/disable rule |
| `GET` | `/api/alerts/history` | viewer | Alert dispatch history |
| `GET` | `/api/alerts/status` | viewer | Alert system summary |

---

## ⚡ Quick Start

### 1. Install & Run

```bash
git clone https://github.com/butterclaw-tech/butterclaw.git
cd butterclaw
pip install flask flask-cors requests cryptography keyring ollama
python server.py
```

**First-boot output:**
```
========================================
🦞 ButterClaw v0.6.2 — The Exoskeleton
   Auth: ENABLED
   Policy Engine: ENABLED
   Alert Dispatcher: ENABLED
========================================
🔑 [AUTH] No admin keys found. Bootstrapping...
🔑 [AUTH] ══════════════════════════════════════
🔑 [AUTH]  FIRST-RUN ADMIN API KEY
🔑 [AUTH]  Key: bc_XXXXXXXXXXXXXXXXXXXX
🔑 [AUTH]  SAVE THIS KEY — it will NOT be shown again.
🔑 [AUTH] ══════════════════════════════════════
🔔 [ALERT] system_startup dispatched
📡 [MCP] Initiating v0.6.2 Handshake Sequence...
```

### 2. Login to Dashboard

Open `http://localhost:5000` — paste the bootstrap admin key into the login modal.

### 3. Create Alert Channels

**Discord webhook:**
```bash
curl -X POST http://localhost:5000/api/alerts/channels \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Discord Ops",
    "channel_type": "discord",
    "config": {
      "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
    }
  }'
```

**ntfy push notification:**
```bash
curl -X POST http://localhost:5000/api/alerts/channels \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mobile Push",
    "channel_type": "ntfy",
    "config": {
      "url": "https://ntfy.sh",
      "topic": "butterclaw-alerts"
    }
  }'
```

**Webhook with HMAC signing:**
```bash
curl -X POST http://localhost:5000/api/alerts/channels \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Production Webhook",
    "channel_type": "webhook",
    "config": { "url": "https://hooks.example.com/butterclaw" },
    "signing_secret": "your-hmac-secret-here"
  }'
```

### 4. Create Alert Rules

```bash
# CRITICAL verdicts → Discord + Webhook
curl -X POST http://localhost:5000/api/alerts/rules \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Critical → Discord",
    "event_type": "verdict_critical",
    "channel_id": "DISCORD_CHANNEL_ID",
    "cooldown_secs": 60
  }'

# Gibson events → all channels, no cooldown
curl -X POST http://localhost:5000/api/alerts/rules \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Gibson → Webhook (immediate)",
    "event_type": "gibson_triggered",
    "channel_id": "WEBHOOK_CHANNEL_ID",
    "cooldown_secs": 0
  }'
```

### 5. Test a Channel

```bash
curl -X POST http://localhost:5000/api/alerts/channels/CHANNEL_ID/test \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY"
```

### 6. Creating Policies

```bash
# Pre-brain: Block malicious websocket TLDs
curl -X POST http://localhost:5000/api/policies \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Block malicious TLDs",
    "scope": "pre_brain",
    "priority": 10,
    "condition": {"field": "payload", "operator": "regex_match", "value": "wss?://[^\\s]*\\.(net|io|xyz|tk|ml)"},
    "action": "override_critical",
    "description": "External websocket to suspicious TLD"
  }'

# Pre-tool: Veto automatic Gibson
curl -X POST http://localhost:5000/api/policies \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Veto Auto-Gibson",
    "scope": "pre_tool",
    "condition": {"field": "tool_name", "operator": "equals", "value": "execute_gibson_kill"},
    "action": "skip_tool"
  }'

# Dry-run test
curl -X POST http://localhost:5000/api/policies/test \
  -H "Authorization: Bearer bc_YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payload": "wss://malicious.net/exfil", "threat_type": "test"}'
```

---

## 📁 File Structure

```
butterclaw/
├── server.py              # Flask API, threat pipeline, ChainExecutor, MCP, 41 routes
├── auth.py                # API Gateway: HMAC-SHA256 keys, RBAC, sessions, rate limiting
├── policy_engine.py       # Deterministic policy evaluator, 3-scope filter, audit log
├── alert_dispatcher.py    # Multi-channel alert routing, signing, cooldown, retry
├── buttervault.py         # Zero-trust credential vault, Fernet encryption, OAuth, Gibson
├── butterclaw_mcp.py      # MCP server, tool definitions, signature scanning
├── mcp_transport.py       # Dual-transport MCP client (stdio + SSE)
├── oauth_config.py        # OAuth provider registry
├── watcher.py             # OS-level telemetry collector
├── index.html             # Main dashboard — Shield Status, ButterVault, Oopsie Logs
├── routing.html           # Routing dashboard — Brain config, MCP, Policies, Alerts, Ledger
├── butterclaw.db          # SQLite — logs, events, keys, policies, channels, rules, history
├── README.md
├── CHANGELOG.md
└── LICENSE
```

---

## 🔒 Security Model

### Defense in Depth

| Layer | Component | What It Does |
|-------|-----------|-------------|
| **Perimeter** | `auth.py` | HMAC-SHA256 API keys, RBAC, session tokens, rate limiting |
| **Deterministic** | `policy_engine.py` | Pre-brain fast-track, post-brain override, pre-tool gates |
| **Probabilistic** | `server.py` (Brain) | LLM-based threat reasoning with 85% confidence threshold |
| **Credential** | `buttervault.py` | Fernet encryption, OS keyring, OAuth lifecycle, Gibson panic |
| **Execution** | `butterclaw_mcp.py` | MCP tools with pre-tool policy gate, ChainExecutor safety rails |
| **Notification** | `alert_dispatcher.py` | External push to 5 channel types, HMAC signing, cooldown, retry |
| **Audit** | Event Ledger + Policy Events + Alert History | Three independent audit trails for execution, policy, and notification |

### OWASP Agentic Security Initiative (ASI) Coverage

| ASI ID | Threat | ButterClaw Mitigation |
|--------|--------|----------------------|
| ASI-01 | Prompt Injection | 4-gate analysis pipeline + pre-brain policy filter + alert dispatch |
| ASI-02 | Excessive Agency | Pre-tool policy gate blocks unauthorized tool calls |
| ASI-03 | Supply Chain | MCP tool allowlisting via pre-tool policies |
| ASI-06 | Uncontrolled Code Exec | ChainExecutor safety rails + policy pattern matching |
| ASI-07 | Insufficient Access Controls | RBAC with 3 tiers + policy event audit log + alert history |
| ASI-09 | Inadequate Logging | Event Ledger + Policy Events + Alert Dispatch History — 3 audit trails + external notification |
| ASI-10 | Cascading Failures | Gibson panic destroys all credentials atomically + alert fires before destruction |

### What Survives Gibson (v0.6.2)

```
DESTROYED by Gibson:           SURVIVES Gibson:
├── vault table (API keys)     ├── policies table (rules are config)
├── oauth_tokens table         ├── policy_events table (audit trail)
├── api_keys table             ├── alert_channels table (delivery config)
├── session cache              ├── alert_rules table (routing config)
└── OS keyring master key      ├── alert_history table (audit trail)
                               ├── mcp_events table (execution ledger)
                               └── logs table (oopsie log)
```

---

## 📊 Version History

| Version | Codename | Key Features |
|---------|----------|-------------|
| **v0.6.2** | **The Exoskeleton: Alert Dispatcher** | **Multi-channel alert routing, webhook signing, cooldown, retry, auth brute-force detection, MCP health monitor** |
| v0.6.1 | The Exoskeleton: Policy Engine | 3-scope deterministic guardrails, 16 operators, policy CRUD, dry-run testing |
| v0.6.0 | The Exoskeleton: API Gateway | HMAC-SHA256 auth, RBAC (3 tiers), session tokens, rate limiting, dashboard login |
| v0.5.2 | ButterVault OAuth | OAuth 2.0 authorization code flow, encrypted token storage, automatic refresh |
| v0.5.1 | The Nervous System (Patch) | Orphaned ledger cleanup, ChainExecutor condition fixes |
| v0.5.0 | The Nervous System | Event Ledger, SSE transport, ChainExecutor, memory injection |
| v0.4.1 | MCP Transport Patch | JSON-RPC 2.0 framing fixes, connection resilience |
| v0.4.0 | MCP Integration | Model Context Protocol, dual-transport client, tool discovery |
| v0.3.1 | CSP & Endpoint Fixes | Content Security Policy, routing.html endpoint resolution |
| v0.3.0 | Brain Routing | Remote/local model selection, routing dashboard |
| v0.2.0 | ButterVault | Fernet encryption, OS keyring integration, Gibson panic button |
| v0.1.0 | Genesis | Core threat analysis, 4-gate pipeline, basic dashboard |

---

## 🗺️ Roadmap — The Exoskeleton (v0.6.x)

| Pillar | Version | Status |
|--------|---------|--------|
| 1. API Gateway & Auth | v0.6.0 | ✅ Delivered |
| 2. Policy Engine | v0.6.1 | ✅ Delivered |
| 3. Alert Dispatcher | v0.6.2 | ✅ Delivered |
| 4. Deployment Packaging | v0.6.3 | 🔧 Next — Docker, systemd, env config |

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

*ButterClaw — deterministic guardrails for probabilistic reasoning. The Sentinel never goes silent. Evaluation before Execution.* 🦞

---

<p align="center">
  <strong>🦞 ButterClaw v0.6.2 — The Exoskeleton (Alert Dispatcher)</strong><br>
  <em>Deterministic guardrails for probabilistic reasoning. Evaluation before Execution.</em><br>
  <a href="https://butterclaw.tech">butterclaw.tech</a> · <a href="https://github.com/butterclaw-tech/butterclaw">GitHub</a>
</p>

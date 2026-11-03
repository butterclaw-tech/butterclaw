# 📡 ButterClaw API Reference (v0.9.3)

ButterClaw features a comprehensive REST API with **80 routes**, protected by a **4-tier Role-Based Access Control (RBAC) system** (Infrastructure, Admin, Operator, Viewer) using HMAC-SHA256 API keys and session tokens.

---

## Authentication

All protected endpoints require one of:
- **API Key** — `Authorization: Bearer <api_key>` header. Verified via HMAC-SHA256 hash comparison.
- **Session Token** — `Authorization: Bearer <session_token>` or `butterclaw_session` cookie. HMAC-signed JSON struct with expiry. Issued by `POST /api/auth/login`.

Public endpoints (`/api/health`, `GET /`, `/favicon.png`, `/api/vault/oauth/callback`) require no authentication.

---

## Role Hierarchy

| Role | Privilege Level | Description | Rate Limit |
|---|---|---|---|
| **infrastructure** | 4 (highest) | Internal machine-to-machine superuser. Used by auto-healing components and the Watcher daemon. Never issued to human operators. Restored from `BUTTERCLAW_API_KEY` env var via `bootstrap_infrastructure_keys_auto_heal()` on startup. | 1000 req/min |
| **admin** | 3 | Full system access — key management, config, vault, SkillGuard directory audits, all write operations | Configurable (`AUTH_RATE_ADMIN`) |
| **operator** | 2 | Threat analysis, chain execution, OAuth flows, dry-run policy testing | Configurable (`AUTH_RATE_OPERATOR`) |
| **viewer** | 1 (lowest) | Read-only access to logs, events, SkillGuard registry, status endpoints, SSE stream | Configurable (`AUTH_RATE_VIEWER`) |

> **Note:** The `infrastructure` role cannot be created via the API — it is bootstrapped from the `BUTTERCLAW_API_KEY` environment variable at startup and does not appear in `GET /api/auth/keys` listings.

---

## Endpoints by Module

### Auth Endpoints (v0.6.0) — 7 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | public | Exchange API key for session token |
| `POST` | `/api/auth/logout` | any | Clear session cookie and invalidate token |
| `GET` | `/api/auth/whoami` | any | Current identity, role, and key metadata |
| `GET` | `/api/auth/keys` | admin | List all API keys (excludes infrastructure keys) |
| `POST` | `/api/auth/keys` | admin | Create new API key with assigned role |
| `DELETE` | `/api/auth/keys/<id>` | admin | Revoke API key (soft delete) |
| `DELETE` | `/api/auth/keys/<id>/purge` | admin | Permanently delete key record |

---

### Policy Endpoints (v0.6.1) — 8 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/policies` | viewer | List all policies (paginated) |
| `POST` | `/api/policies` | admin | Create new DRIFT policy rule |
| `GET` | `/api/policies/<id>` | viewer | Get single policy rule |
| `PUT` | `/api/policies/<id>` | admin | Update policy rule |
| `DELETE` | `/api/policies/<id>` | admin | Delete policy rule |
| `POST` | `/api/policies/<id>/toggle` | admin | Enable or disable a policy rule |
| `POST` | `/api/policies/dry-run` | operator | Test a payload against all active policies without side effects |
| `GET` | `/api/policies/events` | viewer | Query the `policy_events` audit log |

**Available operators (15):** `contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `regex_match`, `greater_than`, `less_than`, `greater_equal`, `less_equal`, `in_list`, `not_in_list`, `length_gt`, `length_lt`

**Available actions (6):** `allow`, `block`, `override_critical`, `override_benign`, `skip_tool` *(pre_tool only)*, `require_confidence` *(post_brain only)*

---

### Alert Endpoints (v0.6.2) — 13 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/alerts/channels` | viewer | List all configured alert channels |
| `POST` | `/api/alerts/channels` | admin | Create new alert channel |
| `PUT` | `/api/alerts/channels/<id>` | admin | Update channel configuration |
| `DELETE` | `/api/alerts/channels/<id>` | admin | Delete channel and cascade-delete associated rules |
| `POST` | `/api/alerts/channels/<id>/toggle` | admin | Enable or disable a channel |
| `POST` | `/api/alerts/channels/<id>/test` | operator | Send test alert to verify channel connectivity |
| `GET` | `/api/alerts/rules` | viewer | List all alert routing rules |
| `POST` | `/api/alerts/rules` | admin | Create new alert routing rule |
| `PUT` | `/api/alerts/rules/<id>` | admin | Update routing rule |
| `DELETE` | `/api/alerts/rules/<id>` | admin | Delete routing rule |
| `POST` | `/api/alerts/rules/<id>/toggle` | admin | Enable or disable a routing rule |
| `GET` | `/api/alerts/history` | viewer | Query alert delivery history |
| `GET` | `/api/alerts/status` | viewer | Alert system summary |

**Supported channel types (6):** `webhook` *(HMAC-SHA256 signed)*, `discord`, `telegram`, `ntfy`, `smtp`, `gotify`

**Supported event types (9):** `critical_verdict`, `high_confidence`, `chain_executed`, `gibson_triggered`, `policy_blocked`, `mcp_tool_called`, `auth_failure`, `vault_accessed`, `audit_complete`

---

### Core Endpoints — 5 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `POST` | `/api/analyze` | operator | Submit threat payload for Guardian Brain analysis |
| `GET` | `/api/health` | public | System health, version (`0.9.3`), instance info, component status (includes `skill_guard`, `fleet_layer`, `mcp`, `policy_engine`, `alert_dispatcher`) |
| `GET` | `/api/config` | admin | Resolved configuration with secrets redacted (includes `skill_guard` and `memory_watchdog` blocks) |
| `GET` | `/api/stream` | viewer | SSE event stream — real-time verdict, chain, and SkillGuard audit updates |
| `GET` | `/api/logs` | viewer | Query analysis log history (paginated) |

**`POST /api/analyze` request body:**
```json
{
  "threat_type": "string",
  "raw_data": "string (max 4096 chars after sanitization)"
}

```

**`POST /api/analyze` response:**

```json
{
  "verdict": "BENIGN | SUSPICIOUS | CRITICAL",
  "confidence": 0.0,
  "reasoning": "string",
  "primary_gate": "string",
  "chain": [],
  "policy_overrides": []
}

```

---

### MCP Endpoints (v0.5.0+) — 7 routes

| Method | Endpoint | Min Role | Description |
| --- | --- | --- | --- |
| `GET` | `/api/mcp/tools` | viewer | List available MCP tools from active transport (7 armed tools in v0.9.3) |
| `POST` | `/api/mcp/restart` | admin | Restart the MCP process (stdio transport only) |
| `GET` | `/api/mcp/status` | viewer | MCP process health and transport type |
| `GET` | `/api/events` | viewer | Query the `mcp_events` Event Ledger (paginated) |
| `GET` | `/api/events/count` | viewer | Total event ledger entry count |
| `GET` | `/api/settings` | viewer | Server runtime settings (Paranoia level, DRY_RUN state, active transport) |
| `POST` | `/api/gates/<id>/toggle` | admin | Arm or disarm a named logic gate. Returns `dry_run` flag. No-ops safely when `DRY_RUN=true`. |

---

### Vault & OAuth Endpoints (v0.5.x) — 10 routes

| Method | Endpoint | Min Role | Description |
| --- | --- | --- | --- |
| `POST` | `/api/rotate-keys` | admin | Manual Gibson Kill Switch — wipes vault + destroys all API keys. Blocked if `DRY_RUN=true`. |
| `GET` | `/api/vault/status` | viewer | Vault health (keyring reachable, row count, encryption status) |
| `GET` | `/api/vault/credentials` | operator | List stored credential names (values never returned) |
| `POST` | `/api/vault/credentials` | admin | Store new encrypted credential |
| `DELETE` | `/api/vault/credentials/<name>` | admin | Delete credential from vault |
| `GET` | `/api/vault/oauth/callback` | public | OAuth redirect callback handler (state-validated) |
| `GET` | `/api/oauth/providers` | viewer | List configured OAuth providers |
| `POST` | `/api/oauth/start/<provider>` | operator | Initiate OAuth authorization flow |
| `GET` | `/api/oauth/tokens` | operator | List stored OAuth tokens (metadata only, no secrets) |
| `DELETE` | `/api/oauth/tokens/<provider>` | admin | Revoke and delete OAuth token for a provider |

> **`POST /api/rotate-keys` (Gibson):** Destructive and irreversible. Overwrites all vault ciphertext, deletes all HMAC key hashes, invalidates all active sessions. Policy rules and SkillGuard attestations are **not** affected. Returns 200 with no action if `DRY_RUN=true`.

---

### Spatial Telemetry Endpoint (v0.8.0 Part 1) — 1 route

| Method | Endpoint | Min Role | Description |
| --- | --- | --- | --- |
| `POST` | `/api/spatial/telemetry` | operator | High-speed ingest and active tollbooth for raw spatial coordinates/keystrokes from AI agents. Evaluates the proposed action through the Memory Engine (Cold Memory signature match, then spatial heuristics) before it lands in the telemetry ledger. A `BLOCK` verdict propagates taint down the agent's process tree via the Topology Manager and hands a kill request to the Watcher Daemon. |

**`POST /api/spatial/telemetry` request body:**

```json
{
  "session_id": "string",
  "action_type": "mouse_click | keyboard_type | scroll | navigate",
  "payload": {},
  "screenshot_ref": "string (optional)"
}

```

**`POST /api/spatial/telemetry` response:**

```json
{
  "status": "allowed | blocked",
  "verdict": "ALLOW | BLOCK",
  "reason": "string"
}

```

---

### Memory / Dream / Loop Endpoints (v0.8.0 Part 2) — 13 routes

Management surface for the unified Deep + Surface Memory Engine and its two hemispheres, the Dream Weaver (idle-triggered consolidation + REM scenario synthesis) and the Loop Proposer (Karpathy-style autoresearch loop). Registered by `memory_api.py`'s `register_memory_routes(app, dream_engine, loop_engine)`.

| Method | Endpoint | Min Role | Description |
| --- | --- | --- | --- |
| `GET` | `/api/memory/hot` | viewer | Live Tier-1 hot-cache entries (not yet flushed to episodic or expired) |
| `GET` | `/api/memory/episodic` | viewer | Paginated Tier-2 warm episodic reader (`?limit=&offset=`) |
| `DELETE` | `/api/memory/episodic/<memory_id>` | admin | Hard-delete a single episodic record. Returns `404` if the ID never existed. |
| `GET` | `/api/memory/semantic` | viewer | Tier-3 cold semantic entity graph — nodes and weighted edges |
| `POST` | `/api/memory/flush` | operator | Force-flush all live hot-cache entries into the episodic store now |
| `GET` | `/api/memory/signatures` | viewer | Cold Memory attractors — from `dreamer_daemon.py`'s offline batch synthesis and the Memory Engine's own scoped live crystallization (tagged `live:` in `threat_category`) |
| `GET` | `/api/memory/status` | viewer | Memory Watchdog tick telemetry and runtime status. |
| `GET` | `/api/dream/log` | viewer | Paginated `dream_log` reader — every consolidation/REM cycle that has run |
| `POST` | `/api/dream/trigger` | operator | Manually start a dream cycle now, bypassing the idle-threshold wait. Still fully subject to the Dream Weaver's hardcoded dry-run (I-13) and live-traffic yield (I-14). Returns `409` if a cycle is already running. |
| `GET` | `/api/loop/experiments` | viewer | Paginated `loop_experiments` reader (`?limit=&status=`) — every proposal scored this run |
| `POST` | `/api/loop/trigger` | operator | Manually run one Loop Proposer cycle now. Subject to the same `LOOP_DRY_RUN`/I-15 gating as a scheduled cycle — does not grant any additional authority. |
| `GET` | `/api/loop/prompts` | viewer | List all staged `prompt_overrides` |
| `POST` | `/api/loop/prompts/<prompt_key>` | admin | Stage (create or overwrite) a prompt override — the highest-trust write in this module. Currently affects the Guardian Brain's and Auditor's persona preamble only (`guardian_brain_preamble`, `auditor_preamble`); the paranoia-dial mode instructions, gate context, and strict JSON response schema are never overridable. |

**`POST /api/loop/prompts/<prompt_key>` request body:**

```json
{
  "prompt_value": "string"
}

```

> **Note on `POST /api/memory/flush`, `/api/dream/trigger`, `/api/loop/trigger`:** none of these three routes can trigger a kinetic action — no route in this module calls `topology_manager`, `watcher_daemon`, or `alert_dispatcher`. They only ever move data between memory tiers, run a consolidation pass, or score a proposal.

> **Version note:** `GET /api/memory/status` was added in v0.9.2 R3 for Memory Watchdog tick telemetry.

---

### Fleet Endpoints (v0.9.0) — 14 routes

> **RBAC:** viewer = read-only; operator = read + trigger + feedback; admin = full management including quarantine and entity demotion.
> All routes return `503` if a fleet component is unavailable.

| Method | Path | Min Role | Description |
| --- | --- | --- | --- |
| `GET` | `/api/fleet/agents` | viewer | List all registered fleet agents with trust scores and reputation |
| `GET` | `/api/fleet/agents/<agent_id>` | viewer | Fetch a single agent record |
| `GET` | `/api/fleet/agents/<agent_id>/trust` | viewer | Return trust graph edges for an agent |
| `POST` | `/api/fleet/agents/<agent_id>/quarantine` | operator | Step 1 — flag agent for quarantine; returns 60s confirmation token |
| `POST` | `/api/fleet/agents/<agent_id>/quarantine/confirm` | operator | Step 2 — consume token and execute quarantine (R-06) |
| `GET` | `/api/fleet/correlations` | viewer | List open correlation events |
| `GET` | `/api/fleet/correlations/<event_id>` | viewer | Fetch a single correlation event |
| `DELETE` | `/api/fleet/correlations/<event_id>` | operator | Dismiss a false-positive correlation event |
| `POST` | `/api/fleet/correlations/<event_id>/promote` | admin | Human-gate: promote correlated session entity to fleet scope (I-03-fleet) |
| `GET` | `/api/fleet/collusions` | viewer | List open collusion events |
| `GET` | `/api/fleet/sentinel/log` | viewer | Fleet Sentinel verdict history (paginated) |
| `POST` | `/api/fleet/sentinel/trigger` | operator | Manually trigger a Fleet Sentinel proactive analysis |
| `POST` | `/api/fleet/sentinel/feedback` | operator | Submit operator feedback on a verdict (TP/FP) |
| `GET` | `/api/fleet/health` | viewer | Fleet component health status (registry, trust graph, sentinel, scheduler) |

**Quarantine lifecycle (R-06):**

```
POST /api/fleet/agents/<id>/quarantine
  → 200 { "confirmation_token": "qtok_...", "expires_in_seconds": 60,
           "active_sessions": [...], "warning": "..." }

POST /api/fleet/agents/<id>/quarantine/confirm?token=qtok_...
  → 200 { "agent_id": "...", "new_reputation": 0.0, "quarantined": true }
  → 400 if token expired or invalid

```

> ⚠️ Quarantine sets reputation to 0.0 and blocks new sessions. It does **NOT** terminate active processes. Use `POST /api/spatial/block` separately to kill active sessions.

---

### SkillGuard Supply-Chain Endpoints (v0.9.3) — 2 routes

Observability and on-demand auditing surface for `SKILL.md` agent packages (`Gate M5` cryptographic Merkle anti-TOCTOU + `Gate M10` path containment). Both routes return `503` if `SkillGuard` is unavailable.

| Method | Endpoint | Min Role | Description |
| --- | --- | --- | --- |
| `GET` | `/api/skills` | viewer | List all attested `SKILL.md` packages in `butterclaw.db` (`skill_attestations`). Accepts optional `?verify=true|false` (default `true`) to run live on-disk SHA-256 Merkle-root verification against `APPROVED` packages and flag post-audit modifications as `TAMPERED`. |
| `POST` | `/api/skills/audit` | admin | Run static frontmatter, Unicode steganography, HTML comment, and Python AST inspection on direct `SKILL.md` subdirectories inside `cfg.SKILL_ROOT` (strictly jailed by Gate M10). Emits an SSE refresh signal to `/api/stream`. |

**`GET /api/skills` response:**

```json
{
  "skills": [
    {
      "skill_name": "log-summarizer",
      "package_path": "/data/skills/log-summarizer",
      "merkle_root": "45b4a254e209824347b28862b36533564b6a9b5fa304d0523b53abbe25f0dd7f",
      "declared_description": "Summarizes local gateway logs into markdown status tables.",
      "allowed_tools": ["log_event"],
      "allow_network": false,
      "allow_env_access": false,
      "risk_score": 0,
      "findings": [],
      "status": "APPROVED",
      "live_status": "APPROVED",
      "integrity_ok": true,
      "integrity_reason": "Merkle root verified",
      "attested_at": "2026-10-25T11:59:11Z"
    }
  ],
  "count": 1,
  "summary": {
    "approved": 1,
    "quarantined": 0,
    "tampered": 0
  },
  "skill_root": "/data/skills",
  "risk_threshold": 25,
  "strict_toctou": true
}

```

**`POST /api/skills/audit` request body (optional):**

```json
{
  "skill_name": "log-summarizer"
}

```

> Omit `skill_name` (or send `{}`) to scan every direct subdirectory containing a `SKILL.md` inside `cfg.SKILL_ROOT`. Passing `/`, `\`, or `..` returns `400` (`Gate M10` path traversal guard).

**`POST /api/skills/audit` response:**

```json
{
  "status": "ok",
  "audited_count": 2,
  "results": [
    {
      "skill_name": "log-summarizer",
      "status": "APPROVED",
      "risk_score": 0,
      "merkle_root": "45b4a254e209824347b28862b36533564b6a9b5fa304d0523b53abbe25f0dd7f",
      "findings_count": 0
    },
    {
      "skill_name": "stealth-exfiltrator",
      "status": "QUARANTINED",
      "risk_score": 100,
      "merkle_root": "062a926334d6974826ea76c358d276e7a47f710ea93089d7ca3e6ceffc9fb383",
      "findings_count": 10
    }
  ]
}

```

---

## Route Count Summary

| Module | Routes | Introduced |
| --- | --- | --- |
| Auth | 7 | v0.6.0 |
| Policy | 8 | v0.6.1 |
| Alert | 13 | v0.6.2 |
| Core | 5 | v0.1–v0.4 |
| MCP | 7 | v0.5.0 |
| Vault & OAuth | 10 | v0.5.x |
| Spatial Telemetry | 1 | v0.8.0 (Part 1) |
| Memory / Dream / Loop | 13 | v0.8.0 (Part 2) |
| Fleet Layer | 14 | v0.9.0 |
| SkillGuard Supply-Chain | 2 | v0.9.3 |
| **Total** | **80** | — |

---

## Error Responses

```json
{
  "error": "human-readable message",
  "code": "MACHINE_READABLE_CODE"
}

```

| Status | Meaning |
| --- | --- |
| `400` | Bad request — missing, malformed, or path-traversal (`..`) fields |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient role, or blocked by pre_brain / spatial policy |
| `404` | Resource or skill package not found |
| `409` | Conflict — duplicate resource or cycle already running |
| `429` | Rate limit exceeded for this key's role |
| `500` | Internal server error |
| `503` | Subsystem disabled or unavailable (Policy, Fleet, MCP, or SkillGuard) |

---

## Related Documentation

* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, Gate M5/M10 invariants, data flow
* [`RUNBOOK.md`](RUNBOOK.md) — Fleet quarantine vs. block flowchart, dry-run rollout, alert procedures (v0.9.0)
* [`SECURITY.md`](SECURITY.md) — Threat model, attack surfaces, responsible disclosure
* [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker, systemd, nginx, backup configuration
* [`THREAT_MODEL.md`](THREAT_MODEL.md) — Updated threat model

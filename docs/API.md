# 📡 ButterClaw API Reference

ButterClaw features a comprehensive REST API with **63 routes**, protected by a **4-tier Role-Based Access Control (RBAC) system** (Infrastructure, Admin, Operator, Viewer) using HMAC-SHA256 API keys and session tokens.

---

## Authentication

All protected endpoints require one of:
- **API Key** — `Authorization: Bearer <api_key>` header. Verified via HMAC-SHA256 hash comparison.
- **Session Token** — `Authorization: Bearer <session_token>` or `butterclaw_session` cookie. HMAC-signed JSON struct with expiry. Issued by `POST /api/auth/login`.

Public endpoints (`/api/health`, `GET /`, `/api/oauth/callback`) require no authentication.

---

## Role Hierarchy

| Role | Privilege Level | Description | Rate Limit |
|---|---|---|---|
| **infrastructure** | 4 (highest) | Internal machine-to-machine superuser. Used by auto-healing components and the Watcher daemon. Never issued to human operators. Restored from `BUTTERCLAW_API_KEY` env var via `bootstrap_infrastructure_keys_auto_heal()` on startup. | 1000 req/min |
| **admin** | 3 | Full system access — key management, config, vault, all write operations | Configurable (`AUTH_RATE_ADMIN`) |
| **operator** | 2 | Threat analysis, chain execution, OAuth flows, dry-run policy testing | Configurable (`AUTH_RATE_OPERATOR`) |
| **viewer** | 1 (lowest) | Read-only access to logs, events, status endpoints, SSE stream | Configurable (`AUTH_RATE_VIEWER`) |

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
| `GET` | `/api/health` | public | System health, version, instance info, component status |
| `GET` | `/api/config` | admin | Resolved configuration (secrets redacted) |
| `GET` | `/api/stream` | viewer | SSE event stream — real-time verdict and chain updates |
| `GET` | `/api/logs` | viewer | Query analysis log history (paginated) |

**`POST /api/analyze` request body:**
​```json
{
  "threat_type": "string",
  "raw_data": "string (max 4096 chars after sanitization)"
}
​```

**`POST /api/analyze` response:**
​```json
{
  "verdict": "BENIGN | SUSPICIOUS | CRITICAL",
  "confidence": 0.0,
  "reasoning": "string",
  "primary_gate": "string",
  "chain": [],
  "policy_overrides": []
}
​```

---

### MCP Endpoints (v0.5.0+) — 7 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/mcp/tools` | viewer | List available MCP tools from active transport |
| `POST` | `/api/mcp/restart` | admin | Restart the MCP process (stdio transport only) |
| `GET` | `/api/mcp/status` | viewer | MCP process health and transport type |
| `GET` | `/api/events` | viewer | Query the `mcp_events` Event Ledger (paginated) |
| `GET` | `/api/events/count` | viewer | Total event ledger entry count |
| `GET` | `/api/settings` | viewer | Server runtime settings (Paranoia level, DRY_RUN state, active transport) |
| `POST` | `/api/gates/<id>/toggle` | admin | Arm or disarm a named logic gate. Returns `dry_run` flag. No-ops safely when `DRY_RUN=true`. |

---

### Vault & OAuth Endpoints (v0.5.x) — 10 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `POST` | `/api/rotate-keys` | admin | Manual Gibson Kill Switch — wipes vault + destroys all API keys. Blocked if `DRY_RUN=true`. |
| `GET` | `/api/vault/status` | viewer | Vault health (keyring reachable, row count, encryption status) |
| `GET` | `/api/vault/credentials` | operator | List stored credential names (values never returned) |
| `POST` | `/api/vault/credentials` | admin | Store new encrypted credential |
| `DELETE` | `/api/vault/credentials/<name>` | admin | Delete credential from vault |
| `GET` | `/api/oauth/providers` | viewer | List configured OAuth providers |
| `POST` | `/api/oauth/start/<provider>` | operator | Initiate OAuth authorization flow |
| `GET` | `/api/oauth/callback` | public | OAuth redirect callback handler (state-validated) |
| `GET` | `/api/oauth/tokens` | operator | List stored OAuth tokens (metadata only, no secrets) |
| `DELETE` | `/api/oauth/tokens/<provider>` | admin | Revoke and delete OAuth token for a provider |

> **`POST /api/rotate-keys` (Gibson):** Destructive and irreversible. Overwrites all vault ciphertext, deletes all HMAC key hashes, invalidates all active sessions. Policy rules are **not** affected. Returns 200 with no action if `DRY_RUN=true`.

---

### Spatial Telemetry Endpoint (v0.8.0 Part 1) — 1 route

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `POST` | `/api/spatial/telemetry` | operator | High-speed ingest and active tollbooth for raw spatial coordinates/keystrokes from AI agents. Evaluates the proposed action through the Memory Engine (Cold Memory signature match, then spatial heuristics) before it lands in the telemetry ledger. A `BLOCK` verdict propagates taint down the agent's process tree via the Topology Manager and hands a kill request to the Watcher Daemon. |

**`POST /api/spatial/telemetry` request body:**
​```json
{
  "session_id": "string",
  "action_type": "mouse_click | keyboard_type | scroll | navigate",
  "payload": {},
  "screenshot_ref": "string (optional)"
}
​```

**`POST /api/spatial/telemetry` response:**
​```json
{
  "status": "allowed | blocked",
  "verdict": "ALLOW | BLOCK",
  "reason": "string"
}
​```

---

### Memory / Dream / Loop Endpoints (v0.8.0 Part 2) — 12 routes

Management surface for the unified Deep + Surface Memory Engine and its two new hemispheres, the Dream Weaver (idle-triggered consolidation + REM scenario synthesis) and the Loop Proposer (Karpathy-style autoresearch loop). Registered by `memory_api.py`'s `register_memory_routes(app, dream_engine, loop_engine)`.

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/memory/hot` | viewer | Live Tier-1 hot-cache entries (not yet flushed to episodic or expired) |
| `GET` | `/api/memory/episodic` | viewer | Paginated Tier-2 warm episodic reader (`?limit=&offset=`) |
| `DELETE` | `/api/memory/episodic/<memory_id>` | admin | Hard-delete a single episodic record. Returns `404` if the ID never existed. |
| `GET` | `/api/memory/semantic` | viewer | Tier-3 cold semantic entity graph — nodes and weighted edges |
| `POST` | `/api/memory/flush` | operator | Force-flush all live hot-cache entries into the episodic store now |
| `GET` | `/api/memory/signatures` | viewer | Cold Memory attractors — from `dreamer_daemon.py`'s offline batch synthesis and the Memory Engine's own scoped live crystallization (tagged `live:` in `threat_category`) |
| `GET` | `/api/dream/log` | viewer | Paginated `dream_log` reader — every consolidation/REM cycle that has run |
| `POST` | `/api/dream/trigger` | operator | Manually start a dream cycle now, bypassing the idle-threshold wait. Still fully subject to the Dream Weaver's hardcoded dry-run (I-13) and live-traffic yield (I-14). Returns `409` if a cycle is already running. |
| `GET` | `/api/loop/experiments` | viewer | Paginated `loop_experiments` reader (`?limit=&status=`) — every proposal scored this run |
| `POST` | `/api/loop/trigger` | operator | Manually run one Loop Proposer cycle now. Subject to the same `LOOP_DRY_RUN`/I-15 gating as a scheduled cycle — does not grant any additional authority. |
| `GET` | `/api/loop/prompts` | viewer | List all staged `prompt_overrides` |
| `POST` | `/api/loop/prompts/<prompt_key>` | admin | Stage (create or overwrite) a prompt override — the highest-trust write in this module. Currently affects the Guardian Brain's and Auditor's persona preamble only (`guardian_brain_preamble`, `auditor_preamble`); the paranoia-dial mode instructions, gate context, and strict JSON response schema are never overridable. |

**`POST /api/loop/prompts/<prompt_key>` request body:**
​```json
{
  "prompt_value": "string"
}
​```

> **Note on `POST /api/memory/flush`, `/api/dream/trigger`, `/api/loop/trigger`:** none of these three routes can trigger a kinetic action — no route in this module calls `topology_manager`, `watcher_daemon`, or `alert_dispatcher`. They only ever move data between memory tiers, run a consolidation pass, or score a proposal.

---

## Route Count Summary

| Module | Routes | Introduced |
|---|---|---|
| Auth | 7 | v0.6.0 |
| Policy | 8 | v0.6.1 |
| Alert | 13 | v0.6.2 |
| Core | 5 | v0.1–v0.4 |
| MCP | 7 | v0.5.0 |
| Vault & OAuth | 10 | v0.5.x |
| Spatial Telemetry | 1 | v0.8.0 (Part 1) |
| Memory / Dream / Loop | 12 | v0.8.0 (Part 2) |
| **Total** | **63** | — |

---

## Error Responses

​```json
{
  "error": "human-readable message",
  "code": "MACHINE_READABLE_CODE"
}
​```

| Status | Meaning |
|---|---|
| `400` | Bad request — missing or malformed fields |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient role, or blocked by pre_brain policy |
| `404` | Resource not found |
| `409` | Conflict — duplicate resource |
| `429` | Rate limit exceeded for this key's role |
| `500` | Internal server error |

---

## Related Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, invariants, data flow
- [`SECURITY.md`](SECURITY.md) — Threat model, attack surfaces, responsible disclosure
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker, systemd, nginx, backup configuration

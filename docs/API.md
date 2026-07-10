# 📡 ButterClaw API Reference

ButterClaw features a comprehensive REST API with **49 routes**, protected by a **4-tier Role-Based Access Control (RBAC) system** (Infrastructure, Admin, Operator, Viewer) using HMAC-SHA256 API keys and session tokens.

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
| **infrastructure** | -1 (highest) | Internal machine-to-machine superuser. Used by auto-healing components and the Watcher daemon. Never issued to human operators. Restored from `BUTTERCLAW_API_KEY` env var via `bootstrap_infrastructure_keys_auto_heal()` on startup. | 1000 req/min |
| **admin** | 0 | Full system access — key management, config, vault, all write operations | Configurable (`AUTH_RATE_ADMIN`) |
| **operator** | 1 | Threat analysis, chain execution, OAuth flows, dry-run policy testing | Configurable (`AUTH_RATE_OPERATOR`) |
| **viewer** | 2 (lowest) | Read-only access to logs, events, status endpoints, SSE stream | Configurable (`AUTH_RATE_VIEWER`) |

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

### MCP Endpoints (v0.5.0+) — 6 routes

| Method | Endpoint | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/mcp/tools` | viewer | List available MCP tools from active transport |
| `POST` | `/api/mcp/restart` | admin | Restart the MCP process (stdio transport only) |
| `GET` | `/api/mcp/status` | viewer | MCP process health and transport type |
| `GET` | `/api/events` | viewer | Query the `mcp_events` Event Ledger (paginated) |
| `GET` | `/api/events/count` | viewer | Total event ledger entry count |
| `GET` | `/api/settings` | viewer | Server runtime settings (Paranoia level, DRY_RUN state, active transport) |

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

## Route Count Summary

| Module | Routes | Introduced |
|---|---|---|
| Auth | 7 | v0.6.0 |
| Policy | 8 | v0.6.1 |
| Alert | 13 | v0.6.2 |
| Core | 5 | v0.1–v0.4 |
| MCP | 6 | v0.5.0 |
| Vault & OAuth | 10 | v0.5.x |
| **Total** | **49** | — |

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

# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/)

---

## [0.6.0] - The Exoskeleton: API Gateway & Authentication - 2026-04-23

### Added
- **Authentication Module (`auth.py`):** New standalone module (~890 lines) providing the complete API gateway for ButterClaw. Zero new pip dependencies — built entirely on stdlib (`hmac`, `hashlib`, `secrets`, `json`, `base64`).
- **API Key Manager (`auth.py`):** HMAC-SHA256 API key generation, hashing, and verification with per-key 16-byte random salts. Keys are hashed before storage — plaintext is shown exactly once at creation and never persists. Functions: `generate_api_key()`, `hash_api_key()`, `create_api_key()`, `verify_api_key()`, `revoke_api_key()`, `delete_api_key()`, `list_api_keys()`.
- **Role-Based Access Control (`auth.py`):** Three-tier role hierarchy — `admin` (full access), `operator` (analyze + read + settings), `viewer` (read-only: events, health, status). Follows the trust-tier pattern from the OWASP Agent Security Checklist.
- **Session Tokens (`auth.py`):** HMAC-SHA256 signed JSON tokens with 1-hour TTL, issued on dashboard login. Stored in `httpOnly` + `SameSite=Strict` cookies. No third-party JWT library. Session signing key derived from the ButterVault master key via HMAC domain separation — Gibson destruction automatically invalidates all active sessions.
- **@require_auth Decorator (`auth.py`):** Flask route decorator with 4-strategy auth chain: `Authorization: Bearer` header → `X-Session-Token` header → session cookie → query parameter (for SSE `EventSource` which cannot set custom headers). Returns structured 401/403 JSON errors. Injects `request.auth_context` with `key_id`, `role`, and `label` for downstream use.
- **Per-API-Key Rate Limiting (`auth.py`):** `is_rate_limited_for_key()` replaces the legacy IP-based rate limiter. Configurable thresholds per role tier: admin (30/min), operator (15/min), viewer (5/min). Sliding window implementation using `collections.deque`.
- **Auth API Endpoints (`auth.py`):** Seven new routes registered via `register_auth_routes(app)`:
  - `POST /api/auth/login` — Exchanges API key for session token. 0.1s delay on failure to prevent brute-force enumeration.
  - `POST /api/auth/logout` — Clears session cookie.
  - `GET /api/auth/whoami` — Returns current identity (role, label, key_id).
  - `GET /api/auth/keys` — Lists all API keys (admin only, hashes redacted).
  - `POST /api/auth/keys` — Creates a new API key with specified role and label. Privilege escalation blocked (operators cannot create admin keys).
  - `DELETE /api/auth/keys/<id>` — Revokes (disables) an API key. Self-revocation blocked to prevent lockout.
  - `DELETE /api/auth/keys/<id>/purge` — Permanently deletes an API key record.
- **Bootstrap CLI (`auth.py`):** `bootstrap_admin_key()` generates a first-run admin API key and prints it to the server terminal. Called automatically on startup if no admin keys exist.
- **New SQLite Table (`auth.py`):** `api_keys` table with `key_id`, `key_hash`, `salt`, `role`, `label`, `created_at`, `last_used`, and `enabled` columns in `butterclaw.db`.
- **Login Modal (`index.html`, `routing.html`):** Full-screen auth modal with API key input, error display, animated transitions, and `ButterClaw v0.6.0 — The Exoskeleton` footer. Blocks all dashboard interaction until authenticated.
- **Session Management JS (`index.html`, `routing.html`):** Shared auth module (~120 lines per file) providing `authFetch()` wrapper (auto-injects Bearer token, auto-clears session + shows login modal on 401/403), `connectAuthSSE()` (appends session token as query param for EventSource), `checkSession()` (validates on page load via `/api/auth/whoami`), `handleLogin()`, `handleLogout()`, and `updateAuthUI()`.
- **Sidebar Auth Badge (`index.html`, `routing.html`):** Identity badge showing current role (color-coded: admin=red, operator=amber, viewer=emerald), label, and logout button. Updates dynamically on login/session check.
- **Auth Diagnostic Mode (`auth.py`):** 10-step self-test suite (`python auth.py`): key generation, hashing, verification, role hierarchy, session token create/verify/expire, rate limiting, bootstrap, and Gibson destruction.

### Changed
- **Route Protection (`server.py`):** All 20 API endpoints now decorated with `@require_auth(min_role=...)` based on endpoint classification. Public: `/api/health`, `/api/vault/oauth/callback`, auth login/logout. Viewer: logs, MCP status/tools/events, vault status, OAuth status, SSE stream. Operator: analyze, settings GET, MCP ping, OAuth start. Admin: vault key store, rotate-keys, shield, MCP restart, settings POST, OAuth revoke.
- **Settings Endpoint Split (`server.py`):** `GET /api/settings` (operator) and `POST /api/settings` (admin) split into separate route handlers to enforce distinct role requirements. Previously a single handler for both methods.
- **Rate Limiter Upgrade (`server.py`):** `analyze_threat()` now uses `is_rate_limited_for_key(ctx["key_id"], ctx["role"])` with per-role thresholds instead of the legacy IP-based `is_rate_limited()`. Error response includes the role-specific limit value.
- **Gibson Kill Switch (`buttervault.py`):** `butter_keys()` now hooks into `auth.destroy_all_api_keys()` after destroying vault and OAuth token ciphertext. Invalidates all API keys and active sessions. Uses `try/except ImportError` for backward compatibility with pre-v0.6.0 deployments.
- **Dashboard API Calls (`index.html`):** All 12 authenticated `fetch()` calls replaced with `authFetch()`. Health check (`/api/health`) correctly excluded as public endpoint. Every `catch` block includes `auth_required` guard to prevent error noise when login modal is shown.
- **Dashboard API Calls (`routing.html`):** All 10 authenticated `fetch()` calls replaced with `authFetch()`. Health check and test ping to arbitrary URLs correctly excluded. Every `catch` block includes `auth_required` guard.
- **SSE Connection (`index.html`):** `new EventSource()` replaced with `connectAuthSSE()` which appends session token as `?token=` query parameter.
- **Dashboard Init (`index.html`):** `connectSSE()` and `fetchLiveLogs()` now gated behind `checkSession().then()` — data loading blocked until session validates.
- **Dashboard Init (`routing.html`):** `init()` function now calls `checkSession()` first and returns early if session is invalid, blocking all gate rendering and data loading.
- **Boot Sequence (`server.py`):** `register_auth_routes(app)` called after CORS setup. `bootstrap_admin_key()` called after `init_db()` and before MCP handshake. Boot banner updated to v0.6.0.
- **Version Bumps (`routing.html`):** Sidebar footer, MCP Armed/Degraded/Offline badges, and MCP Info Box all updated from v0.5.1/v0.5.2 to v0.6.0.

### Architecture Notes

**Endpoint Classification:**

| Tier | Endpoints | Who |
|------|-----------|-----|
| Public | `/api/health`, `/api/vault/oauth/callback`, `/api/auth/login`, `/api/auth/logout` | Anyone (health probes, OAuth redirect, authentication) |
| Viewer | `/api/logs`, `/api/mcp/status`, `/api/mcp/tools`, `/api/mcp/events`, `/api/mcp/events/<id>`, `/api/vault/status`, `/api/vault/oauth/status`, `/api/stream` | Read-only dashboards, monitoring systems |
| Operator | `/api/analyze`, `/api/settings` (GET), `/api/mcp/ping`, `/api/vault/oauth/start/<p>`, `/api/auth/whoami` | Active users running the Sentinel |
| Admin | `/api/vault/key`, `/api/rotate-keys`, `/api/shield`, `/api/mcp/restart`, `/api/settings` (POST), `/api/vault/oauth/revoke/<p>`, `/api/auth/keys` (CRUD) | System owner only |

**What does NOT change (by design):**
- Watcher → Server communication stays unauthenticated (localhost, process-to-process — auth adds latency for zero security gain)
- stdio MCP transport (child process, same machine)
- SSE MCP transport authentication (MCP-spec OAuth 2.1 territory — v0.7+ concern)

**Gibson Destruction Scope (v0.6.0):**
```
butter_keys()
├── UPDATE vault SET ciphertext = garbage           ← Static API keys
├── UPDATE oauth_tokens SET ciphertext = garbage    ← OAuth payloads
└── auth.destroy_all_api_keys()                     ← API key hashes + sessions
```

**Security Design Decisions:**
- HMAC-SHA256 with per-key salt prevents rainbow table attacks
- Constant-time comparison (`hmac.compare_digest()`) prevents timing side-channels
- 0.1s delay on failed login prevents brute-force enumeration
- Session key derived from Vault master key — Gibson automatically invalidates all sessions
- `httpOnly` + `SameSite=Strict` cookies prevent XSS and CSRF on dashboard sessions
- Self-revocation blocked to prevent admin lockout
- Privilege escalation blocked — operators cannot create admin keys
- Plaintext key shown once at creation, never persisted

---

## [0.5.2] - ButterVault OAuth (Credential Lifecycle Management) - 2026-04-16

### Added
- **OAuth Token Storage (`buttervault.py`):** The ButterVault now encrypts and stores structured OAuth token payloads (access token, refresh token, expiry timestamp, token type, scope) as JSON blobs using the same Fernet + OS keyring encryption pipeline trusted for static API keys. New functions: `store_oauth_token()`, `get_oauth_token()`, `delete_oauth_token()`, `list_oauth_providers()`.
- **New SQLite Table (`buttervault.py`):** `oauth_tokens` table with `provider`, `ciphertext`, `created_at`, and `last_refresh` columns. Separate from the `vault` table — same encryption, clean schema separation.
- **Automatic Token Refresh (`buttervault.py`):** `refresh_token_if_needed()` checks token expiry with a 60-second safety buffer, silently refreshes via the provider's token endpoint using the stored refresh token, re-encrypts the new tokens, and updates the Vault. Handles rotating refresh tokens (updates if provider issues a new one). Returns the refreshed token dict or `None` on failure.
- **OAuth Authorization Flow (`server.py`):** Full OAuth 2.0 authorization code flow with four new endpoints:
  - `GET /api/vault/oauth/start/<provider>` — Generates a CSRF-protected authorization URL using `secrets.token_urlsafe(32)`. Client credentials (`client_id`, `client_secret`) are read from the ButterVault, never hardcoded. Google-specific parameters (`access_type=offline`, `prompt=consent`) ensure refresh token acquisition.
  - `GET /api/vault/oauth/callback` — Validates CSRF state (single-use, 10-minute TTL), exchanges the authorization code for tokens via POST to the provider's token endpoint, assembles a structured token dict with computed `expires_at`, and seals it in the ButterVault. Logs a successful connection to the oopsie log (emerald/🔑).
  - `GET /api/vault/oauth/status` — Returns connection status for all OAuth-capable providers: `connected`, `has_refresh_token`, `expires_at`, `expired`, and `has_client_credentials` flags.
  - `POST /api/vault/oauth/revoke/<provider>` — Best-effort remote token revocation at the provider's `revoke_url`, then unconditional local deletion from the Vault regardless of remote result.
- **CSRF State Management (`server.py`):** Thread-safe in-memory state store (`_oauth_states`) with `threading.Lock`, 10-minute TTL, and automatic cleanup of expired tokens on every new flow initiation.
- **OAuth Result Page (`server.py`):** `_oauth_result_page()` helper returns a self-closing HTML popup with success/error styling, `postMessage` to the opener window for cross-window communication, and 2-second auto-close.
- **Vault Diagnostic Mode (`buttervault.py`):** Extended the `if __name__ == "__main__"` test suite with OAuth token store/retrieve and Gibson destruction verification for OAuth payloads.

### Changed
- **Gibson Kill Switch (`buttervault.py`):** `butter_keys()` now atomically destroys **both** the `vault` table (static API keys) AND the `oauth_tokens` table (OAuth payloads). Provider-scoped destruction also hits both tables.
- **Boot Banner (`server.py`):** Updated to v0.5.2.

### Architecture Notes
- `oauth_config.py` remains a pristine static registry — all dynamic URL construction handled by the Flask endpoints in `server.py`.
- Client credentials stored in ButterVault via existing `/api/vault/key` endpoint using provider-namespaced keys (`google_client_id`, `google_client_secret`). If the Vault is Buttered, the OAuth flow cannot start — correct behavior.
- **New Files:** 0. **New Dependencies:** 0. **New SQLite Tables:** 1 (`oauth_tokens`). **New API Endpoints:** 4.

---

## [0.5.1] - Tool Chaining (Multi-Step Execution) - 2026-04-16

### Added
- **ChainExecutor (`server.py`):** New engine allowing the Brain to compose and execute sequential, multi-step MCP tool chains for custom threat response strategies.
- **Condition Evaluator (`server.py`):** Added conditional logic between chain steps using a safe, whitelist-based operator dictionary (`contains`, `not_contains`, `equals`, `not_equals`, `starts_with`). Explicitly avoids arbitrary code execution/`eval()`. Operator logic is case-insensitive and stripped of whitespace.
- **Event Ledger Chain Grouping (`routing.html`):** The ledger UI now visually groups related chain events together by their `chain_id`. Chain blocks feature a consolidated header with a step count, aggregated status icons, and individual step-number badges for each tool execution.
- **Oopsie Card Chain Links (`index.html`):** CRITICAL alerts triggered by a multi-step chain now dynamically render a violet "Multi-Step Chain" badge in the UI action field, alongside a "View in Ledger →" link to trace the execution path.
- **Dynamic Brain Prompting (`server.py`):** The LLM system prompt now dynamically builds the available MCP `tools_context` from the handshake and includes the optional `"chain"` array JSON schema instructions.
- **Safety Rails (`server.py`):** Enforced a hard limit of `MAX_STEPS = 10` and a cumulative total `TIMEOUT = 60` seconds for all chain executions to prevent infinite reasoning loops or stalling.

### Changed
- **CRITICAL Path Routing (`server.py`):** The `analyze_threat` function now intercepts the `"chain"` field from the Brain's output and routes to `ChainExecutor`. If no chain is present, it safely falls back to the legacy hardcoded tool sequence (backward compatible).
- **Vault Integrity Guarantee (`server.py`):** Ensured `buttervault.butter_keys()` is ALWAYS executed locally during a CRITICAL verdict, independently of whether the Brain included `rotate_keys` in its MCP chain contents.
- **Event Ledger Integration (`server.py`):** Tool calls invoked via the `ChainExecutor` now actively populate the `chain_id` and `chain_step` columns in the `mcp_events` SQLite table, linking step sequences together.
- **Step Enumeration (`server.py`):** Improved LLM token efficiency by removing the requirement for the Brain to output specific step numbers, instead deriving `chain_step` dynamically using Python's `enumerate()`.
- **UI State & Copy (`routing.html`, `index.html`):** Version footers bumped to v0.5.1, the MCP Info Box updated to document conditional chaining, and the `ledgerStatusColors` dictionary expanded to support the new `skipped` (violet) step status.

### Fixed
- **Tools List Iteration (`server.py`):** Fixed an `AttributeError` crash during prompt generation by correctly iterating over the `mcp_manager.discovered_tools` list instead of calling `.items()` on it.
- **Orphaned Ledger Entry (`server.py`):** Fixed a bug in `ChainExecutor.execute()` where the exception handler called `ledger_log_start()` without capturing the return value or calling `ledger_log_end()`, leaving ghost "pending" rows in the `mcp_events` table. Now captures `event_id` and closes with `status="error"`.
- **Missing `req_id` (`server.py`):** Fixed two `TypeError` crashes where `ledger_log_start()` was called without the required `req_id` positional argument in the ChainExecutor exception handler and skipped-step path. Both now pass `req_id=None`.

---

## [0.5.0] - The Nervous System (Reasoning Engine + MCP Transport) - 2026-04-14

### Added
- **Event Ledger (`server.py`):** Append-only SQLite audit log (`mcp_events` table) recording every MCP tool invocation with timestamps, request IDs, tool names, arguments, status, results, elapsed time, trigger type, chain ID, and chain step index.
- **Event Ledger API (`server.py`):** Two new endpoints — `GET /api/mcp/events` (with `?limit=`, `?tool=`, `?status=`, `?since=` filters) and `GET /api/mcp/events/<id>` (single event with full payload).
- **Event Ledger UI (`routing.html`):** Interactive timeline view below the MCP panel with status-colored badges, expandable result payloads, tool and status filters, and auto-refresh.
- **SSE Transport (`mcp_transport.py`):** New `StdioTransport` and `SSETransport` classes decoupling I/O from protocol processing. Enables remote MCP clients running on exposed external servers to communicate back to the Brain via SSE without changing tool logic.
- **MCPSSEClient (`server.py`):** SSE-based MCP client for remote tool execution alongside the existing stdio `MCPProcessManager`.
- **MCP Manager Factory (`server.py`):** `create_mcp_manager()` factory function selecting between stdio and SSE transport based on server settings.
- **Memory Injection (`server.py`):** `ledger_query(limit=5, status="success")` sliding window inside `ask_guardian_agent()` provides temporal behavioral tracking to the Brain's reasoning context.
- **MCP Info Box (`routing.html`):** Expandable documentation panel explaining the MCP architecture, transport modes, and tool execution model.
- **SSE Transport Config (`routing.html`):** UI panel for configuring remote SSE endpoint URL, saving to server settings, and restarting MCP with the new transport.

### Changed
- **Self-DoS Prevention (`server.py`):** `CONFIDENCE_THRESHOLD` hardcoded to prevent the paranoia slider from being set below safe minimums.
- **Dynamic Endpoint Resolution (`server.py`):** API endpoints resolve against configurable base URLs instead of hardcoded localhost references.

---

## [0.4.1] - QA Stabilization - 2026-04-12

### Fixed
- **S1 — CSP Violation (`routing.html`):** Removed inline `onclick` handlers and replaced with `addEventListener` to comply with Content Security Policy.
- **S2 — Endpoint Resolution (`routing.html`):** Fixed hardcoded `localhost` references to use dynamic `API_BASE` variable.
- **S3 — JSON Truncation (`server.py`):** Fixed response truncation on large payloads by increasing buffer sizes.
- **S4 — Diagnostic Logic (`buttervault.py`):** Fixed false-positive diagnostic failures when testing on fresh installs with no stored keys.
- **S5 — Error Propagation (`server.py`):** Fixed silent failures in MCP tool execution by properly propagating error responses from child processes.

---

## [0.4.0] - MCP Transport Refactor - 2026-04-10

### Changed
- Refactored MCP communication into modular transport layer.
- Introduced `butterclaw_mcp.py` as the standalone MCP tool server.
- Separated JSON-RPC protocol handling from I/O transport.

---

## [0.3.1] - CSP & Endpoint Fixes - 2026-04-08

### Fixed
- Content Security Policy compliance for routing dashboard.
- Endpoint configuration fixes for non-localhost deployments.

---

## [0.3.0] - Routing Dashboard - 2026-04-06

### Added
- `routing.html` — Advanced configuration dashboard for MCP routing, gate management, and system settings.

---

## [0.2.0] - ButterVault Integration - 2026-04-04

### Added
- `buttervault.py` — Fernet-encrypted credential storage using OS keyring.
- Gibson Kill Switch (`butter_keys()`) for cryptographic credential destruction.
- Vault management UI in the main dashboard.

---

## [0.1.0] - Initial Release - 2026-04-01

### Added
- Core threat analysis engine with Ollama/Gemma integration.
- `watcher.py` — OS-level telemetry collector (process, network, filesystem monitoring).
- `server.py` — Flask API server with SSE real-time dashboard updates.
- `index.html` — Main dashboard with oopsie log, threat analysis, and MCP controls.
- `butterclaw_mcp.py` — MCP tool server with Gibson Kill Switch and key rotation tools.
- Five-gate analysis pipeline: Intent, Origin, Behavior, Sensitivity, Impact.

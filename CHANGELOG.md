# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/)

---

## [0.6.2] - The Exoskeleton: Alert Dispatcher - 2026-05-01

### Added
- **Alert Dispatcher Module (`alert_dispatcher.py`):** New standalone module (~1,566 lines) providing external push notifications when critical events occur. Pushes to 5 channel types: webhook (generic HTTP POST with HMAC-SHA256 signing), Discord (rich embeds), ntfy (push notifications), SMTP email, and Gotify (self-hosted push). Zero new pip dependencies — built entirely on stdlib (`urllib.request`, `smtplib`, `hmac`, `hashlib`).
- **9 Alert Event Types (`alert_dispatcher.py`):** Complete coverage of every critical system event:
  - `verdict_critical` — Brain or Policy returned CRITICAL verdict
  - `verdict_warning` — Brain returned WARNING verdict (≥ 50% confidence)
  - `gibson_triggered` — Automatic Gibson from ChainExecutor critical path
  - `gibson_manual` — Manual Gibson via `/api/rotate-keys`
  - `policy_override` — Policy Engine overrode Brain verdict (pre-brain or post-brain)
  - `policy_blocked` — Policy Engine blocked a request or skipped a tool
  - `auth_brute_force` — 5+ auth failures from one IP within 60 seconds
  - `mcp_offline` — MCP child process health check detected alive→dead transition
  - `system_startup` — ButterClaw server started successfully
- **Channel CRUD (`alert_dispatcher.py`):** `create_channel()`, `get_channel()`, `list_channels()`, `update_channel()`, `delete_channel()`, `toggle_channel()`. Full config validation per channel type — required fields enforced (e.g., webhook requires `url`, smtp requires `host`, `port`, `from_addr`, `to_addr`). Cascade delete removes all rules and history when a channel is deleted.
- **Rule-Based Event Routing (`alert_dispatcher.py`):** `create_rule()`, `get_rule()`, `list_rules()`, `update_rule()`, `delete_rule()`, `toggle_rule()`. Each rule maps one event type to one channel with a configurable cooldown (default 60s, 0 = no cooldown). Per-rule cooldown — same channel can have different cooldowns for different event types.
- **Core Dispatch Engine (`alert_dispatcher.py`):** `dispatch_alert(event_type, context)` — main entry point called from server.py at each integration hook. Finds all enabled rules matching the event type, spawns `_dispatch_worker()` in a daemon thread for non-blocking delivery. `analyze_threat()` returns immediately while alerts fire in the background.
- **Retry with Exponential Backoff (`alert_dispatcher.py`):** Failed deliveries retry with exponential backoff (1s → 2s → 4s, max 3 attempts). Each attempt logged to `alert_history` with response code and error message. Final status: `sent`, `failed`, or `retry_exhausted`.
- **HMAC-SHA256 Webhook Signing (`alert_dispatcher.py`):** Every outbound webhook payload is signed with a per-channel signing secret. Headers: `X-ButterClaw-Signature: sha256=<hex>`, `X-ButterClaw-Event: <event_type>`, `X-ButterClaw-Timestamp: <ISO8601>`. Same pattern as GitHub webhooks — receivers can verify payload authenticity.
- **Per-Channel Payload Formatting (`alert_dispatcher.py`):** `_format_payload()` builds channel-appropriate payloads:
  - `webhook` — JSON with event_type, timestamp, severity, context, instance_id
  - `discord` — Rich embed with color-coded severity sidebar (red=critical, amber=warning, emerald=info), structured fields, footer with version
  - `ntfy` — Title + body + priority mapping (critical=5/urgent, warning=3/default, info=2/low) + tags
  - `smtp` — Subject line with severity emoji + plain-text body with structured fields
  - `gotify` — Title + message + priority (critical=8, warning=5, info=2)
- **Alert History Audit Log (`alert_dispatcher.py`):** `alert_history` table records every dispatch attempt with timestamp, rule_id, channel_id, event_type, status, response_code, error_message, payload_preview (200 chars), and attempt_count. Queryable via `get_alert_history()` with filters for channel_id, event_type, status, since, and limit. `get_alert_history_count()` for totals.
- **Auth Brute-Force Detection (`alert_dispatcher.py`):** `track_auth_failure(ip_address)` tracks 401/403 responses per IP using a thread-safe in-memory sliding window (`collections.deque`). Fires `auth_brute_force` alert when 5 failures from the same IP occur within 60 seconds. Called from server.py via `@after_request` hook.
- **Test Alert (`alert_dispatcher.py`):** `send_test_alert(channel_id)` sends a test notification to any configured channel on demand. Returns delivery result with status, response code, and error message if failed.
- **Cooldown Engine (`alert_dispatcher.py`):** `_is_cooled_down(rule_id, cooldown_secs)` checks `alert_history` for the last successful dispatch within the cooldown window. Prevents alert storms during sustained attacks. Status logged as `cooldown` in history.
- **3 New SQLite Tables (`alert_dispatcher.py`):** All in shared `butterclaw.db`:
  - `alert_channels` — channel_id, name, channel_type, config (JSON), signing_secret, enabled, created_at, last_used, last_status
  - `alert_rules` — rule_id, name, event_type, channel_id (FK), cooldown_secs, enabled, created_at
  - `alert_history` — history_id, rule_id, channel_id, event_type, status, response_code, error_message, payload_preview, attempt_count, created_at
- **13 Alert API Endpoints (`alert_dispatcher.py`):** Registered via `register_alert_routes(app)`:
  - `GET /api/alerts/channels` (viewer) — List all alert channels
  - `POST /api/alerts/channels` (admin) — Create a new channel with config validation
  - `PUT /api/alerts/channels/<id>` (admin) — Update channel config
  - `DELETE /api/alerts/channels/<id>` (admin) — Delete channel (cascades rules + history)
  - `POST /api/alerts/channels/<id>/toggle` (admin) — Enable/disable channel
  - `POST /api/alerts/channels/<id>/test` (operator) — Send test alert to channel
  - `GET /api/alerts/rules` (viewer) — List all rules (filter: event_type, channel_id)
  - `POST /api/alerts/rules` (admin) — Create a new rule
  - `PUT /api/alerts/rules/<id>` (admin) — Update a rule
  - `DELETE /api/alerts/rules/<id>` (admin) — Delete a rule
  - `POST /api/alerts/rules/<id>/toggle` (admin) — Enable/disable rule
  - `GET /api/alerts/history` (viewer) — Query history (filters: channel_id, event_type, status, since, limit)
  - `GET /api/alerts/status` (viewer) — Summary: total channels, active rules, recent dispatches, last alert timestamp
- **14-Step Diagnostic Suite (`alert_dispatcher.py`):** Standalone self-test when run as `python alert_dispatcher.py`: DB init, channel CRUD (5 types), channel validation, channel toggle, rule CRUD, rule validation, rule toggle, webhook signing verification, cooldown enforcement, auth failure tracking (threshold detection), payload formatting (all 5 types), alert history logging, dispatch path (dry run with expected failure), cascade delete cleanup.
- **MCP Health Monitor (`server.py`):** New `mcp_health_monitor()` daemon thread polls MCP process health every 10 seconds. Uses `was_alive` state tracking — dispatches `mcp_offline` only on alive→dead transition (not on persistent-dead, preventing alert storms). Auto-started at module load.
- **Auth Failure Tracking Hook (`server.py`):** `@after_request` decorator on all responses — calls `alert_dispatcher.track_auth_failure(request.remote_addr)` on every 401/403 response. Catches both API key failures and session token failures in one place.
- **Alert Dispatcher UI (`routing.html`):** New full-width section after Policy Engine with:
  - Channel cards — name, type badge (color-coded: webhook=blue, discord=indigo, ntfy=emerald, smtp=amber, gotify=violet), enabled/disabled toggle, last used timestamp, last status badge, config preview (truncated URL — never secrets), Test/Edit/Delete buttons
  - Rule rows — event type label, arrow, channel name, cooldown display, toggle/delete controls
  - Alert history timeline — time-relative timestamps, color-coded status badges (sent=emerald, failed=red, cooldown=amber, retry_exhausted=rose), event type + channel name, event/status filter dropdowns, Load More pagination
  - Channel create/edit modal with dynamic config fields per channel type, signing secret input (webhook only)
  - Rule create modal with event type selector, channel dropdown (populated from enabled channels), cooldown input
  - Status summary bar (channel count, rule count, last alert timestamp)
  - Info box explaining Alert Dispatcher design decisions
- **Alert Dispatch Badge (`index.html`):** Oopsie cards now show a 🔔 "Alert Sent" badge when `alert_dispatched` is true in the SSE payload. Links to routing.html#alertDispatcherSection.
- **Sidebar Nav Links:** 🔔 Alert Dispatcher link added to both `routing.html` (internal anchor) and `index.html` (cross-page link to routing.html#alertDispatcherSection).
- **Tailwind Safelist:** Added indigo color classes (`bg-indigo-50`, `bg-indigo-100`, `border-indigo-200`, `text-indigo-600`) to both files for Discord channel badges.

### Changed
- **Alert Dispatcher Import Guard (`server.py`):** `try: import alert_dispatcher` with `ALERT_DISPATCHER_ENABLED` flag. Graceful degradation — `dispatch_alert()` and `track_auth_failure()` become no-ops when module is not present. All 13 endpoints return 503 when disabled.
- **Route Registration (`server.py`):** `register_alert_routes(app)` called after `register_auth_routes(app)` when `ALERT_DISPATCHER_ENABLED` is True.
- **init_db() (`server.py`):** Now calls `alert_dispatcher.init_alert_db()` after `policy_engine.init_policy_db()` when dispatcher is enabled. Creates 3 new tables.
- **Boot Banner (`server.py`):** Now shows `Alert Dispatcher: ENABLED/DISABLED` alongside Auth and Policy Engine status. `system_startup` alert dispatched after `bootstrap_admin_key()` with version, routing mode, and model name.
- **Verdict Dispatch Hooks (`server.py`):** `dispatch_alert("verdict_critical", ...)` and `dispatch_alert("verdict_warning", ...)` called after final verdict determination in `analyze_threat()`. Context includes payload preview (500 chars), verdict, confidence, primary gate, reasoning preview, source IP, and policy action if applicable.
- **Policy Override/Block Dispatch Hooks (`server.py`):** At each `evaluate_policies()` call site (pre-brain, post-brain, ChainExecutor pre-tool), non-"allow" policy results trigger `dispatch_alert("policy_override", ...)` or `dispatch_alert("policy_blocked", ...)` with scope, policy name, action, original/final verdict, and payload preview.
- **Gibson Alert-Then-Burn Ordering (`server.py`):** All 3 Gibson paths (chain auto, hardcoded fallback, manual rotation) now dispatch the alert BEFORE calling `buttervault.butter_keys()`. Timeline: alert goes out → HTTP requests fire → vault destroyed → auth destroyed → operator receives notification.
- **SSE Oopsie Payload (`server.py`):** Added `alert_dispatched: true` flag when `dispatch_alert()` was called for a verdict. Frontend uses this for the oopsie card badge — no alert content or channel details leak to the frontend.
- **MCP Health Monitoring (`server.py`):** Replaced passive error handling with active health monitor daemon thread. 10-second polling interval with state-transition detection (alive→dead only).
- **Version Bumps:** `VERSION = "0.6.2"` in server.py. 6 version string updates in `routing.html` (sidebar, MCP badges ×3, MCP info box, auth modal). 1 version string update in `index.html` (auth modal footer).
- **Hash-Based Scroll (`routing.html`):** Added `#alertDispatcherSection` handler.
- **Init Sequence (`routing.html`):** `fetchAlertStatus()`, `fetchChannels()`, `fetchRules()`, `fetchAlertHistory()` called after `fetchPolicies()` on session validation.

### Architecture Notes

**Channel Secrets — Why They Live Outside the ButterVault:**

The primary purpose of the Alert Dispatcher is to notify the operator when something catastrophic happens. If Gibson fires and also destroys the ability to notify, that defeats the purpose. Channel secrets (webhook URLs, SMTP passwords, Discord webhook URLs, Gotify tokens) are stored in the `alert_channels` SQLite table, NOT in the ButterVault.

```
Gibson Timeline:
1. dispatch_alert("gibson_triggered", {...})   ← alert goes out over HTTP
2. _dispatch_worker sends to all channels      ← webhook/discord/ntfy/smtp/gotify fire
3. buttervault.butter_keys()                   ← vault destroyed (API keys, OAuth tokens)
4. auth.destroy_all_api_keys()                 ← auth destroyed (sessions invalidated)
5. Operator receives notification              ← Discord ping / email / push arrives
```

If the operator wants to manually purge channel secrets post-Gibson, they can delete channels via the API after re-bootstrapping auth.

**What Survives Gibson (v0.6.2):**

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

**Dispatch Architecture:**

```
server.py hook point
    │
    ▼
dispatch_alert(event_type, context)     ← main thread (non-blocking)
    │
    ├── find matching enabled rules
    ├── spawn daemon thread
    │       │
    │       ▼
    │   _dispatch_worker()              ← background thread
    │       │
    │       ├── for each rule:
    │       │   ├── check cooldown      → skip if within window
    │       │   ├── resolve channel     → get config + type
    │       │   ├── format payload      → channel-specific format
    │       │   ├── sign payload        → HMAC-SHA256 (webhook only)
    │       │   ├── deliver             → HTTP POST / SMTP
    │       │   │   └── retry on fail   → 1s, 2s, 4s (max 3)
    │       │   └── log to history      → status + response code
    │       └── update channel last_used / last_status
    │
    └── return immediately              ← analyze_threat() continues
```

**API Surface (v0.6.2):** 41 total routes

| Category | Count | Auth Tiers |
|----------|-------|------------|
| Auth (v0.6.0) | 7 | admin, operator |
| Core (v0.5.x) | 6 | operator, viewer, admin, public |
| MCP (v0.5.0) | 7 | admin, operator, viewer |
| Vault/OAuth (v0.5.x) | 6 | admin, operator, viewer, public |
| Policy (v0.6.1) | 8 | admin, operator, viewer |
| **Alert (v0.6.2)** | **13** | **admin, operator, viewer** |

**Design Decisions:**

| Decision | Rationale |
|----------|-----------|
| Channel secrets outside ButterVault | Gibson alert must fire before vault destruction |
| Dispatch in daemon thread | Non-blocking — analyze_threat() returns immediately |
| Per-rule cooldown, not per-channel | Same channel can have different cooldowns for different events |
| HMAC-SHA256 webhook signing | Same pattern as GitHub webhooks — receivers verify authenticity |
| Zero new pip dependencies | urllib.request for HTTP, smtplib for email, hmac for signing |
| Retry with exponential backoff | 1s → 2s → 4s handles transient network failures |
| 10s delivery timeout | Prevents slow receivers from blocking dispatch thread |
| alert_dispatched flag in SSE | Frontend knows alert went out without leaking content |
| @after_request for auth tracking | Catches both API key and session failures in one place |
| Cascade delete on channel removal | Prevents orphaned rules/history |
| State-transition MCP monitoring | Only fires on alive→dead, not persistent-dead |

---

## [0.6.1] - The Exoskeleton: Policy Engine - 2026-05-01

### Added
- **Policy Engine Module (`policy_engine.py`):** New standalone module (~350 lines) providing deterministic guardrails for the probabilistic Brain. Implements the DRIFT framework pattern (NeurIPS 2025) — a Dynamic Validator that constrains the Brain's probabilistic reasoning with deterministic rules. Zero new pip dependencies — built entirely on stdlib.
- **3-Scope Filter Pipeline (`policy_engine.py`):** Policies evaluate at three distinct points in the analysis pipeline:
  - `pre_brain` — Pattern-match known-bad/known-good payloads before the Brain. Can short-circuit to CRITICAL or BENIGN without burning inference time.
  - `post_brain` — Validate the Brain's verdict after reasoning. Can override, escalate, downgrade, or require higher confidence.
  - `pre_tool` — Gate individual MCP tool calls inside ChainExecutor. Per-tool allowlist/blocklist.
- **16 Safe Condition Operators (`policy_engine.py`):** Extends ChainExecutor's whitelist operator pattern with: `contains`, `not_contains`, `equals`, `not_equals`, `starts_with`, `ends_with`, `regex_match`, `greater_than`, `less_than`, `greater_equal`, `less_equal`, `in_list`, `not_in_list`, `length_gt`, `length_lt`. All use whitelist dispatch — no `eval()`.
- **Scope-Aware Field Resolvers (`policy_engine.py`):** Each scope provides context-appropriate fields for condition matching:
  - `pre_brain`: 6 fields — `payload`, `threat_type`, `payload_length`, `source_ip`, `hour_of_day`, `day_of_week`
  - `post_brain`: +5 fields — `verdict`, `confidence`, `primary_gate`, `reasoning`, `has_chain`
  - `pre_tool`: +3 fields — `tool_name`, `tool_args`, `chain_step`
- **Policy CRUD (`policy_engine.py`):** `create_policy()`, `get_policy()`, `list_policies()`, `update_policy()`, `delete_policy()`, `toggle_policy()`. Full validation on every write — scope-action compatibility (e.g., `skip_tool` only valid for `pre_tool`, `require_confidence` only valid for `post_brain`), regex compile check at creation time, numeric value validation for comparison operators, `action_params` validation for `require_confidence`.
- **Policy Events Audit Log (`policy_engine.py`):** `policy_events` table records every policy match with timestamp, policy_id, scope, action taken, original verdict, final verdict, payload preview (200 chars), tool name, and chain_id. Queryable via `get_policy_events()` with filters for policy_id, scope, since, and limit. `get_policy_event_count()` for totals.
- **Core Evaluator (`policy_engine.py`):** `evaluate_policies(scope, context)` — loads enabled policies for the given scope in priority order (ascending), evaluates each condition against the context using safe operators. First non-"allow" match wins (short-circuit). "allow" policies are logged but do not stop evaluation. Returns action, policy_id, policy_name, reason, policies_checked, and policies_matched.
- **Dry-Run Testing (`policy_engine.py`):** `test_payload(payload, threat_type)` — evaluates a payload against all 3 scopes without logging events or incrementing hit counters. Simulates Brain output for post_brain testing and tool calls for pre_tool testing.
- **Async Hit Counter (`policy_engine.py`):** `_increment_hit_count()` fires a daemon thread for non-blocking counter updates — never blocks the evaluation hot path.
- **12-Step Diagnostic Suite (`policy_engine.py`):** Self-test via `python policy_engine.py`. Tests: DB init, create (3 scopes), evaluate match/no-match, priority ordering, disabled skip, allow passthrough, unknown operator safety, dry-run, event logging, CRUD (update/toggle/delete), cleanup.
- **New SQLite Tables:** 2 tables added to `butterclaw.db`:
  - `policies` — `id`, `name`, `description`, `priority`, `enabled`, `scope`, `condition` (JSON), `action`, `action_params` (JSON), `created_by`, `created_at`, `updated_at`, `hit_count`
  - `policy_events` — `id`, `timestamp`, `policy_id`, `policy_name`, `scope`, `action_taken`, `original_verdict`, `final_verdict`, `payload_preview`, `tool_name`, `chain_id`
- **8 New API Endpoints (`server.py`):** Policy management endpoints registered with auth decorators:
  - `GET /api/policies` (viewer) — List all policies with optional `?scope=` and `?enabled=` filters.
  - `POST /api/policies` (admin) — Create a new policy rule. Validates required fields, passes `created_by` from `request.auth_context`.
  - `GET /api/policies/<id>` (viewer) — Fetch a single policy by ID.
  - `PUT /api/policies/<id>` (admin) — Update a policy rule.
  - `DELETE /api/policies/<id>` (admin) — Permanently delete a policy.
  - `POST /api/policies/<id>/toggle` (admin) — Enable/disable without deleting.
  - `POST /api/policies/test` (operator) — Dry-run a payload against all policies.
  - `GET /api/policies/events` (viewer) — Query policy event audit log with `?limit=`, `?policy_id=`, `?scope=`, `?since=` filters. Returns events, count, and total.
- **Policy Management UI (`routing.html`):** Full policy engine panel below the Event Ledger section:
  - Policy card list with priority badges, scope-colored badges (emerald=pre_brain, violet=post_brain, amber=pre_tool), action badges, condition previews, hit counts, and inline Toggle/Edit/Delete controls.
  - Scope and status filter dropdowns with auto-refresh on change.
  - Create/Edit modal with dynamic field dropdown (updates based on selected scope), all 15 operators, scope-action compatibility hints (disables incompatible actions), conditional confidence input for `require_confidence` action.
  - Dry-run test panel with payload textarea, threat type selector, 3-column results grid (Pre-Brain / Post-Brain / Pre-Tool), and expandable match details.
  - Info box documenting the DRIFT framework pattern and evaluation semantics.
  - `#policyEngineSection` hash anchor for cross-page deep linking.
- **Policy Override Badge (`index.html`):** Oopsie cards now display a 🛡️ badge when a verdict was influenced by a policy. Four badge variants: "Policy Override" (pre-brain/post-brain escalation), "Policy Fast-Track" (pre-brain benign), "Confidence Gate" (post-brain confidence threshold), "Policy Applied" (generic fallback). Each badge links to `routing.html#policyEngineSection`.
- **Sidebar Nav Links:** Both `index.html` and `routing.html` now include a 🛡️ Policy Engine nav link. Index links to `routing.html#policyEngineSection` (cross-page). Routing links to `#policyEngineSection` (same-page scroll).
- **Tailwind Safelist (`index.html`):** Added `rose` and `violet` color classes for policy badge rendering: `bg-rose-50`, `bg-rose-100`, `border-rose-200`, `text-rose-600`, `text-rose-700`, `bg-violet-50`, `bg-violet-100`, `border-violet-200`, `text-violet-500`, `text-violet-600`.

### Changed
- **Pre-Brain Filter Hook (`server.py`):** `analyze_threat()` now evaluates pre-brain policies before calling `ask_guardian_agent()`. Three outcomes: `override_critical` → skips Brain entirely with verdict=CRITICAL, confidence=1.0, gate=Policy; `override_benign` → skips Brain with verdict=BENIGN; `block` → returns 403 with policy reason. If no policy matches, Brain is called normally. Guarded by `POLICY_ENGINE_ENABLED` flag.
- **Post-Brain Validator Hook (`server.py`):** After the Brain returns a verdict but before the confidence threshold check, post-brain policies can: `override_critical` → escalate to CRITICAL; `override_benign` → downgrade to BENIGN; `require_confidence` → downgrade CRITICAL to WARNING if confidence is below the policy's `min_confidence` threshold. Policy annotations are appended to the `reasoning` field.
- **Pre-Tool Gate in ChainExecutor (`server.py`):** `_execute_step()` now evaluates pre-tool policies before each `mcp_manager.send()` call. `skip_tool` → logs `policy_blocked` status in the Event Ledger and skips the tool. `block` → hard block, tool skipped. Guarded by `POLICY_ENGINE_ENABLED`.
- **Pre-Tool Gate for Hardcoded gibson_kill (`server.py`):** The hardcoded fallback path (when no chain is present) now evaluates pre-tool policies before calling `execute_gibson_kill`. Uses `gibson_blocked` flag pattern — `buttervault.butter_keys()` still fires unconditionally (Sovereign Seal holds). Only the MCP tool call is gated.
- **Pre-Tool Gate for Hardcoded rotate_keys (`server.py`):** Same pattern as gibson_kill — `rotate_blocked` flag prevents the MCP `rotate_keys` call if policy blocks it.
- **Pre-Tool Gate in manual_key_rotation (`server.py`):** The manual Gibson trigger endpoint now evaluates pre-tool policies for `rotate_keys`. Vault destruction fires first (correct), only the MCP call is gated.
- **Policy Engine Import Guard (`server.py`):** `try: import policy_engine` with `except ImportError` sets `POLICY_ENGINE_ENABLED = False` and prints a warning. All policy hooks and endpoints are guarded by this flag — server.py works without policy_engine.py present (backward compat).
- **init_db() Updated (`server.py`):** Now calls `policy_engine.init_policy_db()` when `POLICY_ENGINE_ENABLED` is True. Creates `policies` and `policy_events` tables.
- **Boot Banner (`server.py`):** Now shows `Policy Engine: ENABLED` or `DISABLED` in the startup output. Handshake banner bumped to v0.6.1.
- **All 8 Policy Endpoints Graceful Degradation (`server.py`):** Return 503 with `{"error": "Policy engine not available"}` when `POLICY_ENGINE_ENABLED` is False.
- **Ledger Status Colors (`routing.html`):** Added `policy_blocked` status to `ledgerStatusColors`: `{ bg: 'bg-rose-100', text: 'text-rose-700', dot: 'bg-rose-500' }`.
- **Ledger Status Filter (`routing.html`):** Added `Skipped` and `Policy Blocked` options to the status dropdown.
- **Init Sequence (`routing.html`):** `fetchPolicies()` called after `renderGates()` and `setRoutingMode()` in the init function.
- **Hash-Based Scroll (`routing.html`):** Added `#policyEngineSection` handler alongside existing `#mcpSection` and `#eventLedgerSection`.
- **Version Bumps (`routing.html`):** 6 locations updated from v0.6.0 to v0.6.1 — sidebar footer, MCP Armed/Degraded/Offline badges, MCP Info Box, auth login modal footer.
- **Version Bump (`index.html`):** Auth login modal footer updated from v0.6.0 to v0.6.1.
- **Docstring + VERSION (`server.py`):** Updated to `ButterClaw v0.6.1 — The Exoskeleton (Policy Engine)`, `VERSION = "0.6.1"`.

### Architecture Notes

**Policy Evaluation Pipeline:**
```
Watcher → POST /api/analyze
                │
          ┌─────▼──────────┐
          │ 1. PRE-BRAIN   │ ← Policy Engine: pattern match, fast-track
          │    Filter      │    Can short-circuit to CRITICAL or BENIGN
          │                │    without burning inference time
          └─────┬──────────┘
                │ (if not short-circuited)
          ┌─────▼──────────┐
          │ 2. BRAIN       │ ← Gemma reasoning (unchanged)
          │    (Ollama)    │
          └─────┬──────────┘
                │
          ┌─────▼──────────┐
          │ 3. POST-BRAIN  │ ← Policy Engine: verdict validation
          │    Validator   │    Can override Brain's decision
          └─────┬──────────┘
                │
          ┌─────▼──────────┐
          │ 4. PRE-TOOL    │ ← Policy Engine: per-tool gate
          │    Gate        │    Runs before each MCP send()
          └─────┬──────────┘    inside ChainExecutor
                │
          ┌─────▼──────────┐
          │ 5. MCP Tool    │ ← ChainExecutor or hardcoded fallback
          │    Execution   │
          └────────────────┘
```

**Example Policy Rule:**
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

**Gibson Interaction:**
```
butter_keys()
├── UPDATE vault SET ciphertext = garbage           ← Static API keys
├── UPDATE oauth_tokens SET ciphertext = garbage    ← OAuth payloads
├── auth.destroy_all_api_keys()                     ← API key hashes + sessions
└── policies table: UNTOUCHED                       ← Config survives Gibson
    policy_events table: UNTOUCHED                  ← Audit trail preserved
```

Policies survive Gibson. This is correct behavior — if the Gibson fires and destroys all credentials, you want the policies that triggered or detected the breach to still be there for the post-mortem audit. Policies are operational configuration, not sensitive data.

**Design Decisions:**

| Decision | Rationale |
|---|---|
| Single-condition rules | Compound AND/OR adds complexity for minimal v0.6.1 value — ship simple, extend later |
| Priority-based short-circuit | First non-"allow" match wins — predictable, debuggable |
| Policies survive Gibson | Config, not credentials — needed for post-mortem |
| `try: import policy_engine` | Backward compat — server.py works without policy_engine.py present |
| Regex via `re.search` not `re.match` | `search` finds patterns anywhere in the string — more intuitive for security rules |
| Separate `policy_events` table | Don't pollute `mcp_events` — different audit concern |
| Hit counter on daemon thread | Non-blocking — never slows the evaluation hot path |
| No `eval()` | Same safety principle as ChainExecutor — whitelist operators only |

**New Dependencies:** None. Zero new pip packages.

**New Files:** 1 (`policy_engine.py`)

**New SQLite Tables:** 2 (`policies`, `policy_events`)

**New API Endpoints:** 8

---

## [0.6.0] - The Exoskeleton: API Gateway & Authentication - 2026-04-18

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
- **Bootstrap CLI (`auth.py`):** `bootstrap_admin_key()` generates a first-run admin API key and prints it to the server terminal. Called automatically during server boot after `init_db()`.
- **New SQLite Table (`auth.py`):** `api_keys` table with `key_id`, `key_hash`, `salt`, `role`, `label`, `created_at`, `last_used`, `enabled` columns. Self-managed by auth.py — created on first connection.
- **Dashboard Login Modal (`index.html`, `routing.html`):** Full-screen login modal at `z-[200]` blocks all dashboard interaction until authenticated. API key input with `bc_...` placeholder, error feedback, animated transitions.
- **Auth Session Management JS (`index.html`, `routing.html`):** Shared auth module (~120 lines) providing:
  - `authFetch()` — Wraps `fetch()` with Bearer token injection and auto-redirect to login modal on 401/403.
  - `connectAuthSSE()` — Appends session token as query parameter for EventSource connections.
  - `checkSession()` — Validates token via `/api/auth/whoami` on page load.
  - `handleLogin()` / `handleLogout()` — Full login/logout lifecycle with localStorage session persistence.
  - `updateAuthUI()` — Role badge colors (admin=red, operator=amber, viewer=emerald) in sidebar.
- **Sidebar Auth Badge (`index.html`, `routing.html`):** Auth identity badge with role indicator, label text, and Logout button. Positioned above MCP/connection badges.
- **Auth Diagnostic Mode (`auth.py`):** 10-step self-test suite via `python auth.py`. Tests key generation, hashing, verification, session tokens, rate limiting, role hierarchy, and CRUD operations.

### Changed
- **Route Protection (`server.py`):** All 20 existing routes decorated with `@require_auth()` at appropriate role tiers. Public: `/api/health`, `/api/vault/oauth/callback`. Viewer: logs, status, events, stream. Operator: analyze, settings GET, ping, OAuth start. Admin: vault key, rotate-keys, shield, settings POST, MCP restart, OAuth revoke.
- **Settings Split (`server.py`):** `/api/settings` split into two functions — GET requires `operator`, POST requires `admin`. Operators can read settings but only admins can modify.
- **Per-Key Rate Limiter (`server.py`):** `analyze_threat()` now uses `is_rate_limited_for_key(ctx["key_id"], ctx["role"])` instead of the legacy IP-based rate limiter. Error messages show the per-role limit.
- **Gibson Auth Hook (`buttervault.py`):** `butter_keys()` now calls `auth.destroy_all_api_keys()` after vault destruction. Uses `try/except ImportError` for backward compatibility with pre-v0.6.0 deployments.
- **authFetch Wrapping (`index.html`):** 12 `fetch()` calls wrapped with `authFetch()` — paranoia init/save, shield toggle, vault status/key, OAuth start/revoke/status, rotate-keys, logs, simulate attack, MCP status.
- **authFetch Wrapping (`routing.html`):** 10 `fetch()` calls wrapped with `authFetch()` — settings load/save, gate save, MCP status/tools/ping/restart, SSE save/restart, ledger fetch.
- **SSE Auth (`index.html`):** `connectSSE()` now uses `connectAuthSSE()` to pass session token as query parameter.
- **Dashboard Init Gating (`index.html`, `routing.html`):** Page init functions now call `checkSession()` first — data loading and SSE connection only proceed if session is valid.
- **Boot Sequence (`server.py`):** `bootstrap_admin_key()` called after `init_db()` and before MCP handshake. Prints admin key to terminal on first run.
- **Version Bumps (`routing.html`):** 5 locations updated — sidebar footer, MCP Armed/Degraded/Offline badges, MCP Info Box. All bumped from v0.5.1 to v0.6.0.
- **Auth Error Handling (`index.html`, `routing.html`):** Every `catch` block after `authFetch()` includes `if (e.message === 'auth_required') return;` to prevent error noise when login modal is shown.
- **Docstring + VERSION (`server.py`):** Updated to `ButterClaw v0.6.0 — The Exoskeleton (API Gateway & Auth)`, `VERSION = "0.6.0"`.
- **Docstring (`buttervault.py`):** Updated to v0.6.0 with `[v0.6.0] The Gibson now hooks into auth.py to destroy API key hashes.`

### Architecture Notes

**Authentication Flow:**
```
Browser → index.html / routing.html
        → checkSession() → GET /api/auth/whoami
        → No valid session → showLoginModal()
        → User enters API key → POST /api/auth/login
        → Server verifies key hash (HMAC-SHA256 + salt)
        → Returns session token (HMAC-signed JSON, 1hr TTL)
        → Token stored in localStorage + httpOnly cookie
        → authFetch() injects Bearer header on all API calls
        → 401/403 → auto-clear session → show login modal
```

**Endpoint Classification:**

| Tier | Endpoints | Who |
|---|---|---|
| Public | `/api/health`, `/api/vault/oauth/callback`, `/api/auth/login`, `/api/auth/logout` | Anyone |
| Viewer | `/api/logs`, `/api/mcp/status`, `/api/mcp/tools`, `/api/mcp/events`, `/api/mcp/events/<id>`, `/api/vault/status`, `/api/vault/oauth/status`, `/api/stream`, `/api/auth/whoami` | Read-only dashboards |
| Operator | `/api/analyze`, `/api/settings` (GET), `/api/mcp/ping`, `/api/vault/oauth/start/<p>` | Active operators |
| Admin | `/api/settings` (POST), `/api/vault/key`, `/api/rotate-keys`, `/api/shield`, `/api/mcp/restart`, `/api/vault/oauth/revoke/<p>`, `/api/auth/keys` (all methods) | System owner |

**Gibson Destruction Scope (v0.6.0):**
```
butter_keys()
├── UPDATE vault SET ciphertext = garbage           ← Static API keys
├── UPDATE oauth_tokens SET ciphertext = garbage    ← OAuth payloads
└── auth.destroy_all_api_keys()                     ← API key hashes + sessions
```

After Gibson: all authentication invalidated. System requires fresh `bootstrap_admin_key()` to re-enter.

**What Does NOT Change:**

| Component | Why |
|---|---|
| Watcher → Server comm | Localhost process-to-process — auth adds latency for zero gain |
| stdio MCP transport | Child process, same machine |
| SSE MCP transport auth | MCP-spec OAuth 2.1 territory — v0.7+ concern |
| `butterclaw_mcp.py` | Execution layer, auth-unaware by design |
| `mcp_transport.py` | Transport is auth-agnostic |
| `oauth_config.py` | Static registry — stays pristine |

**Security Design:**

| Decision | Rationale |
|---|---|
| HMAC-SHA256 with per-key salt | Prevents rainbow table attacks |
| Constant-time comparison | `hmac.compare_digest()` prevents timing side-channels |
| 0.1s delay on failed login | Prevents brute-force enumeration |
| Session key derived from Vault master | Gibson destruction invalidates all sessions |
| httpOnly + SameSite=Strict cookies | Prevents XSS and CSRF |
| Self-revocation blocked | Can't revoke your own admin key (prevents lockout) |
| Privilege escalation blocked | Operators can't create admin keys |
| Plaintext shown once | `create_api_key()` returns raw key exactly once |

**New Dependencies:** None. Zero new pip packages.

**New Files:** 1 (`auth.py`)

**New SQLite Tables:** 1 (`api_keys`)

**New API Endpoints:** 7

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
- **Gibson Kill Switch (`buttervault.py`):** `butter_keys()` now destroys **both** the `vault` table (static API keys) AND the `oauth_tokens` table (OAuth payloads) in a single atomic operation. Both global and provider-scoped destruction hit both tables. The Sovereign Seal holds — OAuth tokens are mathematically annihilated alongside static keys.
- **Client Credential Architecture (`server.py`):** OAuth client credentials (`client_id`, `client_secret`) are stored in the ButterVault via the existing `/api/vault/key` endpoint using provider-namespaced keys (e.g., `google_client_id`, `google_client_secret`). The OAuth start endpoint reads them from the Vault at flow initiation time. If the Vault is Buttered, the OAuth flow cannot start — correct behavior.
- **New Imports (`server.py`):** Added `import secrets` (CSRF token generation), `from urllib.parse import quote` (URL encoding without `requests.utils` dependency), and `import oauth_config` (provider registry access).
- **Version Strings:** All files updated to `v0.5.2`.

### Fixed
- **Orphaned Ledger Entry (`server.py`):** Fixed a bug in `ChainExecutor.execute()` where the exception handler called `ledger_log_start()` but never called `ledger_log_end()`, leaving a permanent `pending` row in the `mcp_events` table for any chain step that threw an exception. Now captures the `event_id` and closes the entry as `status="error"` with the exception message.

### Architecture Notes

**OAuth Token Lifecycle:**
```
User clicks "Connect" → Frontend calls /api/vault/oauth/start/google
                         → Server reads client_id from Vault
                         → Server generates CSRF state token
                         → Server returns authorization URL
                         → Frontend opens popup to Google
                         → User authorizes
                         → Google redirects to /api/vault/oauth/callback
                         → Server validates CSRF state
                         → Server exchanges code for tokens
                         → Server seals tokens in ButterVault
                         → Popup closes, signals parent via postMessage
```

**Token Refresh Flow:**
```
Any tool needs OAuth token → refresh_token_if_needed(provider, ...)
                            → Decrypt token from Vault
                            → Check: time.time() < (expires_at - 60)?
                            → Yes: return token (still valid)
                            → No: POST refresh_token to provider
                            → Re-encrypt new tokens in Vault
                            → Return refreshed token
```

**Gibson Destruction Scope (v0.5.2):**
```
butter_keys()
├── UPDATE vault SET ciphertext = garbage        ← Static API keys
└── UPDATE oauth_tokens SET ciphertext = garbage ← OAuth payloads
```

**OAuth-Capable Providers (from oauth_config.py):**

| Provider | Auth Method | OAuth Status |
|---|---|---|
| Anthropic (Claude) | API key only | ❌ No public OAuth |
| OpenRouter | API key only | ❌ No public OAuth |
| Google Cloud (Gemini) | OAuth 2.0 | ✅ Endpoints configured |
| GitHub | OAuth 2.0 | ✅ Endpoints configured |

**New Dependencies:** None. Token exchange uses existing `requests` library. CSRF uses stdlib `secrets`.

**New Files:** None. `oauth_config.py` was created in v0.5.0 — unchanged in v0.5.2 (static registry, no behavioral code added).

**New SQLite Tables:** 1 (`oauth_tokens`)

**New API Endpoints:** 4 (`/start`, `/callback`, `/status`, `/revoke`)

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

---

# Changelog: ButterClaw v0.5.0
Release Date: April 13, 2026

## [0.5.0] - The Nervous System (Event Ledger + SSE Transport)

### Added
- **MCP Event Ledger (`server.py`):** Persistent, append-only audit log of every MCP tool invocation. New `mcp_events` SQLite table tracks timestamp, JSON-RPC id, method, tool name, arguments, status (pending/success/error/timeout), result (truncated to 4KB), elapsed time in ms, trigger source (auto/manual/critical/handshake/ping), and chain metadata (chain_id, chain_step) for future v0.5.1 tool chaining. Every `send()` call in both `MCPProcessManager` and `MCPSSEClient` writes a `pending` row before dispatch, then updates it with the outcome after response/timeout/error.
- **Event Ledger API Endpoints (`server.py`):**
  - `GET /api/mcp/events` — Query the ledger with optional filters: `?limit=`, `?tool=`, `?status=`, `?since=`. Returns events array, count, and total.
  - `GET /api/mcp/events/<id>` — Fetch a single event with full result payload.
- **Event Ledger UI Panel (`routing.html`):** New "Event Ledger" section below the MCP panel with a cyan/teal gradient header. Features:
  - Filterable by tool name and status via dropdown selectors
  - Each event row shows tool name, status dot (color-coded), elapsed ms, timestamp, and event ID
  - Collapsible result preview — click "Show result" to expand the JSON response inline
  - Arguments displayed as a truncated mono line
  - Trigger source and chain metadata shown for non-auto events
  - Auto-refreshes every 30s alongside MCP status polling
  - Manual refresh button
- **Event Ledger Nav Link (`index.html`):** New sidebar navigation entry "Event Ledger" linking to `routing.html#eventLedgerSection`.
- **Temporal Memory Injection (`server.py`):** Cured "LLM amnesia" by patching `ask_guardian_agent()` to query the new `mcp_events` ledger before evaluating a log. The Brain now receives a sliding window of recent tool executions (temporal context) to detect behavioral drift over time rather than evaluating isolated snapshots.
- **Stateless Self-Reflection / The Auditor (`server.py`):** `run_self_audit()` background daemon fires 30 seconds after any CRITICAL verdict. Uses the same Gemma 4 model at `temperature: 0.0` to review the sanitized event ledger and flag potential false positives without giving the AI authority to lower its own shields.
- **Dynamic Dual-Persona Prompting (`server.py`):** Embedded complex JSON schemas and dual-persona instructions (The Instinct vs. The Auditor) directly into the Flask API request payloads. This guarantees 100% plug-and-play portability for users cloning the repo and running vanilla `gemma4:e4b`, eliminating the strict requirement for a custom compiled `Modelfile`.
- **Transport Abstraction Layer (`mcp_transport.py` — NEW FILE):** Decouples MCP I/O from protocol logic. Two transport implementations behind a common `BaseTransport` interface (`read()`, `write()`, `start()`, `stop()`):
  - `StdioTransport` — Wraps stdin/stdout. Extracts the I/O loop that was previously inline in `butterclaw_mcp.py`'s `main()`.
  - `SSETransport` — Runs a threaded HTTP server using stdlib `http.server` (zero new pip dependencies). `GET /sse` opens a Server-Sent Events stream, `POST /message` receives JSON-RPC requests. Supports optional bearer token authentication. Sends 30s keepalive comments to prevent connection timeout. First SSE event is `event: endpoint` telling the client where to POST (MCP SSE spec compliant).
  - `create_transport()` factory function for CLI flag → transport instance creation.
- **SSE Transport CLI Flags (`butterclaw_mcp.py`):** New argparse flags:
  - `--transport stdio|sse` — Select transport mode (default: stdio)
  - `--bind HOST` — Bind address for SSE (default: 127.0.0.1)
  - `--port PORT` — Port for SSE (default: 5001)
  - `--token SECRET` — Bearer token for SSE auth. Required when binding to 0.0.0.0.
  - Safety: binding to 0.0.0.0 without --token is rejected at startup.
- **MCPSSEClient (`server.py` — NEW CLASS):** Connects to a remote MCP server running SSE transport. Same interface as `MCPProcessManager` (`BaseMCPManager`):
  - `send()` POSTs JSON-RPC to `/message`, waits for correlated response on the SSE stream
  - `_read_sse_stream()` background thread parses SSE events, handles endpoint discovery, message correlation, and automatic reconnection (5s backoff)
  - Health check via `GET /health` on startup
  - Auth via `Authorization: Bearer <token>` header on all requests
  - Ledger integration: every `send()` logs to the event ledger identically to stdio manager
- **BaseMCPManager Interface (`server.py`):** Abstract base class defining the common interface for both `MCPProcessManager` and `MCPSSEClient`. Both implement `send()`, `notify()`, `handshake()`, `status()`, `start()`, `stop()`, `restart()`, `is_alive`, and `transport_name`.
- **MCP Manager Factory (`server.py`):** `create_mcp_manager()` reads `mcp_transport_mode` and `mcp_sse_url` from config to instantiate the correct manager. `mcp_restart` endpoint detects transport mode changes and swaps the manager instance.
- **Transport Selector UI (`routing.html`):** New toggle in the MCP panel — stdio vs SSE buttons with violet highlight. Selecting SSE reveals a config panel with URL input, token input, and "Save SSE Config & Restart MCP" button. Saves to `/api/settings` then triggers `/api/mcp/restart`.
- **MCP Transport Settings (`server.py`):** Three new config fields exposed via `/api/settings`:
  - `mcp_transport` — "stdio" or "sse"
  - `mcp_sse_url` — Remote MCP server URL
  - `mcp_sse_token_set` — Boolean (token existence, never exposes the actual token)
- **OAuth Provider Registry (`oauth_config.py` — NEW FILE):** Skeleton configuration mapping provider names to OAuth endpoints, scopes, and metadata. Four providers registered:
  - Anthropic (Claude) — api_key only (no public OAuth as of April 2026)
  - OpenRouter — api_key only
  - Google Cloud (Gemini) — OAuth 2.0 supported, endpoints configured
  - GitHub — OAuth 2.0 supported, endpoints configured
  - Helper functions: `get_provider()`, `list_providers()`, `list_oauth_capable()`, `list_api_key_only()`, `get_auth_method()`

### Changed
- **`butterclaw_mcp.py` Main Loop:** Refactored from raw `sys.stdin.readline()` / `sys.stdout.write()` to `transport.read()` / `transport.write()`. Protocol handler (`ButterClawMCPServer.route()`) was already transport-agnostic — only the I/O layer changed. Added `KeyboardInterrupt` handler and `finally` block for clean transport shutdown.
- **`server.py` Import Alias:** `import requests` renamed to `import requests as http_requests` to avoid collision with Flask's `request` object now that both are used in the SSE client.
- **`/api/mcp/status` Response:** Now includes `transport_mode` ("stdio" or "sse"), `event_count` (total ledger entries), and `remote_url` (for SSE clients).
- **`/api/mcp/restart` Endpoint:** Detects if the transport mode changed since the current manager was created. If so, stops the old manager and creates a new one via the factory before restarting.
- **`/api/mcp/ping` Endpoint:** Now passes `trigger="ping"` to `send()`, so pings are recorded in the event ledger.
- **`/api/settings` GET Response:** Now includes `mcp_transport`, `mcp_sse_url`, and `mcp_sse_token_set`.
- **Version Strings:** All files updated to `v0.5.0` — `server.py`, `butterclaw_mcp.py`, `routing.html` footer/badges, `index.html` comments.
- **MCP Info Box Text (`routing.html`):** Updated description to mention dual transport and event ledger.

### Architecture Notes

**Transport Abstraction:**
```
ButterClawMCPServer.route(request) → response
          ↑                    ↓
  transport.read()     transport.write()
          ↑                    ↓
     ┌────┴────┐          ┌────┴────┐
     │  stdio  │          │   SSE   │
     │ (local) │          │(network)│
     └─────────┘          └─────────┘
```

**Event Ledger Schema:**
```sql
CREATE TABLE mcp_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,         -- ISO 8601 UTC
    req_id      INTEGER,               -- JSON-RPC id
    method      TEXT NOT NULL,         -- e.g. "tools/call"
    tool_name   TEXT,                  -- e.g. "execute_gibson_kill"
    arguments   TEXT,                  -- JSON string of input args
    status      TEXT NOT NULL,         -- pending | success | error | timeout
    result      TEXT,                  -- JSON string (truncated to 4KB)
    elapsed_ms  REAL,                  -- round-trip time
    trigger     TEXT DEFAULT 'auto',   -- auto | manual | critical | handshake | ping
    chain_id    TEXT,                  -- groups steps in a chain (v0.5.1)
    chain_step  INTEGER               -- step number within chain (v0.5.1)
);
```

**Dual Manager Architecture:**
```
server.py
│
├── mcp_manager = create_mcp_manager()
│   │
│   ├── MCPProcessManager (stdio) ← local child process
│   │   ├── stdin writer
│   │   ├── stdout reader thread
│   │   ├── stderr drain thread
│   │   └── ledger hooks in send()
│   │
│   └── MCPSSEClient (sse) ← remote HTTP
│       ├── POST /message sender
│       ├── SSE stream reader thread
│       ├── auto-reconnect (5s backoff)
│       └── ledger hooks in send()
│
└── Both implement BaseMCPManager interface
```

**New Dependencies:** None. SSE transport uses stdlib `http.server` and `threading`. SSE client uses existing `requests` library.

**New Files:**
- `mcp_transport.py` — Transport abstraction layer (~250 lines)
- `oauth_config.py` — OAuth provider registry skeleton (~100 lines)

---

### 📦 v0.4.1 Complete Delivery Recap

| File | Status | Key Fixes |
|---|---|---|
| **`routing.html`** | ✅ Delivered | R1 🔴 CSP comment removed; R2 🟡 dynamic protocol version; R3 🟡 auto-refresh on armed transition |
| **`server.py`** | ✅ Delivered | S1 🔴 auto-restart chains handshake; S2–S5 🟡 thread safety, TOCTOU, MCP truth-telling, module-level threshold |
| **`butterclaw_mcp.py`** | ✅ Delivered | M1 🟡 error correlation; M2 🟡 arg validation; M3 🟢 basicConfig documented; M4 🟢 pre-init guard |
| **`index.html`** | ✅ Delivered | Clean — version alignment only |
| **`CHANGELOG.md`** | ✅ Delivered | Full v0.4.1 QA audit entry with all 15 findings |

### Patched — v0.4.0 QA Audit for v0.4.1

Audit Date: April 11, 2026
Scope: Full codebase review of v0.4.0 release — 4 files audited
Findings: 15 total — 2 🔴 Bugs, 7 🟡 Issues, 6 🟢 Notes

#### `routing.html` — 3 patches (R1, R2, R3)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| R1 | 🔴 Bug | HTML comment placed **inside** the CSP `content` attribute. Browsers parse `<!--` as literal CSP text, not as a comment — likely breaking the `img-src 'self' data:` directive that follows. **Introduced by the v0.3.2 B1 patch itself.** | Removed the comment from inside the attribute. Audit trail preserved as a normal HTML comment above the `<meta>` tag. |
| R2 | 🟡 Issue | Protocol version `"2024-11-05"` hardcoded in a static `<div>` in the MCP info grid. If `butterclaw_mcp.py` updates its `protocolVersion`, the UI shows stale info. | Changed to dynamic: `mcpProtocolVersion` div populated from `/api/mcp/status` response. |
| R3 | 🟡 Issue | `mcpFetchTools()` runs once at page load and on manual Refresh click — not on a periodic interval. When the server transitions from offline → online, the tool list stays empty until manual refresh. | Added `_prevMcpArmed` state tracking. `mcpCheckStatus()` now calls `mcpFetchTools()` automatically when state transitions from non-armed → armed. |

#### `server.py` — 5 patches (S1, S2, S3, S4, S5)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| S1 | 🔴 Bug | **`send()` auto-restart skips handshake.** When `send()` detects a dead child, it calls `self.start()` but **not** `self.handshake()`. After auto-restart: `handshake_ok` stays `False`, `discovered_tools` is empty/stale. | Added `self.handshake()` after `self.start()` in the auto-restart block inside `send()`. |
| S2 | 🟡 Issue | `_req_counter += 1` is not atomic. Two concurrent Flask threads calling `send()` could receive the same `req_id`. | Replaced with `itertools.count(1)` — thread-safe in CPython without requiring a lock. |
| S3 | 🟡 Issue | `status()` has a TOCTOU race on `self.process`. Between the truthiness check and `.pid` access, another thread could call `stop()` and set `self.process = None`. | Snapshot the reference: `proc = self.process` at the top of `status()`, use `proc` throughout. |
| S4 | 🟡 Issue | **CRITICAL verdict path ignores MCP `send()` return values.** If the MCP child is dead or calls timeout, `action` still reports `"SIGKILL \| Keys Buttered"`. | Capture return values. Check for `"error"` key. Append failure details to the action string. |
| S5 | 🟡 Issue | `CONFIDENCE_THRESHOLD = 85` defined as a local variable inside `analyze_threat()`, but the boot banner hardcodes `85` separately. | Extracted `CONFIDENCE_THRESHOLD` to module-level constant. Both references linked. |

#### `butterclaw_mcp.py` — 4 patches (M1, M2, M3, M4)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| M1 | 🟡 Issue | General exception handler sends `"id": None` in error response even though the parsed request dict may be in scope. Parent can't correlate → falls through as "Orphaned response" → parent times out. | Track `last_request` after successful JSON parse. General `except Exception` block now sends `"id": last_request.get("id")`. |
| M2 | 🟡 Issue | `handle_tools_call` passes `**tool_args` directly to tool functions with no schema validation. | Built `_TOOL_ALLOWED_ARGS` lookup from `inputSchema.properties` at module load. Intersects incoming keys against allowed keys. |
| M3 | 🟢 Note | `logging.basicConfig()` is at module level — flagged previously but architecturally correct since this file runs as a standalone subprocess. | Added architectural comment documenting the justification. |
| M4 | 🟢 Note | `initialized` flag is set in `handle_initialize` but never checked — `tools/call` doesn't gate on whether `initialize` was called first. | Added `if not self.initialized` guard in `handle_tools_call` returning `-32002` (Server not initialized). |

#### `index.html` — Clean (version alignment only)

| ID | Severity | Finding | Fix |
|----|----------|---------|-----|
| — | 🟢 Clean | No issues found. CSP is tight, all dynamic content uses `textContent` and `createElement`. | Version comments updated from v0.4.0 → v0.4.1 for alignment. |

#### Cross-File Audit Notes — 🟢 Positive

| # | Scope | Finding |
|---|-------|---------|
| N1 | `index.html`, `routing.html` | XSS safety maintained — all new MCP panel code uses `textContent` and `createElement`. No `innerHTML` with server data. |
| N2 | `index.html`, `routing.html` | MCP badge visual states are consistent — both pages use the same three-state model (Armed / Degraded / Offline). |
| N3 | `server.py` | ButterVault remains a direct local call — `buttervault.butter_keys()` in the CRITICAL path is not routed through MCP. |
| N4 | `server.py` | Reader thread shutdown is clean — `stop()` properly wakes all waiting threads via `event.set()` before clearing `_pending`. No zombie threads. |
| N5 | `butterclaw_mcp.py` | `notify()` is spec-correct — omits `"id"` from the JSON-RPC payload, producing a valid notification per JSON-RPC 2.0. |
| N6 | `server.py` | stderr drain solved — `_read_stderr` runs as a daemon thread, continuously draining and logging child stderr. |

---

# Changelog: ButterClaw v0.4.0
Release Date: April 9, 2026

## [0.4.0] - The Claws Awaken (MCP Transport & Observability)

### Added
- **Full MCP Protocol Compliance (`butterclaw_mcp.py`):** The execution layer now speaks real Model Context Protocol over stdio. `initialize` returns `protocolVersion` (`2024-11-05`), `serverInfo`, and proper `capabilities` shape. Added `tools/list`, `ping`, and `notifications/initialized` handlers. Tool results now return MCP-standard content arrays (`{content: [{type: "text", text: "..."}], isError: bool}`).
- **Threaded MCP Process Manager (`server.py`):** Replaced the inline blocking `stdout.readline()` with a dedicated `MCPProcessManager` class. Stdout and stderr each get their own daemon reader thread — Flask never blocks on MCP I/O, and the child process never deadlocks from a full stderr pipe.
- **Response Correlation by ID:** MCP requests are tracked via a `_pending` dictionary keyed by JSON-RPC `id`. The stdout reader thread wakes the correct waiting sender via `threading.Event`.
- **Configurable Timeouts:** Every `MCPProcessManager.send()` call accepts a `timeout` parameter (default 10s).
- **Auto-Restart:** If `send()` detects a dead child process, it automatically respawns and re-runs the handshake before retrying.
- **3-Step MCP Handshake (`server.py`):** initialize → notifications/initialized → tools/list.
- **4 New API Endpoints (`server.py`):** `/api/mcp/status`, `/api/mcp/ping`, `/api/mcp/tools`, `/api/mcp/restart`.
- **Expanded Tool Registry (`butterclaw_mcp.py`):** 5 tools (up from 2): `execute_gibson_kill`, `rotate_keys`, `system_status`, `scan_port`, `log_event`.
- **MCP Sidebar Badge (`index.html`):** New status indicator showing MCP state (Armed / Degraded / Offline).
- **Live MCP Panel (`routing.html`):** Process status, ping, restart, and dynamic tool list with `inputSchema` inspection.

### Changed
- **Dispatch Table Architecture (`butterclaw_mcp.py`):** Replaced `if/elif` routing with `METHOD_MAP` and `TOOL_DISPATCH` dicts.
- **Tool Schema Field Name:** Now uses `inputSchema` (MCP standard) instead of `parameters`.
- **JSON-RPC Error Codes:** Proper codes throughout — `-32700`, `-32601`, `-32602`, `-32603`.
- **MCP Commands in Analyze Path (`server.py`):** CRITICAL responses now push through `MCPProcessManager` (non-blocking, correlated).
- **Version Strings:** All files updated to `v0.4.0`.

### Fixed
- **Flask Thread Blocking:** Eliminated inline `stdout.readline()` on Flask request threads.
- **Child Deadlock Risk:** stderr now drained continuously by dedicated thread.
- **Orphaned Response Handling:** Unknown response IDs logged with warning instead of silently dropped.
- **Handshake Failure Visibility:** Failed handshake now sets `handshake_ok = False` for truthful status reporting.

---

### Patched — v0.3.1 QA Audit for v0.3.2

Audit Date: April 5, 2026
Scope: Full codebase review of v0.3.1 release — 5 files audited
Findings: 13 total — 5 🔴 Bugs, 8 🟡 Issues, 6 🟢 Notes

*(See v0.3.2 patch notes in CHANGELOG v0.4.0 section above for full audit details.)*

---

# Changelog: ButterClaw v0.3.1
Release Date: April 4, 2026

## [0.3.1] - Reasoning Engine (Self-DoS & Stability Patch)

### Added
- **Self-DoS Prevention:** `CONFIDENCE_THRESHOLD` (85%) prevents weak CRITICAL verdicts from triggering the Gibson.

### Fixed
- **LLM Hallucination Handling:** Confidence formatting correction and clamping to [0.0, 1.0].
- **Execution Hot-Paths:** Module imports moved to top-level scope.

---

# Changelog: ButterClaw v0.3
Release Date: April 4, 2026

## [0.3.0] - The ButterVault & MCP Scaffold

### Added
- **The ButterVault (`buttervault.py`):** AES-encrypted API key storage via OS-native `keyring`.
- **Live Ammunition:** Gibson Kill Switch physically overwrites Vault ciphertexts.
- **True MCP Scaffolding:** `ButterClawMCPServer` with JSON-RPC tool schemas.
- **Hardware Profiles:** `Modelfile.example` for tuned local GPU inference.

### Changed
- **Brain Upgrade:** Pivoted from `phi3` to `gemma4:e4b`.
- **Context Expansion:** Watcher log truncation limit increased from 500 to 4096 characters.

---

## [0.2.1] — The Mind Reader Update - 2026-03-xx

### Added
- **Logic Gate Trace:** `primary_gate` field forcing the Brain to identify the analytical vector.
- **UI Mind Reader Window:** Displays triggering logic gate next to confidence score.

### Changed
- **Terminology Pivot:** "Deterministic" → "Probabilistic".

---

## [0.2.0] — The Kinetic Update - 2026-03-xx

### Added
- **The Claws (`butterclaw_mcp.py`):** MCP execution layer for OS-level interventions.
- **Gibson Kill Switch:** Dry Run safety harness for simulated SIGKILL and key rotation.
- **Structured JSON Intelligence:** Strict JSON schema output.
- **Confidence Scoring:** Probabilistic confidence score (0.0 - 1.0).

### Changed
- **The Brain:** Transitioned from passive "judge" to active "Sentinel".

### Fixed
- **The Box Trap:** Non-deterministic text outputs no longer crash the parser.

---

## [0.1.1] — Security & Routing Update - 2026-03-23

52 patches across 4 files. Zero new dependencies.

---

## [0.1.0] — Initial Prototype Release — 2026-03-17

- Prototype dashboard (`index.html`)
- Flask API server (`server.py`)
- Log watcher daemon (`watcher.py`)
- Ollama + Phi-3 local inference
- SQLite short-term memory
- SSE log streaming

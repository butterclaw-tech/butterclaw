# 🔒 Security Architecture & ASI Coverage

ButterClaw was architected to protect autonomous AI agents from both external exploitation and internal hallucinations.

## Base Security Mechanisms

| Layer | Mechanism |
|---|---|
| **TLS** | nginx reverse proxy with TLSv1.2/1.3, ECDHE ciphers, HSTS |
| **Container** | Non-root user, read-only filesystem, `ProtectSystem=strict`, `NoNewPrivileges=true`, `ProtectHome=true`, `PrivateTmp=true` |
| **Authentication** | HMAC-SHA256 API keys, HMAC-signed session tokens, `httpOnly` cookies |
| **Authorization** | 4-tier RBAC (infrastructure/admin/operator/viewer) |
| **Policy** | Deterministic `pre_brain` / `post_brain` / `pre_tool` guardrails via DRIFT engine |
| **Alerting** | 6 external channels (webhook, discord, telegram, ntfy, smtp, gotify), HMAC-signed webhooks, auth brute-force detection |
| **Vault** | Fernet AES-128-CBC+HMAC-SHA256 encryption, OS keyring master key, active OAuth token revocation, Gibson panic destruction |
| **Analysis** | Local LLM reasoning + confidence scoring + chain safety rails |
| **Monitoring** | Event Ledger + Policy Events + Alert History — 3 independent audit trails |

## 🛡️ OWASP Agentic Security Initiative (ASI) Mapping

ButterClaw provides native mitigation for all 10 primary threats in the OWASP Agentic Security Initiative checklist:

| ASI Threat | ButterClaw Mitigation |
|---|---|
| **ASI-01: Excessive Agency** | Brain confidence gating + `ChainExecutor` `MAX_STEPS=10` / `TIMEOUT=60s` + Policy Engine `pre_tool` scope gating. No tool executes without policy clearance. |
| **ASI-02: Insufficient Access Control** | 4-tier RBAC (infrastructure / admin / operator / viewer) + per-role rate limiting + HMAC-SHA256 auth gateway on all non-public routes. The `infrastructure` role is machine-only at privilege level -1 and cannot be created via the API. |
| **ASI-03: Knowledge Poisoning** | Local-first LLM — no external training data ingestion. Watcher monitors OS telemetry, not user content. Zero-Day Arsenal signatures are static JSON compiled at startup, not fetched at runtime. |
| **ASI-04: Identity & Credential Abuse** | ButterVault (Fernet + OS keyring, master key never on disk) + OAuth lifecycle management + active token revocation + Gibson panic destruction overwrites all credentials atomically. |
| **ASI-05: Cascading Failures** | `ChainExecutor` hard limits: `MAX_STEPS=10`, `TIMEOUT=60s`. Steps fail independently — a crashed MCP tool aborts the chain with partial results logged, not a system crash. Retry queue (`maxlen=100`) prevents watcher memory exhaustion. |
| **ASI-06: Indirect Prompt Injection** | Policy Engine deterministic pattern matching on all inbound payloads (`pre_brain` scope) before the LLM is called. Watcher sanitizer strips shell-dangerous characters (`` [$`{}<>|;!] ``). Truncation limit 4096 chars covers full-length injections. |
| **ASI-07: Insufficient Monitoring** | Event Ledger (`mcp_events` SQLite) + Policy Events (`policy_events` SQLite) + Alert History — 3 independent, queryable audit trails. Auditor fires a second LLM pass 30 seconds after every CRITICAL verdict for false-positive detection. |
| **ASI-08: Insecure Output Handling** | Brain output (LLM response) is treated as untrusted data. The `post_brain` policy scope evaluates verdict/confidence/reasoning before any action is taken — LLM output cannot directly trigger kinetic actions without passing a deterministic policy gate. `DRY_RUN=true` hard-blocks all destructive output handling at the code level. |
| **ASI-09: Inadequate Logging** | 3 audit trails + external notification routing via Alert Dispatcher across 6 channels. All MCP tool calls logged to `mcp_events` with status, result, `elapsed_ms`, `chain_id`, and `chain_step`. Policy evaluations logged to `policy_events` with rule match and action taken. |
| **ASI-10: Uncontrolled Escalation** | Gibson panic destroys all credentials atomically (vault overwrite + API key delete + session cache invalidation) + Alert Dispatcher fires before destruction begins. Paranoia Level 3 is the only escalation path to Gibson; Levels 1 and 2 are non-destructive. `DRY_RUN=true` hard-blocks Level 3 regardless of verdict. |

## Security Headers (nginx)

The following HTTP security headers are set by `nginx/butterclaw.conf` on all responses:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

> **Note:** A `Content-Security-Policy` header is planned but not yet present in `nginx/butterclaw.conf` as of v0.6.5. Tracked for a future release.

## Known Attack Surfaces

| Surface | Exposure | Mitigation |
|---|---|---|
| `/api/analyze` | Localhost only (`127.0.0.1:5000`) | Watcher is the only caller; unauthenticated by design on localhost (see D-03 in `ARCHITECTURE.md`) — must not be exposed externally |
| LLM output | Untrusted — treated as adversarial data | `post_brain` policy gate before any verdict-driven action |
| MCP tool results | Untrusted — treated as adversarial data | `pre_tool` policy gate + `ChainExecutor` step/timeout limits |
| nginx (port 443) | Internet-facing | TLS 1.2/1.3, ECDHE ciphers, HSTS — only entry point to the stack |
| `butterclaw.db` | On-disk SQLite | All credentials are Fernet-encrypted; database without OS keyring entry is useless to an attacker |
| Gibson Kill Switch | Admin-role HTTP endpoint | Requires valid admin Bearer token; hard-blocked by `DRY_RUN=true` at code level |

## Responsible Disclosure

To report a security vulnerability, open a [GitHub Security Advisory](https://github.com/butterclaw-tech/butterclaw/security/advisories/new) or email the maintainers directly. Do not open a public issue for security reports.

## Related Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Trust boundaries, system invariants, design decisions
- [`API.md`](API.md) — Full endpoint reference, RBAC role table, rate limits
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — systemd hardening, nginx config, Docker security posture

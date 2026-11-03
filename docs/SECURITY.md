# 🔒 Security Architecture & ASI Coverage (v0.9.3)

ButterClaw was architected to protect autonomous AI agents from external exploitation, trojanized skill supply chains, multi-agent collusion, and internal hallucinations.

## Base Security Mechanisms

| Layer | Mechanism |
|---|---|
| **TLS** | nginx reverse proxy with TLSv1.2/1.3, ECDHE ciphers, HSTS |
| **Container** | Non-root `butterclaw` user, read-only skill mount (`./skills:/data/skills:ro`), `ProtectSystem=strict`, `NoNewPrivileges=true`, `ProtectHome=true`, `PrivateTmp=true` |
| **Supply-Chain (`SkillGuard`)** | Pre-flight YAML/markdown/Unicode steganography & Python AST static quarantine, SHA-256 Merkle-root SQLite attestation (`skill_attestations`), **Gate M5** runtime anti-TOCTOU verification, **Gate M10** canonical path containment (v0.9.3) |
| **Authentication** | HMAC-SHA256 API keys, HMAC-signed session tokens, `httpOnly` + `SameSite=Strict` cookies |
| **Authorization** | 4-tier RBAC (`infrastructure` / `admin` / `operator` / `viewer`) + Positive Security **Capability Matrix** (`capabilities.json`) mapping agent profiles to allowed MCP tool scopes (v0.7.0) |
| **Physical Transport** | Byte-bounded STDIO physical firewall (`mcp_stdio_transport.json`) enforcing `max_payload_bytes`, strict UTF-8 decoding, and oversized pipe draining (v0.7.0) |
| **Policy** | Deterministic `pre_brain` / `post_brain` / `pre_tool` guardrails via DRIFT engine (15 safe operators, zero `eval()`) + 7 sanitizer-aware Arsenal signatures |
| **Spatial & Fleet Defense** | Sub-millisecond GUI trajectory & Cold Memory attractor gate (`v0.8.0`) + isolated `fleet.db` trust graph, correlation/collusion engines, and 5th-hemisphere Fleet Sentinel (`v0.9.0`) |
| **Alerting** | 6 external channels (webhook, discord, telegram, ntfy, smtp, gotify), HMAC-signed webhooks, auth brute-force detection |
| **Vault** | Fernet AES-128-CBC+HMAC-SHA256 encryption, OS keyring master key, domain-gated remote LLM keys, active OAuth token revocation, Gibson panic destruction |
| **Analysis** | Five-hemisphere local LLM reasoning + confidence scoring + chain safety rails |
| **Monitoring** | Event Ledger + Policy Events + Alert History + Spatial Telemetry + Fleet Sentinel Log + SkillGuard Attestations — independent SQLite audit trails |

## 🛡️ OWASP Agentic Security Initiative (ASI) Mapping

ButterClaw provides native mitigation for all 10 primary threats in the OWASP Agentic Security Initiative checklist:

| ASI Threat | ButterClaw Mitigation |
|---|---|
| **ASI-01: Excessive Agency** | Brain confidence gating + `ChainExecutor` `MAX_STEPS=10` / `TIMEOUT=60s` + Policy Engine `pre_tool` scope gating + Positive Security Capability Matrix (`capabilities.json`) + SkillGuard `SKILL.md` frontmatter capability allowlists (`allowed_tools`, `allow_network`, `allow_env_access`). No tool executes without policy and capability clearance. |
| **ASI-02: Insufficient Access Control** | 4-tier RBAC (`infrastructure` / `admin` / `operator` / `viewer`) + per-role rate limiting + HMAC-SHA256 auth gateway on all non-public routes. The `infrastructure` role is machine-only at privilege level `4` (highest) and cannot be created or listed via the API. |
| **ASI-03: Knowledge Poisoning** | Local-first LLM — no external training data ingestion. Watcher monitors OS telemetry, not user content. Arsenal signatures are static JSON compiled at startup. **SkillGuard (v0.9.3)** blocks poisoned `SKILL.md` packages via pre-flight AST/steganography quarantine, `:ro` Docker mounts, and **Gate M5** runtime SHA-256 Merkle-root re-verification, while cross-fleet semantic memory promotion requires an explicit human admin gate (`I-03-fleet`). |
| **ASI-04: Identity & Credential Abuse** | ButterVault (Fernet + OS keyring, master key never on disk) + OAuth lifecycle management + domain-gated `GOOGLE_API_KEY` headers + SkillGuard AST blocking of `os.environ` harvesting in skill scripts + active token revocation + Gibson panic destruction overwrites all credentials atomically. |
| **ASI-05: Cascading Failures** | `ChainExecutor` hard limits: `MAX_STEPS=10`, `TIMEOUT=60s`. Steps fail independently — a crashed MCP tool aborts the chain with partial results logged, not a system crash. Retry queue (`maxlen=100`) prevents watcher memory exhaustion, and `HemisphereScheduler` circuit-breaks failing background LLM calls while exempting the Guardian Brain. |
| **ASI-06: Indirect Prompt Injection** | Policy Engine deterministic pattern matching on all inbound payloads (`pre_brain` scope) before the LLM is called. Watcher sanitizer strips shell-dangerous characters (`` [$`{}<>|;!] ``) with a 4096-char window. **SkillGuard** scans `SKILL.md` and `references/` for zero-width/tag-block Unicode smuggling, hidden HTML comments, and stealth policy-override directives before Stage 2/3 disclosure. |
| **ASI-07: Insufficient Monitoring** | Event Ledger (`mcp_events`), Policy Events (`policy_events`), Alert History (`alert_history`), Spatial Telemetry (`telemetry_events`), Fleet Sentinel Log (`fleet_sentinel_log`), and SkillGuard Registry (`skill_attestations` with live `GET /api/skills` TOCTOU checks). Auditor fires a second LLM pass 30 seconds after every CRITICAL verdict for false-positive detection. |
| **ASI-08: Insecure Output Handling** | Brain output (LLM response) is treated as untrusted data. The `post_brain` policy scope evaluates verdict/confidence/reasoning before any action is taken — LLM output cannot directly trigger kinetic actions without passing a deterministic policy gate. `DRY_RUN=true` hard-blocks all destructive output handling at the code level. |
| **ASI-09: Inadequate Logging** | Multi-table SQLite audit trails + external notification routing via Alert Dispatcher across 6 channels. All MCP tool calls logged to `mcp_events` with status, result, `elapsed_ms`, `chain_id`, and `chain_step`. Policy evaluations logged to `policy_events`; SkillGuard verdicts and Merkle roots persisted in `skill_attestations`. |
| **ASI-10: Uncontrolled Escalation** | Gibson panic destroys all credentials atomically (vault overwrite + API key delete + session cache invalidation) + Alert Dispatcher fires before destruction begins. Paranoia Level 3 is the only escalation path to Gibson; Levels 1 and 2 are non-destructive, and fleet quarantine uses a 60-second two-step human confirmation token (`R-06`). `DRY_RUN=true` hard-blocks Level 3 regardless of verdict. |

## Security Headers (nginx & Web UI)

The following HTTP security headers are set by `nginx/butterclaw.conf` on all responses:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

> **Note:** Both `index.html` and `routing.html` enforce a document-level `<meta http-equiv="Content-Security-Policy">` (`default-src 'self'`, `connect-src 'self'`, `img-src 'self' data:`) and render dynamic telemetry strictly via DOM `.textContent` (zero untrusted `innerHTML`). Moving `Content-Security-Policy` into `nginx/butterclaw.conf` as an HTTP response header remains tracked for a future release.

## Known Attack Surfaces

| Surface | Exposure | Mitigation |
|---|---|---|
| `/api/analyze` | Internal container network (`port 5000` unexposed to host) | Protected by `@require_auth(min_role="operator")` + per-key rate limiting; Watcher authenticates via `BUTTERCLAW_API_KEY` (`infrastructure` role) |
| `SKILL.md` Packages (`/data/skills:ro`) | Host bind-mount (`./skills`) | Mounted read-only (`:ro`, kernel `Errno 30` on container writes); **Gate M10** canonical path containment rejects symlinks/`..`; pre-flight AST/stego scan quarantines risky skills (`>= 25%`); **Gate M5** recomputes SHA-256 Merkle root at runtime to block post-audit TOCTOU tampering |
| LLM output | Untrusted — treated as adversarial data | `post_brain` policy gate + confidence floor before any verdict-driven action |
| MCP tool calls & pipes | Untrusted — treated as adversarial data | Capability Matrix + `pre_tool` policy gate + `StdioTransport` byte-limit firewall + `ChainExecutor` step/timeout limits |
| Spatial GUI telemetry | Operator-authenticated HTTP (`POST /api/spatial/telemetry`) | O(1) Cold Memory signature gate + velocity/jitter/entropy heuristics; `BLOCK` suspends and terminates the recursive PID tree via `psutil` |
| `fleet.db` | On-disk SQLite (`/data/fleet.db`) | Separate file/inode never co-transacted with `butterclaw.db` (`I-07-fleet`); two-step HMAC quarantine (`R-06`); human-gated fleet entity promotion (`I-03-fleet`) |
| nginx (port 443) | Internet-facing | TLS 1.2/1.3, ECDHE ciphers, HSTS — only entry point to the stack |
| `butterclaw.db` | On-disk SQLite (`/data/butterclaw.db`) | All credentials are Fernet-encrypted; database without OS keyring entry is useless to an attacker |
| Gibson Kill Switch | Admin-role HTTP endpoint (`POST /api/rotate-keys`) | Requires valid admin Bearer token; hard-blocked by `DRY_RUN=true` at code level |

## Responsible Disclosure

To report a security vulnerability, open a [GitHub Security Advisory](https://github.com/butterclaw-tech/butterclaw/security/advisories/new) or email the maintainers directly. Do not open a public issue for security reports.

---

## Related Documentation

* [`API.md`](API.md) — Full endpoint reference (80 routes, 4-tier RBAC)
* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, Gate M5/M10 invariants, design decisions
* [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker (`:ro` mounts), systemd, nginx, backup configuration
* [`RUNBOOK.md`](RUNBOOK.md) — Fleet quarantine vs. block flowchart, dry-run rollout, alert procedures (v0.9.0)
* [`THREAT_MODEL.md`](THREAT_MODEL.md) — Updated threat model

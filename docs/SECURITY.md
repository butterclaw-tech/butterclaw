# 🔒 Security Architecture & ASI Coverage

ButterClaw was architected to protect autonomous AI agents from both external exploitation and internal hallucinations. 

## Base Security Mechanisms

| Layer | Mechanism |
| --- | --- |
| **TLS** | nginx reverse proxy with TLSv1.2/1.3, ECDHE ciphers, HSTS |
| **Container** | Non-root user, read-only filesystem, ProtectSystem=strict |
| **Authentication** | HMAC-SHA256 API keys, session tokens, httpOnly cookies |
| **Authorization** | 3-tier RBAC (admin/operator/viewer) |
| **Policy** | Deterministic pre-brain/post-brain/pre-tool guardrails |
| **Alerting** | 5 external channels, HMAC-signed webhooks, auth brute-force detection |
| **Vault** | Fernet encryption, OS keyring, active network token revocation, Gibson |
| **Analysis** | Local LLM reasoning + confidence scoring + chain safety rails |
| **Monitoring** | Event Ledger + Policy Events + Alert History — 3 audit trails |

## 🛡️ OWASP Agentic Security Initiative (ASI) Mapping

ButterClaw provides native mitigation for 9 of the primary threats outlined in the OWASP Agentic Security Initiative checklist:

| ASI Threat | ButterClaw Mitigation |
| --- | --- |
| **ASI-01: Excessive Agency** | Brain confidence gating + ChainExecutor `MAX_STEPS=10` + Policy Engine pre-tool scope gating. |
| **ASI-02: Insufficient Access Control** | 3-tier RBAC + per-key rate limiting + HMAC-SHA256 auth gateway. |
| **ASI-03: Knowledge Poisoning** | Local-first LLM — no external training data ingestion. Watcher monitors OS telemetry, not user content. |
| **ASI-04: Identity & Credential Abuse** | ButterVault + OAuth lifecycle + active token revocation + Gibson panic destruction. |
| **ASI-05: Cascading Failures** | ChainExecutor safety rails: `MAX_STEPS=10`, `TIMEOUT=60s`. |
| **ASI-06: Indirect Prompt Injection** | Policy Engine deterministic pattern matching on inbound payloads. |
| **ASI-07: Insufficient Monitoring** | Event Ledger + Policy Events + Alert History (3 immutable audit trails). |
| **ASI-09: Inadequate Logging** | 3 audit trails + external notification routing via Alert Dispatcher. |
| **ASI-10: Uncontrolled Escalation** | Gibson panic destroys all credentials atomically + Alert Dispatcher fires before destruction. |
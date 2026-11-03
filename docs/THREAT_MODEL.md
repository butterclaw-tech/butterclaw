# 🎯 ButterClaw Threat Model (v0.9.3)

This document defines the security boundaries of ButterClaw. It outlines what threats the Exoskeleton is designed to intercept, what scenarios are explicitly out of scope, and what baseline assumptions are made about the deployment environment.

## 1. Environment Assumptions

ButterClaw provides a defense-in-depth layer for autonomous agents, but it cannot protect a host that is already fundamentally compromised. We assume the following baseline invariants:

* **Host Integrity:** The underlying host operating system (Linux/Windows) is not root-compromised.
* **Container Isolation:** The Docker daemon is secure, container escape vulnerabilities are patched, and bind-mounted skill packages (`./skills:/data/skills:ro`) enforce Linux VFS read-only flags inside the container.
* **Administrator Trust:** Human operators with SSH access to the host, or physical access to the machine, are trusted. ButterClaw does not protect against rogue system administrators with root access to both the SQLite volume (`butterclaw.db` / `fleet.db`) and the OS keyring.
* **Network Perimeter:** Inbound traffic to the host is blocked by a firewall, with only Nginx (port 443) exposed. Port 5000 is isolated inside the Docker bridge network, and `/api/analyze` requires authenticated `operator`+ credentials.

## 2. In-Scope Threats (What We Defend Against)

ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC) paired with deterministic supply-chain and runtime gates. It is specifically engineered to mitigate the following:

* **Indirect Prompt Injection:** Malicious instructions hidden in web pages, PDFs, or API responses that an authorized agent ingests, instructing the agent to exfiltrate data or perform destructive actions.
* **Trojanized `SKILL.md` Packages & Supply-Chain TOCTOU (`v0.9.3`):** Malicious or compromised agent skills containing zero-width/tag-block Unicode steganography, hidden HTML comment prompt injections, undeclared outbound URLs, covert Python `scripts/*.py` beacons (`socket`, `urllib.request`, `subprocess`, `os.environ`, `eval()`/`exec()`), symlink/`..` path traversal escapes (**Gate M10**), or post-audit file modifications on disk (**Gate M5** SHA-256 Merkle-root mismatch).
* **Cross-Site WebSocket Hijacking (CSWH):** Attackers hijacking the agent's active WebSocket or MCP transport layer to force execution of arbitrary tool calls.
* **Authorized Agent Compromise & Behavioral Drift:** An AI agent that has valid, legitimate API keys but begins acting outside of its designated parameters or capability scope.
* **Malicious Computer-Use / Spatial Trajectories (`v0.8.0`):** Compromised GUI/desktop agents executing anomalous high-velocity pointer sweeps, high-entropy keystroke payloads, or repeating known-bad Cold Memory action sequences.
* **Multi-Agent Collusion & Divided-Labor Kill Chains (`v0.9.0`):** Coordinated swarms splitting reconnaissance (`scout`), encoding (`encoder`), persistence (`persister`), and exfiltration (`exfiltrator`) across N≥3 distinct agents so no individual agent triggers a single-session threshold.
* **Data Exfiltration:** Attempts by a compromised agent to use generic tools (e.g., `curl`, `wget`, Python HTTP clients) to send local environment variables or Vault credentials to external untrusted domains.
* **SSRF (Server-Side Request Forgery):** Attempts by the LLM or tool layer to scrape internal cloud metadata endpoints (e.g., AWS/Azure/GCP IMDS at `169.254.169.254`, `fd00:ec2::254`, or `metadata.google.internal`).

## 3. Out-of-Scope Threats (What We Do Not Cover)

* **Pre-Execution Model Poisoning:** ButterClaw monitors runtime telemetry and `SKILL.md` packages. It does not scan base LLM weights (`.gguf` / safetensors) for backdoors or training data poisoning.
* **Pure Natural-Language Skill Goal Drift (Zero Static Indicators):** While `SkillGuard` (`v0.9.3`) deterministically catches steganography, HTML comments, undeclared URLs, capability mismatches, and dangerous Python AST constructs, a pure-prose `SKILL.md` containing zero technical indicators that subtly nudges business logic via plain English requires semantic LLM review (slated as an optional local-Ollama audit pass in `v0.9.4`).
* **Network-Level DDoS:** ButterClaw is an application-layer defense. It relies on upstream infrastructure (e.g., Cloudflare, Nginx rate limits) to absorb volumetric network attacks.
* **Zero-Day Container Escapes:** If an attacker exploits a zero-day in `runc` or the Linux kernel to break out of the container and read host memory directly, ButterClaw cannot intervene.
* **Post-Hoc Compliance Auditing:** While `SkillGuard` uses cryptographic SHA-256 Merkle roots to attest `SKILL.md` packages on disk, the general `mcp_events` execution ledger is an operational SQLite log rather than an immutable, externally anchored compliance ledger. (For verifiable, hash-chained external audit trails, pair ButterClaw with an evidence layer).

## 4. Addressing "Who Watches the Watchman?"

A common critique of LLM-based security tooling is that the evaluating LLM itself can be manipulated by a clever prompt injection.

ButterClaw mitigates this through **Deterministic Pre/Post Gates** and **Five-Hemisphere Separation** that isolate probabilistic reasoning from execution authority:

1. **Deterministic Override (The Arsenal):** Before the Brain ever sees a payload, the `pre_brain` Policy Engine scans it using the Threat Signature Arsenal. If a known CSWH, reverse-shell, metadata-probe, or injection pattern is detected, the request is blocked instantly. *This operates independently of the LLM layer, ensuring known-signature threats are blocked even if LLM evaluation is bypassed.*
2. **Untrusted LLM Output:** Brain output is treated as adversarial data. The `post_brain` policy scope evaluates the verdict, confidence, and reasoning *before* any kinetic action is taken. The LLM cannot directly trigger the Gibson; it can only request it, subject to deterministic policy clearance and Paranoia Dial state.
3. **Cryptographic Supply-Chain & Capability Gating (Non-LLM, `v0.7.0`–`v0.9.3`):** `SkillGuard` (**Gate M5** SHA-256 Merkle verification + **Gate M10** path containment), the Positive Security Capability Matrix (`capabilities.json`), and the byte-level STDIO firewall (`mcp_transport.py`) execute deterministically in pure Python stdlib. An adversarial prompt cannot persuade `butterclaw_mcp.py` to load a `QUARANTINED` or Merkle-drifted skill or invoke a tool outside its RBAC capability scope.
4. **Read-Only Memory & Code-Immutable Autoresearch (`v0.8.0`–`v0.9.0`):** Recalled Deep Memory is injected strictly as read-only prompt context (`I-12-mem`), Dream Weaver is hardcoded to `DREAM_DRY_RUN=True` (`I-13-mem`), and Loop Proposer is structurally and runtime-barred (`_reject_python_targets`, `I-15-mem`) from modifying `.py` code.

## 5. Failure Modes & Degradation

| Scenario | System Behavior |
| --- | --- |
| **Ollama / Inference Engine Offline** | System fails secure. `server.py` cannot resolve LLM verdicts (unless remote fallback is configured); requests sit in the Watcher's bounded retry queue (persisted to disk on `SIGTERM`) while deterministic `pre_brain` Arsenal rules, Spatial Cold Memory, and SkillGuard Gate M5/M10 continue enforcing normally. |
| **Post-Audit `SKILL.md` Tampering (TOCTOU)** | Fails closed (**Gate M5**). Live SHA-256 Merkle root recomputation detects the byte mismatch against `butterclaw.db`, flips `/api/skills` status to `TAMPERED`, blocks Stage 2/3 disclosure and MCP tool calls, taints the active session, and triggers kinetic fallback. |
| **`fleet.db` Unavailable at Startup** | Fails closed (`I-01-fleet`). Server halts startup rather than running silently with multi-agent collusion and trust-graph tracking disabled. |
| **Dream Engine Stalled / Starved** | Graceful fallback (`v0.9.2` R3). The `_maturation_fallback_loop` watchdog fires batched SQLite maturation ticks independently after 6 hours while `_maturation_tick_lock` prevents double-decay races. |
| **Network Loss During Gibson** | Graceful degradation. External OAuth revocation (HTTP DELETE/POSTs) will fail, but local ButterVault SQLite rows are still mathematically overwritten with random poison-key ciphertext and all session/API key hashes are wiped. |
| **Alert Delivery Failure** | Channel independence. If a Discord webhook is down, SMTP, Telegram, and local ntfy alerts still fire. Failed deliveries are logged to `alert_history` and retried with exponential backoff. |

---

## Related Documentation

* [`API.md`](API.md) — Full endpoint reference (80 routes, 4-tier RBAC)
* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, Gate M5/M10 invariants, design decisions
* [`SECURITY.md`](SECURITY.md) — OWASP ASI coverage, security headers, responsible disclosure
* [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker (`:ro` mounts), systemd, nginx, backup configuration
* [`RUNBOOK.md`](RUNBOOK.md) — Fleet quarantine vs. block flowchart, dry-run rollout, alert procedures (v0.9.0)

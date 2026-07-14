# 🎯 ButterClaw Threat Model

This document defines the security boundaries of ButterClaw. It outlines what threats the Exoskeleton is designed to intercept, what scenarios are explicitly out of scope, and what baseline assumptions are made about the deployment environment.

## 1. Environment Assumptions

ButterClaw provides a defense-in-depth layer for autonomous agents, but it cannot protect a host that is already fundamentally compromised. We assume the following baseline invariants:

* **Host Integrity:** The underlying host operating system (Linux/Windows) is not root-compromised.
* **Container Isolation:** The Docker daemon is secure, and container escape vulnerabilities are patched.
* **Administrator Trust:** Human operators with SSH access to the host, or physical access to the machine, are trusted. ButterClaw does not protect against rogue system administrators with root access to the SQLite database and OS keyring.
* **Network Perimeter:** Inbound traffic to the host is blocked by a firewall, with only Nginx (port 443) exposed. `/api/analyze` is strictly firewalled to localhost.

## 2. In-Scope Threats (What We Defend Against)

ButterClaw acts as an "LLM-in-the-middle" Security Operations Center (SOC). It is specifically engineered to mitigate the following:

* **Indirect Prompt Injection:** Malicious instructions hidden in web pages, PDFs, or API responses that an authorized agent ingests, instructing the agent to exfiltrate data or perform destructive actions.
* **Cross-Site WebSocket Hijacking (CSWH):** Attackers hijacking the agent's active WebSocket or MCP transport layer to force execution of arbitrary tool calls.
* **Authorized Agent Compromise:** An AI agent that has valid, legitimate API keys but begins acting outside of its designated parameters (Behavioral Drift).
* **Data Exfiltration:** Attempts by a compromised agent to use generic tools (e.g., `curl`, `wget`) to send local environment variables or Vault credentials to external untrusted domains.
* **SSRF (Server-Side Request Forgery):** Attempts by the LLM to scrape internal cloud metadata endpoints (e.g., AWS IMDS at `169.254.169.254`). 

## 3. Out-of-Scope Threats (What We Do Not Cover)

* **Pre-Execution Model Poisoning:** ButterClaw monitors runtime telemetry. It does not scan base LLM weights for backdoors or training data poisoning.
* **Network-Level DDoS:** ButterClaw is an application-layer defense. It relies on upstream infrastructure (e.g., Cloudflare, Nginx rate limits) to absorb volumetric network attacks.
* **Zero-Day Container Escapes:** If an attacker exploits a zero-day in `runc` or Docker to break out of the agent's container and read host memory, ButterClaw cannot intervene.
* **Post-Hoc Compliance Auditing:** The ButterClaw event ledger is an operational log, not a cryptographically tamper-evident compliance artifact. (For verifiable, hash-chained audit trails, we recommend pairing ButterClaw with an evidence layer like Halo).

## 4. Addressing "Who Watches the Watchman?"

A common critique of LLM-based security tooling is that the evaluating LLM itself can be manipulated by a clever prompt injection. 

ButterClaw mitigates this through a **Dual-Pass Reasoning** architecture that isolates the reasoning layer from the agent's execution context:

1. **Deterministic Override (The Arsenal):** Before the Brain ever sees a payload, the `pre_brain` Policy Engine scans it using the Threat Signature Arsenal. If a known CSWH or injection pattern is detected, the request is blocked instantly. *This operates independently of the LLM layer, ensuring known-signature threats are blocked even if LLM evaluation is bypassed.*
2. **Untrusted LLM Output:** Brain output is treated as adversarial data. The `post_brain` policy scope evaluates the verdict, confidence, and reasoning *before* any kinetic action is taken. The LLM cannot directly trigger the Gibson; it can only request it, subject to deterministic policy clearance.

## 5. Failure Modes & Degradation

| Scenario | System Behavior |
| --- | --- |
| **Ollama / Inference Engine Offline** | System fails secure. `server.py` cannot resolve verdicts. Requests sit in the Watcher's retry queue (persisted to disk) until inference is restored. |
| **Network Loss During Gibson** | Graceful degradation. External OAuth revocation (HTTP DELETEs) will fail, but the local ButterVault SQLite rows will still be mathematically shredded with random CSPRNG bytes. |
| **Alert Delivery Failure** | Channel independence. If the Discord webhook is down, SMTP and ntfy alerts will still fire. Failed deliveries are logged to `alert_history` and retried with exponential backoff. |
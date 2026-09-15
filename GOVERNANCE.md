# ButterClaw Governance

## Overview

ButterClaw is an open-source security harness for agentic AI. As a project applying for AAIF Growth Stage membership, our governance is designed to be lightweight, transparent, and focused on rapid iteration while maintaining security integrity.

---

## The Maintainer Role

Currently, ButterClaw is led by its founder (Lead Maintainer). The Lead Maintainer is responsible for:

- Strategic direction and project roadmap
- Final approval on all Pull Requests
- Management of the project's security policy (see [SECURITY.md](docs/SECURITY.md))
- Architectural decision-making — significant design changes are documented as GitHub Issues before implementation, so decisions are traceable and reviewable by the community

---

## Decision Making

We operate on a **Lazy Consensus** model:

1. Major changes (new Exoskeleton layers, breaking API changes, new RBAC roles, transport backends) are proposed via GitHub Issues or Discussions with a description of the behavioral gap being addressed.
2. If no substantive objections are raised within **72 hours**, the proposal is considered accepted.
3. Security-sensitive changes (changes to `auth.py`, `buttervault.py`, `policy_engine.py`, or the Gibson sequence) require explicit Lead Maintainer approval regardless of consensus — they bypass the 72-hour window.

---

## Becoming a Maintainer

We welcome contributors to grow into maintainer roles. Contributors who consistently deliver high-quality code, documentation, or security research over a **3-month period** can be nominated for Maintainer status by the Lead Maintainer.

We are **actively seeking co-maintainers** in the following areas:

| Area | Scope |
|---|---|
| **MCP Transport** | v0.7 stdio transport layer, new transport backends |
| **Security Research** | OWASP ASI coverage, threat model expansion, audit coordination |
| **Documentation** | Cross-doc accuracy, contributor onboarding, API reference |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide.

---

## Security Disclosure

Security vulnerabilities must be reported privately. Do not open public issues for security reports.

Use GitHub's **Private Vulnerability Reporting** feature (Security tab → "Report a vulnerability") or contact the Lead Maintainer directly.

Full threat model, known attack surfaces, and OWASP ASI coverage: [SECURITY.md](docs/SECURITY.md).

---

## Alignment

ButterClaw is applying for **AAIF Growth Stage** membership. We align with the Agentic AI Foundation mission to create secure, interoperable, and transparent agentic infrastructure.

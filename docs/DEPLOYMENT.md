# 🚀 ButterClaw Deployment Guide (v0.9.3)

This guide covers Docker (recommended), systemd (bare-metal), and the shared steps
that apply to both: LLM setup, SkillGuard package management, backup, and configuration.

---

## Prerequisites

- Docker + Docker Compose v2 (Docker deployment)
- Python 3.11+ (bare-metal deployment or host setup wizard)
- [Ollama](https://ollama.com) installed and running *(optional if using a domain-gated remote LLM API)*
- A valid SSL certificate in `./nginx/certs/` (self-signed is fine for local use)

---

## 1. LLM Setup — Ollama Model

ButterClaw uses a tuned profile of `gemma4:e4b` optimised for security log analysis.
Two steps are required — first pull the base model from the Ollama registry, then build
the ButterClaw-optimised variant from `Modelfile.example`:

```bash
# Step 1 — pull the base model from the Ollama registry
ollama pull gemma4:e4b

# Step 2 — build the ButterClaw-optimised variant
# Applies: 16k context window, temperature 0.3, top_p 0.9
ollama create butterclaw-optimized -f Modelfile.example
```

**Modelfile.example parameters:**

| Parameter | Value | Purpose |
|---|---|---|
| `FROM` | `gemma4:e4b` | Base model |
| `num_ctx` | `16384` | 16k context window — handles large 4096-char sanitised log payloads |
| `temperature` | `0.3` | Low variance — prioritises precision over creativity for threat classification |
| `top_p` | `0.9` | Nucleus sampling ceiling |

> The model name configured in `.env` (`BUTTERCLAW_MODEL`, default `butterclaw-optimized:latest`)
> must match the name given to `ollama create`. If you use a different model tag, update
> `BUTTERCLAW_MODEL` in `.env` (or switch at runtime on `https://localhost/routing.html`).

---

## 2. Docker Deployment (Recommended)

### Stack Overview

The `docker-compose.yml` defines three services connected over the internal `butterclaw-net` bridge:

| Container Name | Service | Port | Notes |
|---|---|---|---|
| `butterclaw-server` | `butterclaw` — Flask API, Guardian Brain, Five Hemispheres + Watcher (`supervisord`) | Internal `5000` only | Non-root `butterclaw` user; runs `butterclaw.server` + `butterclaw.watcher` |
| *(auto-named)* | `nginx` — TLS termination and reverse proxy | `443` (HTTPS), `80` → redirect | Sole external network entry point |
| `butterclaw-ntfy` | `ntfy` — bundled air-gapped push notification server | `2586` | Self-hosted push alert backend |

**Volumes & Bind Mounts:**
- `butterclaw-data:/data` — persistent volume storing `butterclaw.db`, `fleet.db` (separate inode per `I-07-fleet`), `/data/evidence_locker`, and the container keyring (`XDG_DATA_HOME=/data`)
- `./skills:/data/skills:ro` — **read-only** mount for `SKILL.md` packages inspected by **SkillGuard** (`Gate M5` / `Gate M10`; enforces kernel `Errno 30` against in-container tampering)
- `./openclaw_gateway.log:/app/openclaw_gateway.log` — host-to-container log bridge monitored by the Watcher daemon
- `./index.html`, `./routing.html`, `./favicon.png:ro` — Web UI assets mounted for zero-rebuild frontend updates
- `./nginx:/etc/nginx/conf.d:ro` and `./nginx/certs:/etc/nginx/certs:ro` — read-only Nginx vhost configs and TLS certificates

> **Note:** Inside the Docker container, `supervisord` launches **both** `python -m butterclaw.server`
> and `python -m butterclaw.watcher` automatically. You only need to launch `watcher` manually
> on bare-metal / `systemd` deployments (see Section 4).

### Configure & Start the Stack

```bash
# 1. Install package metadata locally (enables the interactive wizard)
pip install -e .

# 2. Run the 10-section interactive wizard (generates .env + bc_ infrastructure key)
#    (Alternatively: cp .env.example .env and edit values manually)
python -m butterclaw.setup_wizard

# 3. Build and start all services
docker compose up -d --build

# 4. Verify container health (allow up to 60s start_period on cold boot)
docker compose ps
curl -sk https://localhost/api/health | python3 -m json.tool
```

To retrieve your first-run **Admin API Key** for Web UI login (`https://localhost`):

```bash
docker compose logs butterclaw | grep -A 3 "\[AUTH\]"
```

### SkillGuard Package Auditing in Docker (v0.9.3)

Place modular agent skill directories (`SKILL.md`, `references/`, `scripts/`) into `./skills/` on the host, then audit and attest them inside the container via `dash.sh` (Linux/macOS), `dash.bat` (Windows), or the **Scan Skills Dir** button on `https://localhost`:

```bash
# Seed synthetic benign + Trojan test skills (optional verification)
python scripts/seed_test_skills.py

# Pre-flight static + AST + steganographic audit inside the container
./dash.sh audit /data/skills/log-summarizer        # Windows: .\dash.bat audit /data/skills/log-summarizer

# Inspect the SQLite SHA-256 Merkle attestation registry
./dash.sh skills                                   # Windows: .\dash.bat skills

# Run the 7-test SkillGuard Gate M5/M10 unit suite
./dash.sh test                                     # Windows: .\dash.bat test
```

### nginx Configuration Files

The nginx service mounts `./nginx:/etc/nginx/conf.d:ro`. The active files in `nginx/` include:

- **`nginx/butterclaw.conf`** — primary vhost: TLS 1.2/1.3 termination, HSTS & security headers, API proxy rules (`300s` read timeout), unbuffered `/api/stream` SSE location block (`24h` timeout)
- **`nginx/default.conf`** — fallback: catches unmatched hostnames / HTTP redirects

To update nginx config, edit `nginx/butterclaw.conf` and reload without downtime:

```bash
docker compose exec nginx nginx -s reload
```

> **Note:** `nginx/nginx.conf` is not overridden directly. The `conf.d` mount pattern means all
> `.conf` files in `nginx/` are included automatically by the nginx container.

### Stopping and Updating

```bash
docker compose down
git pull
docker compose up -d --build
```

---

## 3. Configuration Reference

Configuration is loaded by `src/butterclaw/config.py` using strict 12-Factor priority:
**OS Environment Variables** (highest) → **`.env` file** → **Hardcoded Defaults** (lowest).
All 36 exported fields across 11 categories are documented in [`.env.example`](../.env.example). Key variables:

| Environment Variable | Category | Description |
|---|---|---|
| `BUTTERCLAW_INSTANCE_ID` | Identity | Unique identifier for this deployment — appears in `/api/health` and alert payloads |
| `BUTTERCLAW_DB_PATH` | Database | Core SQLite path (`/data/butterclaw.db` in Docker, `./butterclaw.db` locally) |
| `BUTTERCLAW_FLEET_DB_PATH` | Database | Fleet SQLite path (`/data/fleet.db` in Docker; must differ from `BUTTERCLAW_DB_PATH` per `I-07-fleet`) |
| `BUTTERCLAW_SKILL_ROOT` | SkillGuard | Canonical `SKILL.md` root directory (`/data/skills` in Docker; `Gate M10` boundary, v0.9.3) |
| `BUTTERCLAW_SKILL_RISK_THRESHOLD` | SkillGuard | Risk score ceiling (`1–100`, default `25`) at or above which skills are `QUARANTINED` (v0.9.3) |
| `BUTTERCLAW_SKILL_STRICT_TOCTOU` | SkillGuard | Re-verify live SHA-256 Merkle root on Stage 2/3 loads and MCP tool calls (`true` default, v0.9.3) |
| `BUTTERCLAW_OLLAMA_URL` | Brain | Ollama API base URL (`http://host.docker.internal:11434` for Docker, `http://localhost:11434` bare-metal) |
| `BUTTERCLAW_MODEL` | Brain | Active reasoning model tag (default `butterclaw-optimized:latest`) |
| `BUTTERCLAW_GOOGLE_API_KEY` | Brain | Optional remote fallback key (strictly domain-gated to `generativelanguage.googleapis.com`) |
| `BUTTERCLAW_PARANOIA` | Response | `1` = Observe, `2` = Active Defense (SIGKILL), `3` = Air-Gapped Lockdown (SIGKILL + Gibson) |
| `BUTTERCLAW_DRY_RUN` | Safety | `true` hard-blocks Gibson vault destruction at the code level |
| `BUTTERCLAW_MCP_DRY_RUN` | Safety | `true` simulates OS `pkill` and remote token rotation inside MCP tools |
| `BUTTERCLAW_LOOP_DRY_RUN` | Safety | `true` records Loop Proposer experiments without mutating live rules (v0.8.0) |
| `BUTTERCLAW_FLEET_SENTINEL_DRY_RUN` | Fleet | `true` logs Fleet Sentinel verdicts without escalating to Guardian Brain (v0.9.0; see `RUNBOOK.md`) |
| `BUTTERCLAW_MEMORY_WATCHDOG_ENABLED` | Memory | `true` arms the R3 6-hour fallback maturation ticker daemon (v0.9.2) |
| `BUTTERCLAW_API_KEY` | Auth | `bc_`-prefixed seed for `infrastructure` role auto-heal bootstrap |
| `BUTTERCLAW_ALERT_NTFY_TOPIC` | Alerts | Auto-bootstraps the default `ntfy` channel and critical alert rules on startup |
| `BUTTERCLAW_RATE_ADMIN` | Auth | Rate limit (req/min) for `admin` role keys (default `30`) |
| `BUTTERCLAW_RATE_OPERATOR` | Auth | Rate limit (req/min) for `operator` role keys (default `15`) |
| `BUTTERCLAW_RATE_VIEWER` | Auth | Rate limit (req/min) for `viewer` role keys (default `5`) |
| `BUTTERCLAW_RATE_INFRASTRUCTURE` | Auth | Rate limit (req/min) for internal `infrastructure` keys (default `1000`) |

---

## 4. Watcher Daemon (Bare-Metal / Standalone)

The Watcher monitors `openclaw_gateway.log` for new lines, strips shell-dangerous metacharacters, and forwards payloads to `/api/analyze`. *(In Docker deployments, `supervisord` runs this daemon automatically inside `butterclaw-server`.)*

```bash
# Standard mode — tail from current EOF (uses .venv on bare-metal)
.venv/bin/python -m butterclaw.watcher

# Replay mode — read log from beginning (useful for testing)
.venv/bin/python -m butterclaw.watcher --replay
```

**Watcher runtime behaviour:**
- PID lock file (`watcher.pid`) prevents duplicate instances — a second invocation
  detects the live PID and exits
- Retry queue (`retry_queue.json`) persists up to 100 undelivered events to disk on
  `SIGTERM`/`SIGINT` and reloads them on next boot
- Log rotation is detected automatically (inode + size comparison)
- Reads `BUTTERCLAW_API_KEY` dynamically from the environment / `.env` and authenticates to
  `/api/analyze` using `Authorization: Bearer <BUTTERCLAW_API_KEY>` (`infrastructure` role)

> **Note:** `systemd/` currently ships `butterclaw.service` for the main server. On bare-metal
> deployments, run `python -m butterclaw.watcher` in an auxiliary `systemd` unit or a
> `tmux`/`screen` session alongside `butterclaw.service`.

---

## 5. systemd Deployment (Bare-Metal)

A hardened systemd unit file is provided at `systemd/butterclaw.service`.

```bash
# 1. Set up the virtual environment and install the package
cd /opt/butterclaw
python3 -m venv .venv
source .venv/bin/activate
pip install .

# 2. Generate your environment configuration and copy to /etc/butterclaw.env (or /opt/butterclaw/.env)
python -m butterclaw.setup_wizard

# 3. Install and start the service
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw
sudo systemctl status butterclaw
journalctl -u butterclaw -f
```

### systemd Security Hardening

| Directive | Value | Effect |
|---|---|---|
| `ProtectSystem` | `strict` | Mounts `/`, `/usr`, `/boot` as read-only |
| `NoNewPrivileges` | `true` | Prevents privilege escalation via `setuid`/`setgid` |
| `ProtectHome` | `true` | Makes `/home`, `/root`, `/run/user` invisible |
| `PrivateTmp` | `true` | Gives the process a private `/tmp` namespace |
| `CapabilityBoundingSet` | `CAP_KILL CAP_SYS_PTRACE` | Grants surgical kinetic authority (`SIGKILL`) without root capabilities |
| `ReadWritePaths` | `/opt/butterclaw /opt/butterclaw/butterclaw.db` | Restricts filesystem writes to the application data paths |

> **Bare-metal path note:** When running under `ProtectSystem=strict` with `v0.9.0+` Fleet Layer and
> Watcher enabled, ensure `ReadWritePaths` in your local `butterclaw.service` includes `fleet.db`,
> `retry_queue.json`, and `watcher.pid` (or place all mutable state inside `/opt/butterclaw/data` and
> whitelist that directory):
> `ReadWritePaths=/opt/butterclaw /opt/butterclaw/butterclaw.db /opt/butterclaw/fleet.db /opt/butterclaw/retry_queue.json /opt/butterclaw/watcher.pid`

---

## 6. Backup & Restore

```bash
# Run atomic backup manually
bash scripts/backup.sh

# Verify backup SQLite integrity & I-07-fleet inode isolation (v0.9.0+)
bash scripts/verify_backup.sh /data

# Interactive restore from timestamped archive in backups/
bash scripts/restore.sh

# Schedule via cron (daily at 03:00)
echo "0 3 * * * /opt/butterclaw/scripts/backup.sh" | crontab -

# Override database path if non-default
BUTTERCLAW_DB_PATH=/custom/path/butterclaw.db bash scripts/backup.sh
```

**What `backup.sh` / `/data` volume backups include:**

| Item | Backed Up | Notes |
|---|---|---|
| `butterclaw.db` | ✅ | `sqlite3 .backup` — atomic online snapshot (includes policies, memory tiers, and `skill_attestations`) |
| `fleet.db` | ✅ *(verify via `verify_backup.sh`)* | Must remain on a distinct file/inode from `butterclaw.db` (`I-07-fleet`; see `RUNBOOK.md`) |
| `.env` | ✅ | Plain file copy |
| `retry_queue.json` | ❌ | Ephemeral queue — acceptable to lose on restore |
| `default_signatures.json` / `capabilities.json` | ❌ | Tracked in git — restore from repo |
| `skills/` | ❌ | Host-mounted read-only packages; re-audit via `dash.sh audit` if skill files change |
| `nginx/` & `systemd/` | ❌ | Tracked in git — restore from repo |
| Vault master key (keyring) | ⚠️ Environment-dependent | **Bare-metal:** lives in host OS keyring (not backed up by `backup.sh`). **Docker:** `XDG_DATA_HOME=/data` stores `keyrings.alt` state inside the `butterclaw-data` volume. |

**Retention:** Last 7 archives in `backups/` are kept automatically; older backups are pruned.

> ⚠️ **Critical:** On bare-metal installs, the OS keyring entry holding the ButterVault master key is
> **not** included in `backup.sh` output (and in Docker, copying `.tar.gz` DB snapshots without the `/data`
> keyring directory has the same effect). If the master key is lost during a host migration, the encrypted
> credential rows in `butterclaw.db` are permanently unrecoverable. Always back up your keyring before migrating hosts.

---

## 7. Health Checks & Diagnostics

### API Health Endpoint

```bash
curl -sk https://localhost/api/health | python3 -m json.tool
```

Returns: `status`, `version` (`0.9.3`), `instance_id`, `uptime_seconds`, `config_source`, and per-component status (`auth`, `policy_engine`, `alert_dispatcher`, `mcp`, `skill_guard`, `fleet_layer`, `fleet_sentinel_dry_run`, `hemisphere_scheduler`).

### Module Self-Test Suites

```bash
# Run inside the container (or inside .venv on bare-metal)
docker compose exec butterclaw python -m butterclaw.config            # 23/23 config & SkillGuard assertions
docker compose exec butterclaw python -m butterclaw.policy_engine     # 16/16 DRIFT & Arsenal assertions
./dash.sh test                                                        # 7/7 SkillGuard Gate M5/M10 unit tests
```

### Auth Gateway Diagnostics

The auth gateway supports **4 roles** (`infrastructure`, `admin`, `operator`, `viewer`). When diagnosing access issues, check the role of the key in use:

```bash
# List all non-infrastructure API keys (requires admin Bearer token)
curl -sk -H "Authorization: Bearer <admin_key>" https://localhost/api/auth/keys

# Check identity and role of the current token
curl -sk -H "Authorization: Bearer <any_key>" https://localhost/api/auth/whoami
```

> The `infrastructure` role (privilege level `4`, highest) is bootstrapped automatically from the
> `BUTTERCLAW_API_KEY` environment variable at startup via
> `bootstrap_infrastructure_keys_auto_heal()`. It does not appear in `GET /api/auth/keys`
> listings and cannot be created or deleted via the API. If the infrastructure key is
> wiped during a Gibson event, restart the server with `BUTTERCLAW_API_KEY` set in `.env` to auto-heal it.

### Watcher Diagnostics

```bash
# Check retry queue depth (host bare-metal path; inside Docker check /data/retry_queue.json)
python3 -c "import json; q = json.load(open('retry_queue.json')); print(f'{len(q)} items queued')"

# Replay the gateway log against the live API
python3 -m butterclaw.watcher --replay
```

### Docker Stack & TUI Diagnostics

```bash
docker compose ps
docker compose logs -f butterclaw       # Flask API + Guardian Brain + Watcher
docker compose logs -f nginx            # TLS proxy
docker logs -f butterclaw-ntfy          # ntfy push server (port 2586)

# Launch real-time TUI SOC dashboard
./dash.sh                               # Windows: .\dash.bat
```

---

## 8. ntfy Push Notifications

The Docker stack bundles a self-hosted ntfy server as `butterclaw-ntfy` on port `2586`.
This is the backend for the `ntfy` alert channel type — no external `ntfy.sh` account or internet access required.

If `BUTTERCLAW_ALERT_NTFY_TOPIC` is set in `.env` (configured automatically by `setup_wizard.py`), ButterClaw auto-creates the channel and default critical alert rules on startup via `bootstrap_infrastructure_alerts()`.

```bash
# Subscribe to alerts via ntfy CLI
ntfy subscribe http://localhost:2586/<your-ntfy-topic>

# Or open the local ntfy web UI in your browser
open http://localhost:2586
```

When creating an additional `ntfy` channel manually via `POST /api/alerts/channels` (or the Alert Dispatcher modal on `routing.html`), set:
- `channel_type`: `"ntfy"`
- `config`: `{"url": "http://butterclaw-ntfy:2586", "topic": "butterclaw-alerts"}` *(use the internal Docker service hostname `http://butterclaw-ntfy:2586`, not `localhost`)*

---

## Related Documentation

* [`API.md`](API.md) — Full endpoint reference (80 routes, 4-tier RBAC)
* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, Gate M5/M10 invariants, design decisions
* [`RUNBOOK.md`](RUNBOOK.md) — Fleet quarantine vs. block flowchart, dry-run rollout, alert procedures (v0.9.0)
* [`SECURITY.md`](SECURITY.md) — OWASP ASI coverage, security headers, responsible disclosure
* [`THREAT_MODEL.md`](THREAT_MODEL.md) — Updated threat model

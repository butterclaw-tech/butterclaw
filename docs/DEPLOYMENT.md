# 🚀 ButterClaw Deployment Guide

This guide covers Docker (recommended), systemd (bare-metal), and the shared steps
that apply to both: LLM setup, backup, and configuration.

---

## Prerequisites

- Docker + Docker Compose v2 (Docker deployment)
- Python 3.11+ (bare-metal deployment)
- [Ollama](https://ollama.ai) installed and running
- A valid SSL certificate (self-signed is fine for local use)

---

## 1. LLM Setup — Ollama Model

ButterClaw uses a tuned profile of `gemma4:e4b` optimised for security log analysis.
Two steps are required — first pull the base model from the Ollama registry, then build
the ButterClaw-optimised variant from `Modelfile.example`:

​```bash
# Step 1 — pull the base model from the Ollama registry
ollama pull gemma4:e4b

# Step 2 — build the ButterClaw-optimised variant
# Applies: 16k context window, temperature 0.3, top_p 0.9
ollama create butterclaw-optimized -f Modelfile.example
​```

**Modelfile.example parameters:**

| Parameter | Value | Purpose |
|---|---|---|
| `FROM` | `gemma4:e4b` | Base model |
| `num_ctx` | `16384` | 16k context window — handles large 4096-char sanitised log payloads |
| `temperature` | `0.3` | Low variance — prioritises precision over creativity for threat classification |
| `top_p` | `0.9` | Nucleus sampling ceiling |

> The model name used in `butterclaw.yml` (`OLLAMA_MODEL`) must match the name given
> to `ollama create`. If you use a different name, update `OLLAMA_MODEL` accordingly.

---

## 2. Docker Deployment (Recommended)

### Stack Overview

The `docker-compose.yml` defines three services:

| Container Name | Service | Port | Resource Limit |
|---|---|---|---|
| `butterclaw-server` | ButterClaw Flask API + Guardian Brain | Internal only | 512 MB RAM, 1 CPU |
| *(auto-named)* | nginx — TLS termination and reverse proxy | `443` (external), `80` → redirect | — |
| `butterclaw-ntfy` | ntfy — bundled push notification server | `2586` | — |

**Volumes:**
- `butterclaw-data:/data` — persistent data volume for SQLite and runtime state
- `./nginx:/etc/nginx/conf.d:ro` — mounts the entire `nginx/` directory read-only;
  both `butterclaw.conf` and `default.conf` are served automatically

> **Note:** The Watcher daemon (`watcher.py`) is **not** a Docker service. It runs as
> a separate process on the host (see Section 4). It is not defined in `docker-compose.yml`.

### Start the Stack

​```bash
# Copy and edit config
cp butterclaw.yml.example butterclaw.yml
nano butterclaw.yml

# Set the mandatory env var for infrastructure key bootstrapping
export BUTTERCLAW_API_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

# Start all services
docker compose up -d

# Verify health
docker compose ps
curl -s https://localhost/api/health | python3 -m json.tool
​```

### nginx Configuration Files

The nginx service mounts `./nginx:/etc/nginx/conf.d:ro`. The two files in `nginx/` are:

- **`nginx/butterclaw.conf`** — primary vhost: TLS termination, security headers,
  proxy rules, SSE location block
- **`nginx/default.conf`** — fallback: catches unmatched hostnames, returns 444

To update nginx config, edit `nginx/butterclaw.conf` and reload:

​```bash
docker compose exec nginx nginx -s reload
​```

> **Note:** `nginx/nginx.conf` does not exist. The `conf.d` mount pattern means all
> `.conf` files in `nginx/` are included automatically by the nginx container.

### Stopping and Updating

​```bash
docker compose down
git pull
docker compose build butterclaw
docker compose up -d
​```

---

## 3. Configuration Reference

Configuration is loaded from `butterclaw.yml` (or environment variable overrides).
All 26 fields across 9 categories are described in the example config file. Key fields:

| Field | Category | Description |
|---|---|---|
| `INSTANCE_ID` | Core | Unique identifier for this deployment — appears in alert payloads |
| `OLLAMA_HOST` | LLM | Ollama API base URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | LLM | Must match the name passed to `ollama create` |
| `PARANOIA_LEVEL` | Response | 1 = Observe, 2 = Active Defense, 3 = Lockdown+Gibson |
| `DRY_RUN` | Safety | `true` hard-blocks Gibson and all destructive actions at code level |
| `BUTTERCLAW_API_KEY` | Auth | Seed for `infrastructure` role key bootstrap — set as env var, not in YAML |
| `AUTH_RATE_ADMIN` | Auth | Rate limit (req/min) for admin role keys |
| `AUTH_RATE_OPERATOR` | Auth | Rate limit (req/min) for operator role keys |
| `AUTH_RATE_VIEWER` | Auth | Rate limit (req/min) for viewer role keys |

---

## 4. Watcher Daemon

The Watcher monitors `openclaw_gateway.log` for new lines and forwards them to the
Flask API for analysis. It runs separately from the Docker stack.

​```bash
# Standard mode — tail from current EOF
python3 watcher.py

# Replay mode — read log from beginning (useful for testing)
python3 watcher.py --replay
​```

**Watcher runtime behaviour:**
- PID lock file (`watcher.pid`) prevents duplicate instances — a second invocation
  detects the live PID and exits
- Retry queue (`retry_queue.json`) persists up to 100 undelivered events to disk on
  SIGTERM/SIGINT and reloads them on next boot
- Log rotation is detected automatically (inode + size comparison)
- The watcher POSTs to `http://127.0.0.1:5000/api/analyze` — unauthenticated at the
  transport layer by design (localhost only — see `ARCHITECTURE.md` D-03)

> **Note:** There is currently no `watcher.service` unit file in the repo — only
> `butterclaw.service` exists in `systemd/`. To survive reboots on a bare-metal install,
> add an `ExecStartPost` directive to `butterclaw.service` or run the watcher in a
> `screen`/`tmux` session. A dedicated `watcher.service` unit is planned for a future release.

---

## 5. systemd Deployment (Bare-Metal)

A single systemd unit file is provided: `systemd/butterclaw.service`.

​```bash
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw
sudo systemctl status butterclaw
journalctl -u butterclaw -f
​```

### systemd Security Hardening

| Directive | Value | Effect |
|---|---|---|
| `ProtectSystem` | `strict` | Mounts `/`, `/usr`, `/boot` as read-only |
| `NoNewPrivileges` | `true` | Prevents privilege escalation via `setuid`/`setgid` |
| `ProtectHome` | `true` | Makes `/home`, `/root`, `/run/user` invisible |
| `PrivateTmp` | `true` | Gives the process a private `/tmp` namespace |
| `ReadWritePaths` | `/opt/butterclaw /opt/butterclaw/butterclaw.db` | Only these paths are writable |

> **Known gap:** `ReadWritePaths` does not currently include `retry_queue.json` or
> `watcher.pid`. If you run the watcher under the same unit with `ProtectSystem=strict`,
> those files will fail to write. Add the following to your local copy of the unit file
> until this is fixed upstream:
> `ReadWritePaths=/opt/butterclaw /opt/butterclaw/butterclaw.db /opt/butterclaw/retry_queue.json /opt/butterclaw/watcher.pid`

---

## 6. Backup

​```bash
# Run backup manually
bash scripts/backup.sh

# Schedule via cron (daily at 03:00)
echo "0 3 * * * /opt/butterclaw/scripts/backup.sh" | crontab -

# Override database path
BUTTERCLAW_DB_PATH=/custom/path/butterclaw.db bash scripts/backup.sh
​```

**What `backup.sh` includes:**

| Item | Backed Up | Notes |
|---|---|---|
| `butterclaw.db` | ✅ | `sqlite3 .backup` — safe online backup, no lock required |
| `.env` | ✅ | Plain file copy |
| `retry_queue.json` | ❌ | Ephemeral queue — acceptable to lose on restore |
| `default_signatures.json` | ❌ | Tracked in git — restore from repo |
| `nginx/` | ❌ | Tracked in git — restore from repo |
| `systemd/` | ❌ | Tracked in git — restore from repo |
| OS keyring (vault master key) | ❌ | **Cannot be backed up by script.** Lives in OS keyring only. |

**Retention:** Last 7 backups kept automatically; older backups are pruned.

> ⚠️ **Critical:** The OS keyring entry holding the ButterVault master key is **not**
> included in `backup.sh` output. If you migrate to a new host or the keyring is wiped,
> the encrypted contents of `butterclaw.db` are permanently unrecoverable. Always export
> your OS keyring separately before any host migration.

---

## 7. Health Checks & Diagnostics

### API Health Endpoint

​```bash
curl -s https://localhost/api/health | python3 -m json.tool
​```

Returns: version, instance ID, uptime, Ollama connectivity, vault keyring status,
MCP transport status, active policy count, component health map.

### Auth Gateway Diagnostics

The auth gateway supports **4 roles**. When diagnosing access issues, check the role
of the key in use:

​```bash
# List all non-infrastructure API keys (requires admin Bearer token)
curl -s -H "Authorization: Bearer <admin_key>" https://localhost/api/auth/keys

# Check identity and role of the current token
curl -s -H "Authorization: Bearer <any_key>" https://localhost/api/auth/whoami
​```

> The `infrastructure` role (privilege level -1) is bootstrapped automatically from the
> `BUTTERCLAW_API_KEY` environment variable at startup via
> `bootstrap_infrastructure_keys_auto_heal()`. It does not appear in `GET /api/auth/keys`
> listings and cannot be created or deleted via the API. If the infrastructure key is
> missing after Gibson, restart the server with `BUTTERCLAW_API_KEY` set to restore it.

### Watcher Diagnostics

​```bash
# Check if watcher is running
cat /opt/butterclaw/watcher.pid

# Check retry queue depth
python3 -c "import json; q = json.load(open('retry_queue.json')); print(f'{len(q)} items queued')"

# Replay the gateway log against the live API
python3 watcher.py --replay
​```

### Docker Stack Diagnostics

​```bash
docker compose ps
docker compose logs -f butterclaw       # Flask API + Guardian Brain
docker compose logs -f nginx            # TLS proxy
docker compose logs -f butterclaw-ntfy  # ntfy push server (port 2586)
docker compose exec butterclaw bash
​```

---

## 8. ntfy Push Notifications

The Docker stack bundles a self-hosted ntfy server as `butterclaw-ntfy` on port `2586`.
This is the backend for the `ntfy` alert channel type — no external ntfy.sh account required.

​```bash
# Subscribe to alerts via ntfy CLI
ntfy subscribe http://localhost:2586/butterclaw

# Or open the ntfy web UI
open http://localhost:2586
​```

When creating an ntfy channel via `POST /api/alerts/channels`, set:
- `type`: `ntfy`
- `url`: `http://butterclaw-ntfy:2586/butterclaw` *(use the Docker service hostname
  inside the stack, not `localhost`)*

---

## Related Documentation

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, invariants, design decisions
- [`API.md`](API.md) — Full endpoint reference, RBAC role table, rate limits
- [`SECURITY.md`](SECURITY.md) — Security mechanisms, ASI coverage, known attack surfaces

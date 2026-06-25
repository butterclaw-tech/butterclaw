# 🚀 Deployment & Configuration Guide

ButterClaw is designed to be deployed anywhere—from a local laptop for agent development to a hardened, internet-facing bare-metal VPS. 

This guide covers the centralized configuration model, the four supported deployment strategies, and the backup/restore procedures for the ButterVault database.

---

## ⚙️ Centralized Configuration (`.env`)

ButterClaw strictly follows the **12-Factor App** methodology. All configuration is loaded dynamically at boot via `config.py`. You should **never** edit the Python files to change runtime behavior.

**The Priority Chain:**
1. **OS Environment Variables** (Highest priority — set by Docker or systemd)
2. **`.env` File** (Loaded if present in the project root)
3. **Hardcoded Defaults** (Lowest priority — fallback safety)

*Note: All ButterClaw variables are strictly namespaced with the `BUTTERCLAW_` prefix to prevent collision with system variables.*

### Core Configuration Variables

Copy `.env.example` to `.env` to get started. Below are the critical variables you may need to adjust:

| Variable | Default | Description |
|---|---|---|
| `BUTTERCLAW_INSTANCE_ID` | `bc_alpha` | Unique identifier for this SOC instance (used in alerts). |
| `BUTTERCLAW_DEBUG` | `false` | Enables Werkzeug debug mode. **Hard-crashes in production.** |
| `BUTTERCLAW_PORT` | `5000` | Internal Flask binding port (Nginx proxies to this). |
| `BUTTERCLAW_PARANOIA` | `1` | Defense Level: `1` (Observe), `2` (Active Defense), `3` (Lockdown). |
| `BUTTERCLAW_DRY_RUN` | `true` | When true, blocks actual `SIGKILL` and Vault destruction for safe testing. |
| `BUTTERCLAW_OLLAMA_BASE_URL`| `http://ollama:11434` | URL to your local Ollama inference engine. |
| `BUTTERCLAW_MODEL_NAME` | `gemma4:e4b` | The local model the Brain will use for probabilistic reasoning. |
| `BUTTERCLAW_ALERT_NTFY_TOPIC`| *(empty)* | Set to auto-bootstrap a local push notification channel on boot. |

---

## 🚀 Deployment Methods

### 1. Autonomous Deployment (The Fastest Path)
The autonomous installer is designed for fresh Ubuntu/Debian VPS environments. It drops time-to-value to under 60 seconds by scaffolding the `.env`, generating local OpenSSL certificates for Nginx, and igniting the Docker stack.

```bash
curl -sSL [https://raw.githubusercontent.com/butterclaw-tech/butterclaw/main/install.sh](https://raw.githubusercontent.com/butterclaw-tech/butterclaw/main/install.sh) | bash

```

### 2. Docker Compose (Production Recommended)

The standard production stack isolates ButterClaw behind an Nginx reverse proxy. Port `5000` is completely hidden from the host network.

**The 3-Container Stack:**

* `butterclaw`: The main application running as a non-root user.
* `ollama`: GPU-accelerated local inference (gracefully falls back to CPU).
* `nginx`: TLS termination, static file serving, and SSE-specific proxy buffering.

```bash
git clone [https://github.com/butterclaw-tech/butterclaw.git](https://github.com/butterclaw-tech/butterclaw.git)
cd butterclaw && git checkout main

# Configure your environment
cp .env.example .env
# Edit .env to set your INSTANCE_ID and NTFY_TOPIC

# Generate Local TLS Certificates (For Nginx)
mkdir -p nginx/certs
docker run --rm -v "${PWD}/nginx/certs:/certs" alpine/openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /certs/butterclaw.key -out /certs/butterclaw.crt -subj "/CN=localhost"

# Ignite the Exoskeleton
docker compose up -d --build

# Retrieve your Bootstrap Admin API Key
docker compose logs -f butterclaw

```

*Access the dashboard at `https://localhost` (or your server IP).*

### 3. systemd (Bare-Metal VPS)

For operators who prefer running native services without Docker overhead. The `butterclaw.service` file includes strict filesystem hardening (`ProtectSystem=strict`, `NoNewPrivileges=true`).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Install Ollama and pull the optimized model
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh
ollama pull Modelfile.example

# 3. Configure the environment
sudo cp .env.example /etc/butterclaw.env
# Edit /etc/butterclaw.env with your settings

# 4. Install and enable the service
sudo cp systemd/butterclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now butterclaw

# 5. Monitor logs and grab the initial Admin Key
journalctl -u butterclaw -f

```

### 4. Local Development (Bare-Metal)

For building custom MCP tools or testing the system locally.

```bash
pip install -r requirements.txt
cp .env.example .env

# Start the Flask API
python server.py

```

---

## 💾 Backup & Restore

Because ButterClaw stores encrypted API keys, OAuth tokens, and audit logs in SQLite, **you cannot simply copy the `butterclaw.db` file while the server is running** (this risks journal corruption).

ButterClaw provides atomic backup utilities in the `scripts/` directory.

### Create a Backup

```bash
./scripts/backup.sh

```

* Safely executes an atomic SQLite `.backup` command.
* Packages the database and the active `.env` file into a timestamped `.tar.gz` archive.
* Automatically prunes old backups to prevent disk exhaustion (keeps the last 7).

### Restore a Backup

```bash
# List all available backups
./scripts/restore.sh

# Restore from a specific archive
./scripts/restore.sh backups/butterclaw-backup-20260621-1200.tar.gz

```

* Restores both the database and the configuration.
* Interactively prompts for confirmation before overwriting active data.

---

## 🩺 Diagnostics & Health

ButterClaw includes built-in standalone diagnostic suites to verify system integrity before or after deployment. You can run these from the project root:

| Module | Command | Coverage |
| --- | --- | --- |
| **Config Loader** | `python config.py` | Validates `.env` parsing, ranges, and transport settings. |
| **Alert Dispatcher** | `python alert_dispatcher.py` | Tests webhook HMAC signing, cooldown limits, and Auth tracking. |
| **Policy Engine** | `python policy_engine.py` | Verifies priority ordering, DRIFT pattern locks, and safe evaluation. |
| **Auth Gateway** | `python auth.py` | Tests HMAC key generation, session TTLs, and RBAC tiers. |

# =============================================
# ButterClaw v0.9.2 — Production Container
# =============================================
# Multi-stage build: deps first (cached), app second
# Base: python:3.11-slim (minimal attack surface)
# No root: runs as butterclaw user

FROM python:3.11-slim AS base

# System deps (none needed beyond stdlib for ButterClaw itself)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r butterclaw && \
    useradd -r -g butterclaw -d /app -s /sbin/nologin butterclaw

WORKDIR /app

# ── Application stage ──
# 1. Copy and install dependencies first (caches this heavy layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the packaging files and source code
COPY pyproject.toml .
COPY README.md .
COPY src/ ./src/

# Copy root JSON/HTML artifacts
COPY default_signatures.json .
COPY capabilities.json .
COPY mcp_stdio_transport.json .
COPY index.html .
COPY routing.html .

# Copy scripts directory (for healthcheck, test_attack, etc.)
COPY scripts/ ./scripts/

# Install ButterClaw as a package (handles dependencies and links the module)
RUN pip install --no-cache-dir .

# Create data directory for DB volume mount and grant access to /app
RUN mkdir -p /data && chown -R butterclaw:butterclaw /data /app

# Install supervisor and create configuration file
RUN pip install --no-cache-dir supervisor && \
    mkdir -p /etc/supervisor/conf.d && \
    echo "[supervisord]" > /etc/supervisor/conf.d/butterclaw.conf && \
    echo "nodaemon=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "user=butterclaw" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "[program:server]" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "command=python -m butterclaw.server" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autostart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile=/dev/stderr" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile=/dev/stdout" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "[program:watcher]" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "command=python -m butterclaw.watcher" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autostart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile=/dev/stderr" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile=/dev/stdout" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf

# Default env vars (can be overridden by .env / docker-compose)
ENV BUTTERCLAW_HOST=0.0.0.0
ENV BUTTERCLAW_PORT=5000
ENV BUTTERCLAW_DB_PATH=/data/butterclaw.db
# v0.9.0: Fleet DB — separate file, never co-transacted with butterclaw.db (I-07-fleet)
ENV BUTTERCLAW_FLEET_DB_PATH=/data/fleet.db
# Force keyring credentials to save inside the persistent volume
ENV XDG_DATA_HOME=/data
ENV BUTTERCLAW_INSTANCE_ID=butterclaw-docker
# v0.9.0: Fleet Sentinel dry-run mode (set to false in production after validation)
ENV BUTTERCLAW_FLEET_SENTINEL_DRY_RUN=true

# Persistent data volume — both DBs live here (I-01-fleet: fleet.db in backup)
VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python /app/scripts/healthcheck.py

# Switch to non-root
USER butterclaw

EXPOSE 5000

# Start server + watcher via supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/butterclaw.conf"]
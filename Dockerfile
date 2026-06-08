# =============================================
# ButterClaw v0.6.4 — Production Container
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

# ── Dependencies stage ──
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application stage ──
FROM deps AS app

# Copy application code
COPY server.py .
COPY config.py .
COPY auth.py .
COPY policy_engine.py .
COPY alert_dispatcher.py .
COPY buttervault.py .
COPY butterclaw_mcp.py .
COPY mcp_transport.py .
COPY oauth_config.py .
COPY index.html .
COPY routing.html .
COPY watcher.py .

# Copy health check script
COPY scripts/healthcheck.py /app/scripts/healthcheck.py

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
    echo "command=python /app/server.py" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autostart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile=/dev/stderr" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stderr_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile=/dev/stdout" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "stdout_logfile_maxbytes=0" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "[program:watcher]" >> /etc/supervisor/conf.d/butterclaw.conf && \
    echo "command=python /app/watcher.py" >> /etc/supervisor/conf.d/butterclaw.conf && \
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
# Force keyring credentials to save inside the persistent volume
ENV XDG_DATA_HOME=/data
# ENV BUTTERCLAW_OLLAMA_URL=http://ollama:11434
ENV BUTTERCLAW_INSTANCE_ID=butterclaw-docker

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python /app/scripts/healthcheck.py

# Switch to non-root
USER butterclaw

EXPOSE 5000

# Start server + watcher via supervisor
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/butterclaw.conf"]
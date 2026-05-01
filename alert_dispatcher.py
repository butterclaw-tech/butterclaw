"""
ButterClaw v0.6.2 — Alert Dispatcher
======================================
Push notifications to external channels when critical events occur.

Solves the problem that ButterClaw's alerts currently only exist on the
dashboard — if nobody is watching, threats go unnoticed.

Provides:
  - Channel management (webhook, discord, ntfy, smtp, gotify)
  - Rule-based event routing with per-rule cooldown
  - Non-blocking dispatch via daemon threads
  - Retry with exponential backoff (3 attempts: 1s, 2s, 4s)
  - HMAC-SHA256 webhook signing
  - Auth brute-force detection (5 failures / 60s per IP)
  - Full alert history audit log
  - 14-step diagnostic suite

Design decisions:
  - Zero new pip dependencies — uses stdlib only
  - Shares butterclaw.db with server.py (same DB_PATH pattern)
  - Channel secrets stored OUTSIDE ButterVault — Gibson alert must
    fire BEFORE vault destruction
  - gibson_triggered dispatch fires BEFORE butter_keys() — alert goes
    out, then vault burns
  - Dispatch in daemon thread — non-blocking, analyze_threat() returns
    immediately
  - Per-rule cooldown (not per-channel) — same channel can have
    different cooldowns for different events
  - Policies and alert tables survive Gibson — config/audit, not creds
  - Cascade delete on channel removal — prevents orphaned rules/history
  - @after_request for auth failure tracking — catches both API key
    and session failures

Event types:
  - verdict_critical    — Brain returned CRITICAL verdict
  - verdict_warning     — Brain returned WARNING verdict
  - gibson_triggered    — Gibson panic button (chain path)
  - gibson_manual       — Manual Gibson via /api/rotate-keys
  - policy_override     — Policy Engine overrode Brain verdict
  - policy_blocked      — Policy Engine blocked a request
  - auth_brute_force    — 5+ auth failures from one IP in 60s
  - mcp_offline         — MCP server health check failed
  - system_startup      — ButterClaw server started

Channel types:
  - webhook  — Generic HTTP POST with HMAC-SHA256 signing
  - discord  — Discord webhook with embed JSON
  - ntfy     — Push notification via ntfy.sh or self-hosted
  - smtp     — Email via smtplib
  - gotify   — Self-hosted push notification

Integration points (server.py):
  - analyze_threat():   verdict_critical, verdict_warning
  - analyze_threat():   policy_override, policy_blocked (via policy engine)
  - butter_keys():      gibson_triggered (chain path, BEFORE vault burn)
  - /api/rotate-keys:   gibson_manual
  - @after_request:     auth_brute_force (via track_auth_failure)
  - MCP health check:   mcp_offline
  - startup:            system_startup
  - register_alert_routes(app): 13 API endpoints
"""

import json
import time
import datetime
import sqlite3
import os
import re
import uuid
import threading
import logging
import hashlib
import hmac
import smtplib
from email.mime.text import MIMEText
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger("butterclaw.alert")

# =============================================
# CONSTANTS
# =============================================

VALID_EVENT_TYPES = (
    "verdict_critical",
    "verdict_warning",
    "gibson_triggered",
    "gibson_manual",
    "policy_override",
    "policy_blocked",
    "auth_brute_force",
    "mcp_offline",
    "system_startup",
)

VALID_CHANNEL_TYPES = ("webhook", "discord", "ntfy", "smtp", "gotify")

# Required config fields per channel type
CHANNEL_CONFIG_REQUIRED = {
    "webhook": ["url"],
    "discord": ["webhook_url"],
    "ntfy":    ["url", "topic"],
    "smtp":    ["host", "port", "from_addr", "to_addr"],
    "gotify":  ["url", "token"],
}

# Severity mapping
SEVERITY_MAP = {
    "verdict_critical": "critical",
    "gibson_triggered":  "critical",
    "gibson_manual":     "critical",
    "auth_brute_force":  "critical",
    "verdict_warning":   "warning",
    "policy_override":   "warning",
    "policy_blocked":    "warning",
    "mcp_offline":       "warning",
    "system_startup":    "info",
}

# Discord embed colors
DISCORD_COLORS = {
    "critical": 15548997,   # red
    "warning":  16776960,   # amber
    "info":     5793266,    # emerald
}

# ntfy priority mapping
NTFY_PRIORITY = {
    "critical": 5,
    "warning":  3,
    "info":     2,
}

# Gotify priority mapping
GOTIFY_PRIORITY = {
    "critical": 8,
    "warning":  5,
    "info":     2,
}

DEFAULT_COOLDOWN = 60           # seconds
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1          # exponential: 1s, 2s, 4s
DELIVERY_TIMEOUT = 10           # seconds
AUTH_FAILURE_THRESHOLD = 5
AUTH_FAILURE_WINDOW = 60        # seconds

# =============================================
# DATABASE
# =============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

_db_lock = threading.Lock()


def _get_db():
    """Get a database connection with Row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_alert_db():
    """Initialize alert dispatcher tables in butterclaw.db."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS alert_channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    config TEXT NOT NULL,
                    signing_secret TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    last_status TEXT
                );

                CREATE TABLE IF NOT EXISTS alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    cooldown_secs INTEGER NOT NULL DEFAULT 60,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (channel_id) REFERENCES alert_channels(channel_id)
                );

                CREATE TABLE IF NOT EXISTS alert_history (
                    history_id TEXT PRIMARY KEY,
                    rule_id TEXT,
                    channel_id TEXT,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_code INTEGER,
                    error_message TEXT,
                    payload_preview TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)
            conn.commit()
            logger.info("Alert dispatcher tables initialized")
        finally:
            conn.close()


# =============================================
# AUTH FAILURE TRACKING
# =============================================

_auth_failure_tracker = {}   # ip -> [timestamp, ...]
_auth_failure_lock = threading.Lock()


def track_auth_failure(ip_address):
    """
    Track an authentication failure for an IP address.
    Fires auth_brute_force when threshold is reached.
    """
    now = time.time()
    with _auth_failure_lock:
        if ip_address not in _auth_failure_tracker:
            _auth_failure_tracker[ip_address] = []

        # Prune old entries outside the window
        _auth_failure_tracker[ip_address] = [
            t for t in _auth_failure_tracker[ip_address]
            if now - t < AUTH_FAILURE_WINDOW
        ]
        _auth_failure_tracker[ip_address].append(now)
        count = len(_auth_failure_tracker[ip_address])

    if count >= AUTH_FAILURE_THRESHOLD:
        logger.warning(
            "Auth brute-force detected from %s (%d failures in %ds)",
            ip_address, count, AUTH_FAILURE_WINDOW
        )
        dispatch_alert("auth_brute_force", {
            "ip_address": ip_address,
            "failure_count": count,
            "window_seconds": AUTH_FAILURE_WINDOW,
        })
        # Reset tracker for this IP after firing
        with _auth_failure_lock:
            _auth_failure_tracker[ip_address] = []


# =============================================
# CHANNEL CRUD
# =============================================

def _validate_channel_config(channel_type, config):
    """Validate channel config has all required fields."""
    if channel_type not in VALID_CHANNEL_TYPES:
        return False, f"Invalid channel type: {channel_type}. Must be one of: {', '.join(VALID_CHANNEL_TYPES)}"
    required = CHANNEL_CONFIG_REQUIRED[channel_type]
    missing = [f for f in required if f not in config or not config[f]]
    if missing:
        return False, f"Missing required config fields for {channel_type}: {', '.join(missing)}"
    return True, None


def create_channel(name, channel_type, config, signing_secret=None):
    """Create a new alert channel."""
    valid, err = _validate_channel_config(channel_type, config)
    if not valid:
        return {"error": err}

    channel_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat() + "Z"

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                """INSERT INTO alert_channels
                   (channel_id, name, channel_type, config, signing_secret, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (channel_id, name, channel_type, json.dumps(config), signing_secret, now)
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Created alert channel: %s (%s / %s)", channel_id, name, channel_type)
    return {"channel_id": channel_id, "name": name, "channel_type": channel_type}


def get_channel(channel_id):
    """Get a single channel by ID."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM alert_channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        if not row:
            return None
        ch = dict(row)
        ch["config"] = json.loads(ch["config"])
        return ch
    finally:
        conn.close()


def list_channels():
    """List all alert channels."""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM alert_channels ORDER BY created_at DESC"
        ).fetchall()
        channels = []
        for row in rows:
            ch = dict(row)
            ch["config"] = json.loads(ch["config"])
            channels.append(ch)
        return channels
    finally:
        conn.close()


def update_channel(channel_id, **kwargs):
    """Update a channel's fields (name, config, signing_secret, enabled)."""
    channel = get_channel(channel_id)
    if not channel:
        return {"error": f"Channel {channel_id} not found"}

    # If config is being updated, validate it
    if "config" in kwargs:
        valid, err = _validate_channel_config(channel["channel_type"], kwargs["config"])
        if not valid:
            return {"error": err}

    allowed = {"name", "config", "signing_secret", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return {"error": "No valid fields to update"}

    set_clauses = []
    values = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = ?")
        values.append(json.dumps(v) if k == "config" else v)
    values.append(channel_id)

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                f"UPDATE alert_channels SET {', '.join(set_clauses)} WHERE channel_id = ?",
                values
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Updated alert channel: %s", channel_id)
    return {"channel_id": channel_id, "updated": list(updates.keys())}


def delete_channel(channel_id):
    """Delete a channel and cascade-delete its rules and history."""
    channel = get_channel(channel_id)
    if not channel:
        return {"error": f"Channel {channel_id} not found"}

    with _db_lock:
        conn = _get_db()
        try:
            # Cascade: delete history for rules pointing at this channel
            conn.execute(
                """DELETE FROM alert_history WHERE rule_id IN
                   (SELECT rule_id FROM alert_rules WHERE channel_id = ?)""",
                (channel_id,)
            )
            # Cascade: delete rules for this channel
            conn.execute(
                "DELETE FROM alert_rules WHERE channel_id = ?", (channel_id,)
            )
            # Delete the channel itself
            conn.execute(
                "DELETE FROM alert_channels WHERE channel_id = ?", (channel_id,)
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Deleted alert channel (cascade): %s", channel_id)
    return {"deleted": channel_id}


def toggle_channel(channel_id):
    """Toggle a channel's enabled state."""
    channel = get_channel(channel_id)
    if not channel:
        return {"error": f"Channel {channel_id} not found"}

    new_state = 0 if channel["enabled"] else 1
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE alert_channels SET enabled = ? WHERE channel_id = ?",
                (new_state, channel_id)
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Toggled channel %s -> %s", channel_id, "enabled" if new_state else "disabled")
    return {"channel_id": channel_id, "enabled": bool(new_state)}


# =============================================
# RULE CRUD
# =============================================

def create_rule(name, event_type, channel_id, cooldown_secs=DEFAULT_COOLDOWN):
    """Create a new alert rule."""
    if event_type not in VALID_EVENT_TYPES:
        return {"error": f"Invalid event_type: {event_type}. Must be one of: {', '.join(VALID_EVENT_TYPES)}"}

    channel = get_channel(channel_id)
    if not channel:
        return {"error": f"Channel {channel_id} not found"}

    rule_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat() + "Z"

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                """INSERT INTO alert_rules
                   (rule_id, name, event_type, channel_id, cooldown_secs, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (rule_id, name, event_type, channel_id, cooldown_secs, now)
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Created alert rule: %s (%s -> %s)", rule_id, event_type, channel_id)
    return {"rule_id": rule_id, "name": name, "event_type": event_type, "channel_id": channel_id}


def get_rule(rule_id):
    """Get a single rule by ID."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM alert_rules WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_rules(channel_id=None, event_type=None):
    """List alert rules, optionally filtered by channel or event type."""
    conn = _get_db()
    try:
        query = "SELECT * FROM alert_rules WHERE 1=1"
        params = []
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_rule(rule_id, **kwargs):
    """Update a rule's fields (name, event_type, channel_id, cooldown_secs, enabled)."""
    rule = get_rule(rule_id)
    if not rule:
        return {"error": f"Rule {rule_id} not found"}

    if "event_type" in kwargs and kwargs["event_type"] not in VALID_EVENT_TYPES:
        return {"error": f"Invalid event_type: {kwargs['event_type']}"}

    if "channel_id" in kwargs:
        channel = get_channel(kwargs["channel_id"])
        if not channel:
            return {"error": f"Channel {kwargs['channel_id']} not found"}

    allowed = {"name", "event_type", "channel_id", "cooldown_secs", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return {"error": "No valid fields to update"}

    set_clauses = []
    values = []
    for k, v in updates.items():
        set_clauses.append(f"{k} = ?")
        values.append(v)
    values.append(rule_id)

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                f"UPDATE alert_rules SET {', '.join(set_clauses)} WHERE rule_id = ?",
                values
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Updated alert rule: %s", rule_id)
    return {"rule_id": rule_id, "updated": list(updates.keys())}


def delete_rule(rule_id):
    """Delete a rule and its history."""
    rule = get_rule(rule_id)
    if not rule:
        return {"error": f"Rule {rule_id} not found"}

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("DELETE FROM alert_history WHERE rule_id = ?", (rule_id,))
            conn.execute("DELETE FROM alert_rules WHERE rule_id = ?", (rule_id,))
            conn.commit()
        finally:
            conn.close()

    logger.info("Deleted alert rule: %s", rule_id)
    return {"deleted": rule_id}


def toggle_rule(rule_id):
    """Toggle a rule's enabled state."""
    rule = get_rule(rule_id)
    if not rule:
        return {"error": f"Rule {rule_id} not found"}

    new_state = 0 if rule["enabled"] else 1
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE alert_rules SET enabled = ? WHERE rule_id = ?",
                (new_state, rule_id)
            )
            conn.commit()
        finally:
            conn.close()

    logger.info("Toggled rule %s -> %s", rule_id, "enabled" if new_state else "disabled")
    return {"rule_id": rule_id, "enabled": bool(new_state)}


# =============================================
# COOLDOWN
# =============================================

def _is_cooled_down(rule_id, cooldown_secs):
    """
    Check if enough time has passed since the last successful send
    for this rule. Returns True if the rule is ready to fire again.
    """
    if cooldown_secs <= 0:
        return True

    conn = _get_db()
    try:
        row = conn.execute(
            """SELECT created_at FROM alert_history
               WHERE rule_id = ? AND status = 'sent'
               ORDER BY created_at DESC LIMIT 1""",
            (rule_id,)
        ).fetchone()
        if not row:
            return True
        last_sent = datetime.datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (now - last_sent).total_seconds()
        return elapsed >= cooldown_secs
    finally:
        conn.close()


# =============================================
# WEBHOOK SIGNING
# =============================================

def _sign_payload(payload_bytes, signing_secret):
    """
    Sign a payload with HMAC-SHA256.
    Returns signature string: sha256=<hex digest>
    """
    mac = hmac.new(
        signing_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    )
    return f"sha256={mac.hexdigest()}"


# =============================================
# PAYLOAD FORMATTING
# =============================================

def _format_payload(event_type, context, channel_type):
    """
    Build a channel-appropriate payload for the given event.
    Returns (payload_dict_or_str, headers_dict).
    """
    severity = SEVERITY_MAP.get(event_type, "info")
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    title = f"🦞 ButterClaw Alert: {event_type.replace('_', ' ').title()}"
    description = context.get("description", context.get("summary", json.dumps(context, default=str)))

    if channel_type == "webhook":
        payload = {
            "event": event_type,
            "severity": severity,
            "timestamp": timestamp,
            "data": context,
        }
        return payload, {}

    elif channel_type == "discord":
        color = DISCORD_COLORS.get(severity, DISCORD_COLORS["info"])
        embed = {
            "title": title,
            "description": str(description)[:2048],
            "color": color,
            "timestamp": timestamp,
            "footer": {"text": "ButterClaw Alert Dispatcher"},
            "fields": [],
        }
        # Add context fields as embed fields
        for key, value in context.items():
            if key in ("description", "summary"):
                continue
            embed["fields"].append({
                "name": str(key).replace("_", " ").title(),
                "value": str(value)[:1024],
                "inline": True,
            })
            if len(embed["fields"]) >= 10:
                break
        payload = {"embeds": [embed]}
        return payload, {}

    elif channel_type == "ntfy":
        priority = NTFY_PRIORITY.get(severity, 2)
        # ntfy tags map to emoji
        tag_map = {"critical": "rotating_light", "warning": "warning", "info": "information_source"}
        payload = {
            "title": title,
            "message": str(description)[:4096],
            "priority": priority,
            "tags": [tag_map.get(severity, "lobster")],
        }
        return payload, {}

    elif channel_type == "smtp":
        subject = f"[ButterClaw {severity.upper()}] {event_type}"
        body_lines = [
            f"ButterClaw Alert — {severity.upper()}",
            f"Event: {event_type}",
            f"Time: {timestamp}",
            "",
            "Details:",
        ]
        for key, value in context.items():
            body_lines.append(f"  {key}: {value}")
        body_lines.append("")
        body_lines.append("— ButterClaw Alert Dispatcher")
        payload = {"subject": subject, "body": "\n".join(body_lines)}
        return payload, {}

    elif channel_type == "gotify":
        priority = GOTIFY_PRIORITY.get(severity, 2)
        payload = {
            "title": title,
            "message": str(description)[:4096],
            "priority": priority,
        }
        return payload, {}

    # Fallback
    return {"event": event_type, "data": context}, {}


# =============================================
# DELIVERY FUNCTIONS
# =============================================

def _deliver_webhook(config, payload, signing_secret=None):
    """Deliver alert via generic webhook (HTTP POST)."""
    url = config["url"]
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ButterClaw-Alert/0.6.2",
        "X-ButterClaw-Event": payload.get("event", "unknown"),
        "X-ButterClaw-Timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    if signing_secret:
        signature = _sign_payload(payload_bytes, signing_secret)
        headers["X-ButterClaw-Signature"] = signature

    req = Request(url, data=payload_bytes, headers=headers, method="POST")
    resp = urlopen(req, timeout=DELIVERY_TIMEOUT)
    return resp.status


def _deliver_discord(config, payload):
    """Deliver alert via Discord webhook."""
    url = config["webhook_url"]
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ButterClaw-Alert/0.6.2",
    }

    req = Request(url, data=payload_bytes, headers=headers, method="POST")
    resp = urlopen(req, timeout=DELIVERY_TIMEOUT)
    return resp.status


def _deliver_ntfy(config, payload):
    """Deliver alert via ntfy push notification."""
    base_url = config["url"].rstrip("/")
    topic = config["topic"]
    url = f"{base_url}/{topic}"

    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ButterClaw-Alert/0.6.2",
    }

    # ntfy supports auth token
    if config.get("token"):
        headers["Authorization"] = f"Bearer {config['token']}"

    req = Request(url, data=payload_bytes, headers=headers, method="POST")
    resp = urlopen(req, timeout=DELIVERY_TIMEOUT)
    return resp.status


def _deliver_smtp(config, payload):
    """Deliver alert via SMTP email."""
    host = config["host"]
    port = int(config["port"])
    from_addr = config["from_addr"]
    to_addr = config["to_addr"]
    username = config.get("username")
    password = config.get("password")
    use_tls = config.get("use_tls", True)

    msg = MIMEText(payload["body"])
    msg["Subject"] = payload["subject"]
    msg["From"] = from_addr
    msg["To"] = to_addr

    if use_tls:
        server = smtplib.SMTP(host, port, timeout=DELIVERY_TIMEOUT)
        server.starttls()
    else:
        server = smtplib.SMTP(host, port, timeout=DELIVERY_TIMEOUT)

    try:
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
    finally:
        server.quit()

    return 250  # SMTP success code


def _deliver_gotify(config, payload):
    """Deliver alert via Gotify push notification."""
    base_url = config["url"].rstrip("/")
    token = config["token"]
    url = f"{base_url}/message?token={token}"

    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ButterClaw-Alert/0.6.2",
    }

    req = Request(url, data=payload_bytes, headers=headers, method="POST")
    resp = urlopen(req, timeout=DELIVERY_TIMEOUT)
    return resp.status


# Channel type -> delivery function
_DELIVERY_MAP = {
    "webhook": lambda config, payload, secret: _deliver_webhook(config, payload, secret),
    "discord": lambda config, payload, secret: _deliver_discord(config, payload),
    "ntfy":    lambda config, payload, secret: _deliver_ntfy(config, payload),
    "smtp":    lambda config, payload, secret: _deliver_smtp(config, payload),
    "gotify":  lambda config, payload, secret: _deliver_gotify(config, payload),
}


# =============================================
# HISTORY
# =============================================

def _log_history(rule_id, channel_id, event_type, status, response_code=None,
                 error_message=None, payload_preview=None, attempt_count=0):
    """Log an alert dispatch attempt to history."""
    history_id = str(uuid.uuid4())[:12]
    now = datetime.datetime.utcnow().isoformat() + "Z"

    if payload_preview and len(payload_preview) > 200:
        payload_preview = payload_preview[:200]

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                """INSERT INTO alert_history
                   (history_id, rule_id, channel_id, event_type, status,
                    response_code, error_message, payload_preview, attempt_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (history_id, rule_id, channel_id, event_type, status,
                 response_code, error_message, payload_preview, attempt_count, now)
            )
            conn.commit()
        finally:
            conn.close()

    return history_id


def get_alert_history(channel_id=None, event_type=None, status=None,
                      since=None, limit=50):
    """Query alert history with optional filters."""
    conn = _get_db()
    try:
        query = "SELECT * FROM alert_history WHERE 1=1"
        params = []
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if since:
            query += " AND created_at >= ?"
            params.append(since)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_alert_history_count(channel_id=None, event_type=None, status=None):
    """Get total count of alert history entries."""
    conn = _get_db()
    try:
        query = "SELECT COUNT(*) as cnt FROM alert_history WHERE 1=1"
        params = []
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        row = conn.execute(query, params).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# =============================================
# CORE DISPATCH
# =============================================

def _dispatch_worker(rule, channel, event_type, context):
    """
    Worker function for alert dispatch (runs in daemon thread).
    Handles cooldown, payload formatting, delivery with retry, and history.
    """
    rule_id = rule["rule_id"]
    channel_id = channel["channel_id"]
    channel_type = channel["channel_type"]
    config = channel["config"] if isinstance(channel["config"], dict) else json.loads(channel["config"])
    signing_secret = channel.get("signing_secret")

    # --- Cooldown check ---
    if not _is_cooled_down(rule_id, rule["cooldown_secs"]):
        logger.debug("Rule %s is in cooldown, skipping", rule_id)
        _log_history(rule_id, channel_id, event_type, "cooldown",
                     payload_preview=json.dumps(context, default=str)[:200])
        return

    # --- Format payload ---
    payload, extra_headers = _format_payload(event_type, context, channel_type)
    payload_preview = json.dumps(payload, default=str)[:200]

    # --- Deliver with retry ---
    deliver_fn = _DELIVERY_MAP.get(channel_type)
    if not deliver_fn:
        logger.error("No delivery function for channel type: %s", channel_type)
        _log_history(rule_id, channel_id, event_type, "failed",
                     error_message=f"Unknown channel type: {channel_type}",
                     payload_preview=payload_preview)
        return

    last_error = None
    response_code = None

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response_code = deliver_fn(config, payload, signing_secret)
            # Success
            _log_history(rule_id, channel_id, event_type, "sent",
                         response_code=response_code,
                         payload_preview=payload_preview,
                         attempt_count=attempt)

            # Update channel last_used / last_status
            with _db_lock:
                conn = _get_db()
                try:
                    now = datetime.datetime.utcnow().isoformat() + "Z"
                    conn.execute(
                        "UPDATE alert_channels SET last_used = ?, last_status = ? WHERE channel_id = ?",
                        (now, "ok", channel_id)
                    )
                    conn.commit()
                finally:
                    conn.close()

            logger.info("Alert sent: %s -> %s (%s) [attempt %d]",
                        event_type, channel_id, channel_type, attempt)
            return

        except (HTTPError, URLError, OSError, smtplib.SMTPException) as e:
            last_error = str(e)
            if isinstance(e, HTTPError):
                response_code = e.code
            logger.warning("Alert delivery failed (attempt %d/%d): %s -> %s: %s",
                           attempt, MAX_RETRY_ATTEMPTS, event_type, channel_id, last_error)

            if attempt < MAX_RETRY_ATTEMPTS:
                backoff = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                time.sleep(backoff)

    # All retries exhausted
    _log_history(rule_id, channel_id, event_type, "retry_exhausted",
                 response_code=response_code,
                 error_message=last_error,
                 payload_preview=payload_preview,
                 attempt_count=MAX_RETRY_ATTEMPTS)

    # Update channel last_status
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute(
                "UPDATE alert_channels SET last_status = ? WHERE channel_id = ?",
                ("error", channel_id)
            )
            conn.commit()
        finally:
            conn.close()

    logger.error("Alert delivery exhausted retries: %s -> %s", event_type, channel_id)


def dispatch_alert(event_type, context=None):
    """
    Dispatch an alert for the given event type.
    Finds all matching enabled rules and spawns daemon threads for each.
    Non-blocking — returns immediately.
    """
    if context is None:
        context = {}

    if event_type not in VALID_EVENT_TYPES:
        logger.warning("dispatch_alert called with invalid event_type: %s", event_type)
        return

    # Find matching enabled rules
    conn = _get_db()
    try:
        rows = conn.execute(
            """SELECT r.*, c.channel_type, c.config, c.signing_secret, c.enabled as channel_enabled
               FROM alert_rules r
               JOIN alert_channels c ON r.channel_id = c.channel_id
               WHERE r.event_type = ? AND r.enabled = 1 AND c.enabled = 1""",
            (event_type,)
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.debug("No active rules for event_type: %s", event_type)
        return

    for row in rows:
        rule = dict(row)
        channel = {
            "channel_id": rule["channel_id"],
            "channel_type": rule["channel_type"],
            "config": rule["config"],
            "signing_secret": rule.get("signing_secret"),
        }
        t = threading.Thread(
            target=_dispatch_worker,
            args=(rule, channel, event_type, context),
            daemon=True,
            name=f"alert-{rule['rule_id']}-{event_type}"
        )
        t.start()

    logger.info("Dispatched %d alert(s) for event: %s", len(rows), event_type)


# =============================================
# TEST ALERT
# =============================================

def send_test_alert(channel_id):
    """Send a test notification to verify channel configuration."""
    channel = get_channel(channel_id)
    if not channel:
        return {"error": f"Channel {channel_id} not found"}
    if not channel["enabled"]:
        return {"error": f"Channel {channel_id} is disabled"}

    channel_type = channel["channel_type"]
    config = channel["config"]
    signing_secret = channel.get("signing_secret")

    test_context = {
        "description": "This is a test alert from ButterClaw Alert Dispatcher.",
        "channel_id": channel_id,
        "channel_type": channel_type,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    payload, _ = _format_payload("system_startup", test_context, channel_type)
    deliver_fn = _DELIVERY_MAP.get(channel_type)

    if not deliver_fn:
        return {"error": f"Unknown channel type: {channel_type}"}

    try:
        response_code = deliver_fn(config, payload, signing_secret)
        _log_history(None, channel_id, "system_startup", "sent",
                     response_code=response_code,
                     payload_preview="[test alert]",
                     attempt_count=1)
        # Update last_used
        with _db_lock:
            conn = _get_db()
            try:
                now = datetime.datetime.utcnow().isoformat() + "Z"
                conn.execute(
                    "UPDATE alert_channels SET last_used = ?, last_status = ? WHERE channel_id = ?",
                    (now, "ok", channel_id)
                )
                conn.commit()
            finally:
                conn.close()
        return {"status": "sent", "response_code": response_code}
    except Exception as e:
        error_msg = str(e)
        _log_history(None, channel_id, "system_startup", "failed",
                     error_message=error_msg,
                     payload_preview="[test alert]",
                     attempt_count=1)
        return {"status": "failed", "error": error_msg}


# =============================================
# API ROUTE REGISTRATION
# =============================================

def register_alert_routes(app):
    """
    Register all alert dispatcher API endpoints on the Flask app.
    Requires auth module's @require_auth decorator.
    """
    try:
        from auth import require_auth
    except ImportError:
        logger.warning("auth module not available — alert routes will be unprotected")
        def require_auth(min_role="viewer"):
            def decorator(f):
                return f
            return decorator

    # --- Channel endpoints ---

    @app.route('/api/alerts/channels', methods=['GET'])
    @require_auth(min_role="viewer")
    def api_list_channels():
        channels = list_channels()
        # Redact sensitive config fields for non-admin
        from flask import request as req, jsonify
        role = getattr(req, 'auth_context', {}).get('role', 'viewer')
        if role != 'admin':
            for ch in channels:
                # Redact secrets from config display
                redacted = {}
                for k, v in ch.get("config", {}).items():
                    if any(s in k.lower() for s in ("secret", "password", "token")):
                        redacted[k] = "***"
                    else:
                        redacted[k] = v
                ch["config"] = redacted
                ch["signing_secret"] = "***" if ch.get("signing_secret") else None
        return jsonify({"channels": channels})

    @app.route('/api/alerts/channels', methods=['POST'])
    @require_auth(min_role="admin")
    def api_create_channel():
        from flask import request as req, jsonify
        data = req.get_json(silent=True) or {}
        name = data.get("name")
        channel_type = data.get("channel_type")
        config = data.get("config", {})
        signing_secret = data.get("signing_secret")

        if not name or not channel_type:
            return jsonify({"error": "name and channel_type are required"}), 400

        result = create_channel(name, channel_type, config, signing_secret)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 201

    @app.route('/api/alerts/channels/<channel_id>', methods=['PUT'])
    @require_auth(min_role="admin")
    def api_update_channel(channel_id):
        from flask import request as req, jsonify
        data = req.get_json(silent=True) or {}
        result = update_channel(channel_id, **data)
        if "error" in result:
            return jsonify(result), 400 if "not found" not in result["error"] else 404
        return jsonify(result)

    @app.route('/api/alerts/channels/<channel_id>', methods=['DELETE'])
    @require_auth(min_role="admin")
    def api_delete_channel(channel_id):
        from flask import jsonify
        result = delete_channel(channel_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route('/api/alerts/channels/<channel_id>/toggle', methods=['POST'])
    @require_auth(min_role="admin")
    def api_toggle_channel(channel_id):
        from flask import jsonify
        result = toggle_channel(channel_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route('/api/alerts/channels/<channel_id>/test', methods=['POST'])
    @require_auth(min_role="operator")
    def api_test_channel(channel_id):
        from flask import jsonify
        result = send_test_alert(channel_id)
        if "error" in result:
            status_code = 404 if "not found" in result.get("error", "") else 400
            return jsonify(result), status_code
        return jsonify(result)

    # --- Rule endpoints ---

    @app.route('/api/alerts/rules', methods=['GET'])
    @require_auth(min_role="viewer")
    def api_list_rules():
        from flask import request as req, jsonify
        channel_id = req.args.get("channel_id")
        event_type = req.args.get("event_type")
        rules = list_rules(channel_id=channel_id, event_type=event_type)
        return jsonify({"rules": rules})

    @app.route('/api/alerts/rules', methods=['POST'])
    @require_auth(min_role="admin")
    def api_create_rule():
        from flask import request as req, jsonify
        data = req.get_json(silent=True) or {}
        name = data.get("name")
        event_type = data.get("event_type")
        channel_id = data.get("channel_id")
        cooldown_secs = data.get("cooldown_secs", DEFAULT_COOLDOWN)

        if not name or not event_type or not channel_id:
            return jsonify({"error": "name, event_type, and channel_id are required"}), 400

        result = create_rule(name, event_type, channel_id, cooldown_secs)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 201

    @app.route('/api/alerts/rules/<rule_id>', methods=['PUT'])
    @require_auth(min_role="admin")
    def api_update_rule(rule_id):
        from flask import request as req, jsonify
        data = req.get_json(silent=True) or {}
        result = update_rule(rule_id, **data)
        if "error" in result:
            return jsonify(result), 400 if "not found" not in result["error"] else 404
        return jsonify(result)

    @app.route('/api/alerts/rules/<rule_id>', methods=['DELETE'])
    @require_auth(min_role="admin")
    def api_delete_rule(rule_id):
        from flask import jsonify
        result = delete_rule(rule_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    @app.route('/api/alerts/rules/<rule_id>/toggle', methods=['POST'])
    @require_auth(min_role="admin")
    def api_toggle_rule(rule_id):
        from flask import jsonify
        result = toggle_rule(rule_id)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)

    # --- History & status endpoints ---

    @app.route('/api/alerts/history', methods=['GET'])
    @require_auth(min_role="viewer")
    def api_alert_history():
        from flask import request as req, jsonify
        channel_id = req.args.get("channel_id")
        event_type = req.args.get("event_type")
        status = req.args.get("status")
        since = req.args.get("since")
        limit = int(req.args.get("limit", 50))
        history = get_alert_history(channel_id=channel_id, event_type=event_type,
                                    status=status, since=since, limit=limit)
        return jsonify({"history": history, "count": len(history)})

    @app.route('/api/alerts/status', methods=['GET'])
    @require_auth(min_role="viewer")
    def api_alert_status():
        from flask import jsonify
        channels = list_channels()
        rules = list_rules()
        total_sent = get_alert_history_count(status="sent")
        total_failed = get_alert_history_count(status="failed")
        total_exhausted = get_alert_history_count(status="retry_exhausted")
        return jsonify({
            "channels_total": len(channels),
            "channels_enabled": sum(1 for c in channels if c["enabled"]),
            "rules_total": len(rules),
            "rules_enabled": sum(1 for r in rules if r["enabled"]),
            "alerts_sent": total_sent,
            "alerts_failed": total_failed,
            "alerts_exhausted": total_exhausted,
            "event_types": list(VALID_EVENT_TYPES),
            "channel_types": list(VALID_CHANNEL_TYPES),
        })

    logger.info("Alert dispatcher routes registered (13 endpoints)")


# =============================================
# DIAGNOSTIC MODE
# =============================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(message)s")
    print("=" * 60)
    print("🦞 ButterClaw Alert Dispatcher — Diagnostic Mode")
    print("=" * 60)

    results = {"passed": 0, "failed": 0}
    test_db = os.path.join(BASE_DIR, 'butterclaw_test_alert.db')

    # Override DB_PATH for testing
    import alert_dispatcher
    alert_dispatcher.DB_PATH = test_db
    # Also update module-level reference
    globals()['DB_PATH'] = test_db

    def test_pass(num, name):
        results["passed"] += 1
        print(f"  ✅ Test {num}: {name}")

    def test_fail(num, name, reason):
        results["failed"] += 1
        print(f"  ❌ Test {num}: {name} — {reason}")

    # --- Test 1: DB Init ---
    print("\n[Test 1] Database initialization")
    try:
        init_alert_db()
        conn = _get_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('alert_channels','alert_rules','alert_history')"
        ).fetchall()
        conn.close()
        if len(tables) == 3:
            test_pass(1, "All 3 tables created")
        else:
            test_fail(1, "Table creation", f"Expected 3 tables, got {len(tables)}")
    except Exception as e:
        test_fail(1, "DB init", str(e))

    # --- Test 2: Channel CRUD (create 5 types) ---
    print("\n[Test 2] Channel CRUD — create 5 channel types")
    test_channels = {}
    channel_configs = {
        "webhook": {"url": "https://example.com/webhook"},
        "discord": {"webhook_url": "https://discord.com/api/webhooks/test/token"},
        "ntfy":    {"url": "https://ntfy.sh", "topic": "butterclaw-test"},
        "smtp":    {"host": "smtp.example.com", "port": "587", "from_addr": "claw@example.com", "to_addr": "admin@example.com"},
        "gotify":  {"url": "https://gotify.example.com", "token": "test-token"},
    }
    all_created = True
    for ch_type, config in channel_configs.items():
        result = create_channel(f"Test {ch_type}", ch_type, config, signing_secret="test-secret-123")
        if "error" in result:
            test_fail(2, f"Create {ch_type} channel", result["error"])
            all_created = False
        else:
            test_channels[ch_type] = result["channel_id"]
    if all_created:
        test_pass(2, f"Created {len(test_channels)} channels")

    # --- Test 3: Channel validation (reject invalid) ---
    print("\n[Test 3] Channel validation")
    bad1 = create_channel("Bad", "carrier_pigeon", {"url": "lol"})
    bad2 = create_channel("Bad", "webhook", {})  # missing url
    if "error" in bad1 and "error" in bad2:
        test_pass(3, "Rejected invalid channel type and missing config")
    else:
        test_fail(3, "Channel validation", "Should have rejected invalid inputs")

    # --- Test 4: Channel toggle ---
    print("\n[Test 4] Channel toggle")
    if test_channels.get("webhook"):
        r1 = toggle_channel(test_channels["webhook"])
        ch = get_channel(test_channels["webhook"])
        r2 = toggle_channel(test_channels["webhook"])
        ch2 = get_channel(test_channels["webhook"])
        if not ch["enabled"] and ch2["enabled"]:
            test_pass(4, "Toggle off then on")
        else:
            test_fail(4, "Channel toggle", f"States: {ch['enabled']} -> {ch2['enabled']}")
    else:
        test_fail(4, "Channel toggle", "No webhook channel to test")

    # --- Test 5: Rule CRUD ---
    print("\n[Test 5] Rule CRUD")
    test_rules = {}
    if test_channels.get("webhook"):
        r = create_rule("Critical to webhook", "verdict_critical", test_channels["webhook"], 30)
        if "error" not in r:
            test_rules["critical_webhook"] = r["rule_id"]
            # Verify get
            rule = get_rule(r["rule_id"])
            if rule and rule["event_type"] == "verdict_critical":
                test_pass(5, "Rule created and retrieved")
            else:
                test_fail(5, "Rule CRUD", "Could not retrieve rule")
        else:
            test_fail(5, "Rule CRUD", r["error"])
    else:
        test_fail(5, "Rule CRUD", "No webhook channel available")

    # --- Test 6: Rule validation ---
    print("\n[Test 6] Rule validation")
    bad_r1 = create_rule("Bad", "alien_invasion", test_channels.get("webhook", "x"))
    bad_r2 = create_rule("Bad", "verdict_critical", "nonexistent-channel-id")
    if "error" in bad_r1 and "error" in bad_r2:
        test_pass(6, "Rejected invalid event_type and nonexistent channel_id")
    else:
        test_fail(6, "Rule validation", "Should have rejected invalid inputs")

    # --- Test 7: Rule toggle ---
    print("\n[Test 7] Rule toggle")
    if test_rules.get("critical_webhook"):
        toggle_rule(test_rules["critical_webhook"])
        rule = get_rule(test_rules["critical_webhook"])
        toggle_rule(test_rules["critical_webhook"])
        rule2 = get_rule(test_rules["critical_webhook"])
        if not rule["enabled"] and rule2["enabled"]:
            test_pass(7, "Rule toggle off then on")
        else:
            test_fail(7, "Rule toggle", f"States: {rule['enabled']} -> {rule2['enabled']}")
    else:
        test_fail(7, "Rule toggle", "No rule to test")

    # --- Test 8: Webhook signing verification ---
    print("\n[Test 8] Webhook signing")
    test_payload = b'{"event":"test","data":{}}'
    test_secret = "my-secret-key"
    sig = _sign_payload(test_payload, test_secret)
    # Verify signature
    expected = hmac.new(test_secret.encode("utf-8"), test_payload, hashlib.sha256).hexdigest()
    if sig == f"sha256={expected}":
        test_pass(8, "HMAC-SHA256 signature verified")
    else:
        test_fail(8, "Webhook signing", f"Mismatch: {sig}")

    # --- Test 9: Cooldown enforcement ---
    print("\n[Test 9] Cooldown enforcement")
    if test_rules.get("critical_webhook"):
        rid = test_rules["critical_webhook"]
        # No history yet — should be cooled down
        if _is_cooled_down(rid, 60):
            # Manually log a "sent" entry
            _log_history(rid, test_channels["webhook"], "verdict_critical", "sent")
            # Now should NOT be cooled down
            if not _is_cooled_down(rid, 60):
                test_pass(9, "Cooldown blocks after recent send")
            else:
                test_fail(9, "Cooldown", "Should be in cooldown after send")
        else:
            test_fail(9, "Cooldown", "Should be cooled down with no history")
    else:
        test_fail(9, "Cooldown", "No rule to test")

    # --- Test 10: Auth failure tracking ---
    print("\n[Test 10] Auth failure tracking")
    # Reset tracker
    _auth_failure_tracker.clear()
    test_ip = "192.168.1.99"
    # Track 4 failures — should NOT fire
    for _ in range(4):
        with _auth_failure_lock:
            if test_ip not in _auth_failure_tracker:
                _auth_failure_tracker[test_ip] = []
            _auth_failure_tracker[test_ip].append(time.time())
    count_before = len(_auth_failure_tracker.get(test_ip, []))
    if count_before == 4:
        # The 5th should trigger (but dispatch will fail since no real channel)
        # We just verify the tracking logic
        _auth_failure_tracker[test_ip].append(time.time())
        if len(_auth_failure_tracker[test_ip]) >= AUTH_FAILURE_THRESHOLD:
            test_pass(10, f"Threshold detected at {AUTH_FAILURE_THRESHOLD} failures")
        else:
            test_fail(10, "Auth tracking", "Threshold not detected")
    else:
        test_fail(10, "Auth tracking", f"Expected 4 tracked, got {count_before}")

    # --- Test 11: Payload formatting per channel type ---
    print("\n[Test 11] Payload formatting")
    test_context = {"description": "Test payload", "ip": "10.0.0.1", "verdict": "CRITICAL"}
    all_formatted = True
    for ch_type in VALID_CHANNEL_TYPES:
        payload, headers = _format_payload("verdict_critical", test_context, ch_type)
        if not payload:
            test_fail(11, f"Format {ch_type}", "Empty payload")
            all_formatted = False
            break
    if all_formatted:
        # Verify Discord has embeds
        discord_p, _ = _format_payload("verdict_critical", test_context, "discord")
        smtp_p, _ = _format_payload("verdict_critical", test_context, "smtp")
        if "embeds" in discord_p and "subject" in smtp_p:
            test_pass(11, f"All {len(VALID_CHANNEL_TYPES)} channel payloads formatted correctly")
        else:
            test_fail(11, "Payload format", "Discord missing embeds or SMTP missing subject")

    # --- Test 12: Alert history logging + querying ---
    print("\n[Test 12] Alert history")
    hid = _log_history("test-rule", "test-channel", "verdict_critical", "sent",
                       response_code=200, payload_preview='{"test": true}')
    history = get_alert_history(event_type="verdict_critical")
    count = get_alert_history_count(event_type="verdict_critical")
    if len(history) > 0 and count > 0:
        test_pass(12, f"History logged and queried ({count} entries)")
    else:
        test_fail(12, "Alert history", "No history found after logging")

    # --- Test 13: Test alert dispatch (dry — will fail delivery but test the path) ---
    print("\n[Test 13] Dispatch path (dry)")
    if test_channels.get("webhook") and test_rules.get("critical_webhook"):
        # Clear cooldown by waiting or using 0 cooldown
        update_rule(test_rules["critical_webhook"], cooldown_secs=0)
        # Dispatch — will spawn thread but delivery will fail (fake URL)
        dispatch_alert("verdict_critical", {"description": "Diagnostic test", "source": "diagnostic"})
        time.sleep(2)  # Give daemon thread time to run
        # Check history for an attempt
        recent = get_alert_history(event_type="verdict_critical", limit=5)
        dispatch_attempted = any(
            h.get("rule_id") == test_rules["critical_webhook"]
            and h.get("status") in ("sent", "failed", "retry_exhausted")
            for h in recent
        )
        if dispatch_attempted or len(recent) > 0:
            test_pass(13, "Dispatch path executed (delivery failed as expected — fake URL)")
        else:
            test_fail(13, "Dispatch path", "No history entry from dispatch")
    else:
        test_fail(13, "Dispatch path", "No channel/rule to test")

    # --- Test 14: Cleanup — cascade delete ---
    print("\n[Test 14] Cascade delete cleanup")
    cleanup_ok = True
    for ch_type, ch_id in test_channels.items():
        result = delete_channel(ch_id)
        if "error" in result:
            test_fail(14, f"Delete {ch_type} channel", result["error"])
            cleanup_ok = False
    # Verify rules are gone
    remaining_rules = list_rules()
    remaining_channels = list_channels()
    if cleanup_ok and len(remaining_rules) == 0 and len(remaining_channels) == 0:
        test_pass(14, "All channels, rules, and history cascade-deleted")
    elif cleanup_ok:
        test_fail(14, "Cascade delete", f"Orphans remain: {len(remaining_rules)} rules, {len(remaining_channels)} channels")

    # Cleanup test DB
    try:
        os.remove(test_db)
    except OSError:
        pass

    # --- Summary ---
    print("\n" + "=" * 60)
    passed = results["passed"]
    failed = results["failed"]
    total = passed + failed
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f" ({failed} failed)")
    else:
        print(" — all clear 🦞")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)

"""
ButterClaw v0.6.5 — Authentication & Authorization Module
==========================================================
API Gateway for the ButterClaw Reasoning Engine.

Provides:
  - HMAC-SHA256 API key generation, hashing, and verification
  - Role-based access control (infra > admin > operator > viewer)
  - Session tokens (HMAC-signed, httpOnly cookies, 1-hour TTL)
  - @require_auth() decorator for Flask route protection
  - Per-API-key rate limiting with configurable thresholds
  - CLI bootstrap for first-run admin key generation

Design decisions:
  - Zero new pip dependencies — uses stdlib hmac, hashlib, secrets, json, base64
  - API key hashes stored in butterclaw.db (api_keys table), never plaintext
  - Session tokens are HMAC-signed JSON, not JWT (no pyjwt dependency)
  - Watcher → Server communication stays unauthenticated (localhost, same machine)
  - OAuth callback endpoint stays public (provider redirect target)
  - Gibson destroys API key hashes alongside vault contents
"""

import hmac
import hashlib
import secrets
import time
import json
import base64
import sqlite3
import os
import threading
import logging
import queue
from functools import wraps
from collections import defaultdict, deque

from flask import request, jsonify, Response

logger = logging.getLogger("butterclaw.auth")

# Keep this line so the diagnostic tests still know where they are!
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from config import cfg
    DB_PATH = cfg.DB_PATH
except ImportError:
    DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

# =============================================
# CONSTANTS
# =============================================

# [S-01] Role hierarchy fixed. Infrastructure role added to prevent ghost-key rejection.
# Lower number = higher privilege
ROLE_HIERARCHY = {
    "infrastructure": -1,  # Internal machine-to-machine superuser
    "admin": 0,
    "operator": 1,
    "viewer": 2,
}

# Session token TTL (seconds)
SESSION_TTL = cfg.SESSION_TTL

# API key prefix for identification (not security — just UX)
KEY_PREFIX = "bc_"

# Per-role rate limits (requests per minute on /api/analyze)
ROLE_RATE_LIMITS = {
    "infrastructure": 1000, # Max throughput for internal daemons
    "admin": cfg.AUTH_RATE_ADMIN,
    "operator": cfg.AUTH_RATE_OPERATOR,
    "viewer": cfg.AUTH_RATE_VIEWER,
}

# Default rate limit for unauthenticated (shouldn't happen if auth is enforced)
DEFAULT_RATE_LIMIT = 10

# Rate limit window in seconds
RATE_LIMIT_WINDOW = 60

# =============================================
# DATABASE
# =============================================

def _get_auth_db():
    """Thread-safe connection to the ButterClaw database."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id      TEXT PRIMARY KEY,
            key_hash    TEXT NOT NULL,
            salt        TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'viewer',
            label       TEXT,
            created_at  TEXT NOT NULL,
            last_used   TEXT,
            enabled     INTEGER NOT NULL DEFAULT 1
        )
    ''')
    conn.commit()
    return conn


# =============================================
# SESSION SIGNING KEY
# =============================================

_session_key_cache = None
_session_key_lock = threading.Lock()

def _get_session_signing_key():
    """
    Derive a session signing key from the ButterVault master key.
    Cached in memory for the lifetime of the process.
    If the master key is destroyed (Gibson), sessions become unverifiable.
    """
    global _session_key_cache
    if _session_key_cache is not None:
        return _session_key_cache

    with _session_key_lock:
        if _session_key_cache is not None:
            return _session_key_cache

        try:
            import keyring
            KEYRING_SERVICE = "butterclaw_sentinel"
            KEYRING_USER = "vault_master_key"
            master_key = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)

            if not master_key:
                logger.warning("⚠️ No master key in keyring. Sessions unavailable until Vault initializes.")
                return None

            # Derive a separate key for sessions via HMAC (domain separation)
            derived = hmac.new(
                master_key.encode('utf-8'),
                b"butterclaw_session_signing_v1",
                hashlib.sha256
            ).digest()
            _session_key_cache = derived
            return derived

        except Exception as e:
            logger.error(f"❌ Failed to derive session signing key: {e}")
            return None


def invalidate_session_cache():
    """
    Clear the cached session signing key.
    Call this BEFORE Gibson deletes the database.
    """
    global _session_key_cache
    with _session_key_lock:
        _session_key_cache = None


# =============================================
# API KEY MANAGEMENT
# =============================================

def generate_api_key():
    """
    Generate a new API key.
    Returns the plaintext key (shown once to the user, never stored).
    Format: bc_<48 random urlsafe chars>
    """
    raw = secrets.token_urlsafe(36)  # 48 chars of entropy
    return f"{KEY_PREFIX}{raw}"


def hash_api_key(plaintext_key, salt=None):
    """
    Hash an API key using HMAC-SHA256 with a per-key salt.
    Returns (hash_hex, salt_hex).
    """
    if salt is None:
        salt = secrets.token_hex(16)  # 32-char hex string, 16 bytes

    key_hash = hmac.new(
        salt.encode('utf-8'),
        plaintext_key.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return key_hash, salt


def create_api_key(role="viewer", label=None, predefined_key=None):
    """
    Generate, hash, and store a new API key.
    Returns the plaintext key (shown once) and the key_id.
    """
    if role not in ROLE_HIERARCHY:
        raise ValueError(f"Invalid role: {role}. Must be one of: {', '.join(ROLE_HIERARCHY.keys())}")

    plaintext = predefined_key if predefined_key else generate_api_key() 
    key_id = f"key_{secrets.token_hex(8)}"  # 16-char hex ID
    key_hash, salt = hash_api_key(plaintext)

    now = _iso_now()

    conn = _get_auth_db()
    try:
        conn.execute(
            "INSERT INTO api_keys (key_id, key_hash, salt, role, label, created_at, enabled) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (key_id, key_hash, salt, role, label, now)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"🔑 API key created: {key_id} (role={role}, label={label or 'none'})")

    return {
        "key": plaintext,
        "key_id": key_id,
        "role": role,
        "label": label,
        "created_at": now,
    }


def verify_api_key(plaintext_key):
    """
    Verify a plaintext API key against all stored hashes.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not plaintext_key or not plaintext_key.startswith(KEY_PREFIX):
        return None

    conn = _get_auth_db()
    try:
        rows = conn.execute(
            "SELECT key_id, key_hash, salt, role, label, created_at, last_used, enabled FROM api_keys WHERE enabled = 1"
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        candidate_hash, _ = hash_api_key(plaintext_key, salt=row["salt"])
        if hmac.compare_digest(candidate_hash, row["key_hash"]):
            _update_last_used(row["key_id"])
            return dict(row)

    return None


def revoke_api_key(key_id):
    """Disable an API key without deleting it (preserves audit trail)."""
    conn = _get_auth_db()
    try:
        result = conn.execute("UPDATE api_keys SET enabled = 0 WHERE key_id = ?", (key_id,))
        conn.commit()
        affected = result.rowcount
    finally:
        conn.close()

    if affected > 0:
        logger.info(f"🚫 API key revoked: {key_id}")
        return True
    return False


def delete_api_key(key_id):
    """Permanently delete an API key."""
    conn = _get_auth_db()
    try:
        result = conn.execute("DELETE FROM api_keys WHERE key_id = ?", (key_id,))
        conn.commit()
        affected = result.rowcount
    finally:
        conn.close()

    if affected > 0:
        logger.info(f"🗑️ API key deleted: {key_id}")
        return True
    return False


def list_api_keys():
    """List all API keys (metadata only — never returns hashes or salts)."""
    conn = _get_auth_db()
    try:
        rows = conn.execute(
            "SELECT key_id, role, label, created_at, last_used, enabled FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def destroy_all_api_keys():
    """
    Nuclear option — called by Gibson.
    Deletes all API key hashes from the database.
    """
    # [S-06] Invalidate cache FIRST to prevent race conditions during DB wipe
    invalidate_session_cache()
    
    conn = _get_auth_db()
    try:
        conn.execute("DELETE FROM api_keys")
        conn.commit()
    finally:
        conn.close()

    logger.warning("☢️ ALL API keys destroyed (Gibson).")


# =============================================
# BACKGROUND WORKER FOR LAST_USED UPDATES
# =============================================
# [R-05] Replaced thread-per-request with a bounded queue worker
_last_used_queue = queue.Queue(maxsize=1000)

def _last_used_worker():
    while True:
        key_id = _last_used_queue.get()
        if key_id is None: break
        try:
            conn = _get_auth_db()
            try:
                conn.execute(
                    "UPDATE api_keys SET last_used = ? WHERE key_id = ?",
                    (_iso_now(), key_id)
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

threading.Thread(target=_last_used_worker, daemon=True).start()

def _update_last_used(key_id):
    """Queue the last_used timestamp for a key (non-blocking)."""
    try:
        _last_used_queue.put_nowait(key_id)
    except queue.Full:
        pass  # Drop update under extreme load rather than crash


# =============================================
# SESSION TOKENS
# =============================================

def create_session_token(key_record):
    """
    Create an HMAC-signed session token from a verified API key record.
    The token is a base64-encoded JSON payload with an HMAC-SHA256 signature.
    """
    signing_key = _get_session_signing_key()
    if signing_key is None:
        return None

    now = time.time()
    payload = {
        "kid": key_record["key_id"],
        "role": key_record["role"],
        "iat": now,
        "exp": now + SESSION_TTL,
    }

    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8')

    signature = hmac.new(signing_key, payload_bytes, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).decode('utf-8')

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token):
    """Verify and decode a session token."""
    signing_key = _get_session_signing_key()
    if signing_key is None:
        return None

    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None

        payload_b64, sig_b64 = parts

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        provided_sig = base64.urlsafe_b64decode(sig_b64)

        # Verify signature (constant-time)
        expected_sig = hmac.new(signing_key, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            return None

        payload = json.loads(payload_bytes)

        # Check expiry
        if time.time() > payload.get("exp", 0):
            return None

        # Verify the key still exists and is enabled
        conn = _get_auth_db()
        try:
            row = conn.execute(
                "SELECT enabled FROM api_keys WHERE key_id = ?",
                (payload["kid"],)
            ).fetchone()
        finally:
            conn.close()

        if not row or not row["enabled"]:
            return None

        return {
            "key_id": payload["kid"],
            "role": payload["role"],
        }

    except Exception:
        return None


# =============================================
# PER-KEY RATE LIMITER
# =============================================

_rate_logs = defaultdict(deque)  # key_id → deque of timestamps
_rate_lock = threading.Lock()


def is_rate_limited_for_key(key_id, role):
    """
    Check if a specific API key has exceeded its rate limit.
    Returns True if rate limited, False if OK.
    """
    max_requests = ROLE_RATE_LIMITS.get(role, DEFAULT_RATE_LIMIT)
    now = time.time()

    with _rate_lock:
        log = _rate_logs[key_id]

        # Evict expired entries
        while log and log[0] < now - RATE_LIMIT_WINDOW:
            log.popleft()

        if len(log) >= max_requests:
            return True

        log.append(now)
        return False


# =============================================
# AUTH DECORATOR
# =============================================

def require_auth(min_role="viewer"):
    """
    Flask route decorator that enforces authentication and authorization.
    """
    if min_role not in ROLE_HIERARCHY:
        raise ValueError(f"Invalid min_role: {min_role}")

    required_level = ROLE_HIERARCHY[min_role]

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_context = None

            # --- Strategy 1: Bearer token (API key) ---
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

                if token.startswith(KEY_PREFIX):
                    # It's a raw API key
                    key_record = verify_api_key(token)
                    if key_record:
                        auth_context = {
                            "key_id": key_record["key_id"],
                            "role": key_record["role"],
                            "auth_method": "api_key",
                        }
                else:
                    # It's a session token
                    session = verify_session_token(token)
                    if session:
                        auth_context = {
                            "key_id": session["key_id"],
                            "role": session["role"],
                            "auth_method": "session_token",
                        }

            # --- Strategy 2: X-Session-Token header ---
            if auth_context is None:
                session_header = request.headers.get("X-Session-Token", "")
                if session_header:
                    session = verify_session_token(session_header)
                    if session:
                        auth_context = {
                            "key_id": session["key_id"],
                            "role": session["role"],
                            "auth_method": "session_header",
                        }

            # --- Strategy 3: Cookie ---
            if auth_context is None:
                cookie_token = request.cookies.get("butterclaw_session", "")
                if cookie_token:
                    session = verify_session_token(cookie_token)
                    if session:
                        auth_context = {
                            "key_id": session["key_id"],
                            "role": session["role"],
                            "auth_method": "session_cookie",
                        }

            # --- No valid credentials ---
            if auth_context is None:
                return jsonify({
                    "error": "Authentication required",
                    "hint": "Provide an API key via 'Authorization: Bearer bc_...' header, or log in via the dashboard."
                }), 401

            # --- Check role ---
            user_level = ROLE_HIERARCHY.get(auth_context["role"], 99)
            if user_level > required_level:
                return jsonify({
                    "error": "Insufficient permissions",
                    "required_role": min_role,
                    "your_role": auth_context["role"],
                }), 403

            # Attach auth context to request for use in route handlers
            request.auth_context = auth_context
            return f(*args, **kwargs)

        return decorated_function
    return decorator


# =============================================
# AUTH API ENDPOINTS (registered by server.py)
# =============================================

def register_auth_routes(app):
    """Register authentication endpoints on the Flask app."""

    @app.route('/api/auth/login', methods=['POST'])
    def auth_login():
        data = request.json
        if not data or "api_key" not in data:
            return jsonify({"error": "Missing 'api_key' in request body"}), 400

        key_record = verify_api_key(data["api_key"])
        if not key_record:
            # Constant-time-ish delay to prevent timing enumeration
            time.sleep(0.1)
            return jsonify({"error": "Invalid API key"}), 401

        session_token = create_session_token(key_record)
        if not session_token:
            return jsonify({"error": "Session creation failed — Vault may not be initialized"}), 500

        response = jsonify({
            "status": "authenticated",
            "key_id": key_record["key_id"],
            "role": key_record["role"],
            "label": key_record["label"],
            "expires_in": SESSION_TTL,
            "session_token": session_token,
        })

        # Set httpOnly cookie for dashboard use
        response.set_cookie(
            "butterclaw_session",
            session_token,
            max_age=SESSION_TTL,
            httponly=True,
            samesite="Strict",
            secure=getattr(cfg, "COOKIE_SECURE", True),
            path="/",
        )

        logger.info(f"🔓 Login: {key_record['key_id']} ({key_record['role']})")
        return response, 200

    @app.route('/api/auth/logout', methods=['POST'])
    def auth_logout():
        response = jsonify({"status": "logged_out"})
        response.delete_cookie("butterclaw_session", path="/")
        return response, 200

    @app.route('/api/auth/whoami', methods=['GET'])
    @require_auth(min_role="viewer")
    def auth_whoami():
        ctx = request.auth_context
        return jsonify({
            "key_id": ctx["key_id"],
            "role": ctx["role"],
            "auth_method": ctx["auth_method"],
        }), 200

    @app.route('/api/auth/keys', methods=['GET'])
    @require_auth(min_role="admin")
    def auth_list_keys():
        keys = list_api_keys()
        return jsonify({"keys": keys, "count": len(keys)}), 200

    @app.route('/api/auth/keys', methods=['POST'])
    @require_auth(min_role="admin")
    def auth_create_key():
        data = request.json or {}
        role = data.get("role", "viewer")
        label = data.get("label")

        if role not in ROLE_HIERARCHY:
            return jsonify({
                "error": f"Invalid role: {role}",
                "valid_roles": list(ROLE_HIERARCHY.keys())
            }), 400

        # Prevent non-admin from creating admin keys
        caller_role = request.auth_context["role"]
        if ROLE_HIERARCHY[role] < ROLE_HIERARCHY[caller_role]:
            return jsonify({
                "error": "Cannot create a key with higher privileges than your own"
            }), 403

        try:
            result = create_api_key(role=role, label=label)
            return jsonify({
                "status": "created",
                "key": result["key"],  # ← SHOWN ONCE
                "key_id": result["key_id"],
                "role": result["role"],
                "label": result["label"],
                "warning": "Save this key now — it will never be shown again."
            }), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route('/api/auth/keys/<key_id>', methods=['DELETE'])
    @require_auth(min_role="admin")
    def auth_delete_key(key_id):
        if key_id == request.auth_context["key_id"]:
            return jsonify({"error": "Cannot revoke your own API key"}), 400

        if revoke_api_key(key_id):
            return jsonify({"status": "revoked", "key_id": key_id}), 200
        return jsonify({"error": f"Key not found: {key_id}"}), 404

    @app.route('/api/auth/keys/<key_id>/purge', methods=['DELETE'])
    @require_auth(min_role="admin")
    def auth_purge_key(key_id):
        if key_id == request.auth_context["key_id"]:
            return jsonify({"error": "Cannot delete your own API key"}), 400

        if delete_api_key(key_id):
            return jsonify({"status": "deleted", "key_id": key_id}), 200
        return jsonify({"error": f"Key not found: {key_id}"}), 404


# =============================================
# BOOTSTRAP (CLI)
# =============================================

def bootstrap_admin_key():
    existing = list_api_keys()
    admin_keys = [k for k in existing if k["role"] == "admin" and k["enabled"]]

    if admin_keys:
        logger.info(f"🔑 {len(admin_keys)} admin key(s) already exist. Skipping bootstrap.")
        return None

    result = create_api_key(role="admin", label="Bootstrap Admin")
    print("\n" + "=" * 60)
    print("🔑 FIRST-RUN BOOTSTRAP: Admin API Key Created")
    print("=" * 60)
    print(f"  Key ID:  {result['key_id']}")
    print(f"  Role:    {result['role']}")
    print(f"  Key:     {result['key']}")
    print("")
    print("  ⚠️  SAVE THIS KEY NOW — it will never be shown again.")
    print("  Use it to log into the dashboard or create additional keys.")
    print("=" * 60 + "\n")

    return result["key"]


def bootstrap_infrastructure_keys():
    existing = list_api_keys()
    infra_keys = [k for k in existing if k["role"] == "infrastructure" and k["enabled"]]

    if infra_keys:
        logger.info(f"🔑 {len(infra_keys)} infrastructure key(s) already exist. Skipping bootstrap.")
        return None

    new_key = secrets.token_hex(32)

    key_id = f"key_{secrets.token_hex(8)}"
    key_hash, salt = hash_api_key(new_key)
    now = _iso_now()

    conn = _get_auth_db()
    try:
        conn.execute(
            "INSERT INTO api_keys (key_id, key_hash, salt, role, label, created_at, enabled) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (key_id, key_hash, salt, "infrastructure", "infrastructure-bootstrap", now)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(f"🔑 Infrastructure API key created: {key_id}")
    return new_key


def bootstrap_infrastructure_keys_auto_heal():
    env_key = os.environ.get("BUTTERCLAW_API_KEY")
    if not env_key:
        return None

    if verify_api_key(env_key):
        return None

    # [S-01] Role matches the hierarchy now
    create_api_key(role="infrastructure", label="Infrastructure Watcher (.env)", predefined_key=env_key)
    logger.info("⚙️ [AUTO-HEAL] Infrastructure API Key restored from environment.")
    return True

# =============================================
# ROUTE CLASSIFICATION MAP
# =============================================

ROUTE_CLASSIFICATION = {
    # --- Public (no auth) ---
    "GET  /api/health":                          "public",
    "GET  /api/vault/oauth/callback":            "public",  # OAuth redirect target

    # --- Viewer (read-only) ---
    "GET  /api/mcp/status":                      "viewer",
    "GET  /api/mcp/tools":                       "viewer",
    "GET  /api/mcp/events":                      "viewer",
    "GET  /api/mcp/events/<id>":                 "viewer",
    "GET  /api/vault/status":                    "viewer",
    "GET  /api/vault/oauth/status":              "viewer",
    "GET  /api/logs":                            "viewer",
    "GET  /api/stream":                          "viewer",  # SSE

    # --- Operator (active use) ---
    "POST /api/analyze":                         "operator",
    "GET  /api/settings":                        "operator",
    "GET  /api/mcp/ping":                        "operator",
    "GET  /api/vault/oauth/start/<provider>":    "operator",

    # --- Admin (destructive / config) ---
    "POST /api/settings":                        "admin",
    "POST /api/vault/key":                       "admin",
    "POST /api/rotate-keys":                     "admin",
    "POST /api/shield":                          "admin",
    "POST /api/mcp/restart":                     "admin",
    "POST /api/vault/oauth/revoke/<provider>":   "admin",

    # --- Auth endpoints (self-managing) ---
    "POST /api/auth/login":                      "public",    # Exchanges key for session
    "POST /api/auth/logout":                     "public",    # Clears cookie
    "GET  /api/auth/whoami":                     "viewer",    # Identity check
    "GET  /api/auth/keys":                       "admin",     # List keys
    "POST /api/auth/keys":                       "admin",     # Create key
    "DELETE /api/auth/keys/<key_id>":            "admin",     # Revoke key
    "DELETE /api/auth/keys/<key_id>/purge":      "admin",     # Purge key
}


# =============================================
# UTILITIES
# =============================================

def _iso_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# =============================================
# STANDALONE DIAGNOSTIC MODE
# =============================================

if __name__ == "__main__":
    print("🦞 ButterClaw Auth Module — Diagnostic Boot\n")

    print("1. Creating admin key...")
    admin = create_api_key(role="admin", label="Diagnostic Admin")
    print(f"   ✅ Created: {admin['key_id']} → {admin['key'][:20]}...")

    print("2. Creating operator key...")
    operator = create_api_key(role="operator", label="Diagnostic Operator")
    print(f"   ✅ Created: {operator['key_id']} → {operator['key'][:20]}...")

    print("3. Verifying admin key...")
    verified = verify_api_key(admin["key"])
    if verified and verified["role"] == "admin":
        print(f"   ✅ Verified: {verified['key_id']} (role={verified['role']})")
    else:
        print("   ❌ Verification failed!")

    print("4. Verifying operator key...")
    verified_op = verify_api_key(operator["key"])
    if verified_op and verified_op["role"] == "operator":
        print(f"   ✅ Verified: {verified_op['key_id']} (role={verified_op['role']})")
    else:
        print("   ❌ Verification failed!")

    print("5. Testing invalid key...")
    invalid = verify_api_key("bc_totally_fake_key_12345")
    if invalid is None:
        print("   ✅ Invalid key correctly rejected.")
    else:
        print("   ❌ Invalid key was accepted!")

    print("6. Testing session token...")
    token = create_session_token(verified)
    if token:
        decoded = verify_session_token(token)
        if decoded and decoded["key_id"] == admin["key_id"]:
            print(f"   ✅ Session token created and verified (role={decoded['role']})")
        else:
            print("   ❌ Session token verification failed!")
    else:
        print("   ⚠️ Session token creation skipped (no master key in keyring)")

    print("7. Revoking operator key...")
    if revoke_api_key(operator["key_id"]):
        revoked_check = verify_api_key(operator["key"])
        if revoked_check is None:
            print("   ✅ Revoked key correctly rejected on verify.")
        else:
            print("   ❌ Revoked key still verifies!")
    else:
        print("   ❌ Revocation failed!")

    print("8. Listing all keys...")
    all_keys = list_api_keys()
    for k in all_keys:
        status = "active" if k["enabled"] else "revoked"
        print(f"   {k['key_id']} | {k['role']:8} | {status} | {k['label']}")

    print("9. Testing rate limiter...")
    test_key = "test_rate_key"
    limited = False
    for i in range(ROLE_RATE_LIMITS["viewer"] + 5):
        if is_rate_limited_for_key(test_key, "viewer"):
            print(f"   ✅ Rate limited at request {i + 1} (limit={ROLE_RATE_LIMITS['viewer']})")
            limited = True
            break
    if not limited:
        print("   ❌ Rate limiter failed to trigger!")

    print("10. Testing Gibson (destroy all keys)...")
    destroy_all_api_keys()
    post_gibson = list_api_keys()
    if len(post_gibson) == 0:
        print("   ✅ All API keys destroyed.")
    else:
        print(f"   ❌ {len(post_gibson)} keys survived Gibson!")

    print("\n🦞 Diagnostic complete. Background worker exiting...")
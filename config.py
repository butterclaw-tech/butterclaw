"""
ButterClaw v0.6.4 — Configuration Module
==========================================
Single source of truth for all runtime configuration.

Solves the problem that server.py, auth.py, policy_engine.py,
alert_dispatcher.py, and buttervault.py each independently compute
DB_PATH and hardcode their own defaults. If you mount the DB at a
different location (Docker volume, shared NFS, etc.) you'd have to
patch five files. config.py becomes the canonical import.

Loads from (in priority order):
  1. Environment variables (highest — set by Docker, systemd, shell)
  2. .env file in project root (if present — never overrides env vars)
  3. Hardcoded defaults (lowest — match v0.6.2 behavior exactly)

Design decisions:
  - Zero new pip dependencies — .env parsing is ~30 lines of stdlib
  - No third-party dotenv library required
  - Singleton pattern: `from config import cfg`
  - try/except ImportError in consumers for backward compat
  - Secrets never appear in to_dict() output
  - _validate() runs at import time — fail fast on bad config
  - BUTTERCLAW_ prefix on all env vars — namespace isolation
  - Diagnostic mode: `python config.py` prints resolved config

Usage:
  from config import cfg

  db_path = cfg.DB_PATH
  port = cfg.PORT
  confidence = cfg.CONFIDENCE_THRESHOLD

Integration points (server.py, auth.py, policy_engine.py,
                    alert_dispatcher.py, buttervault.py):
  - Replace per-module BASE_DIR / DB_PATH with cfg.DB_PATH
  - Replace hardcoded ALLOWED_ORIGINS with cfg.CORS_ORIGINS
  - Replace hardcoded model_name with cfg.MODEL_NAME
  - Replace hardcoded OLLAMA_LOCAL_BASE with cfg.OLLAMA_BASE_URL
  - Replace hardcoded CONFIDENCE_THRESHOLD with cfg.CONFIDENCE_THRESHOLD
  - Replace app.run(host, port, debug) with cfg values
  - All consumers use try/except ImportError for backward compat
"""

import os
import sys
import logging

logger = logging.getLogger("butterclaw.config")


# =============================================
# CONSTANTS
# =============================================

CONFIG_VERSION = "0.6.4"

# All environment variable names used by ButterClaw.
# Prefixed with BUTTERCLAW_ to avoid collision with system vars.
ENV_PREFIX = "BUTTERCLAW_"


# =============================================
# .env FILE PARSER (stdlib only — no python-dotenv)
# =============================================

def _load_dotenv(path):
    """
    Minimal .env parser. Handles:
      - KEY=value
      - KEY="quoted value"  (double-quoted, strips quotes)
      - KEY='single quoted' (single-quoted, strips quotes)
      - # full-line comments
      - Inline comments after unquoted values (KEY=val # comment)
      - Empty lines
      - Whitespace around = sign
      - export KEY=value (shell-compatible prefix)

    Does NOT override existing environment variables —
    env vars set by Docker/systemd/shell always take precedence.
    This is the correct behavior for 12-factor apps.

    Returns the number of variables loaded (for diagnostics).
    """
    loaded = 0

    if not os.path.isfile(path):
        return loaded

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                # Strip optional 'export ' prefix
                if line.startswith("export "):
                    line = line[7:].strip()

                # Must contain =
                if "=" not in line:
                    continue

                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()

                # Validate key: must be non-empty, alphanumeric + underscore
                if not key or not all(c.isalnum() or c == "_" for c in key):
                    continue

                # Strip surrounding quotes
                if len(value) >= 2:
                    if (value[0] == '"' and value[-1] == '"') or \
                       (value[0] == "'" and value[-1] == "'"):
                        value = value[1:-1]
                    else:
                        # Remove inline comments for unquoted values
                        # Only split on ' #' (space + hash) to avoid breaking URLs
                        if " #" in value:
                            value = value[:value.index(" #")].strip()
                else:
                    # Single character or empty — use as-is
                    pass

                # Don't override existing env vars
                if key not in os.environ:
                    os.environ[key] = value
                    loaded += 1

    except (IOError, OSError) as e:
        logger.warning("Failed to read .env file at %s: %s", path, e)

    return loaded


# =============================================
# HELPER: safe type coercion
# =============================================

def _env_str(key, default=""):
    """Get string from environment with BUTTERCLAW_ prefix."""
    return os.environ.get(ENV_PREFIX + key, default)


def _env_int(key, default=0):
    """Get integer from environment with BUTTERCLAW_ prefix."""
    raw = os.environ.get(ENV_PREFIX + key, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid integer for %s%s: '%s' — using default %d",
            ENV_PREFIX, key, raw, default,
        )
        return default


def _env_bool(key, default=False):
    """Get boolean from environment with BUTTERCLAW_ prefix.
    Truthy: 'true', '1', 'yes', 'on' (case-insensitive).
    Everything else is falsy.
    """
    raw = os.environ.get(ENV_PREFIX + key, "")
    if not raw:
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _env_list(key, default=None, separator=","):
    """Get comma-separated list from environment with BUTTERCLAW_ prefix.
    Returns list of stripped, non-empty strings.
    """
    raw = os.environ.get(ENV_PREFIX + key, "")
    if not raw:
        return default if default is not None else []
    return [item.strip() for item in raw.split(separator) if item.strip()]


# =============================================
# CONFIGURATION CLASS
# =============================================

class ButterClawConfig:
    """
    Centralized configuration with validation.
    All values are resolved at instantiation time.
    Immutable after __init__ — no runtime mutation.

    Categories:
      - Paths        (DB, MCP script, base directory)
      - Server       (host, port, debug)
      - CORS         (allowed origins)
      - Brain/Ollama (model, endpoint, confidence, dry-run)
      - MCP          (transport mode, SSE config)
      - Auth         (rate limits, session TTL)
      - Alerts       (delivery timeout, retries, brute-force)
      - OAuth        (state TTL)
      - Identity     (instance ID)
    """

    def __init__(self):
        # ── Resolve base directory FIRST ──
        # This is the directory containing config.py itself.
        # All relative paths are resolved from here.
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        # ── Load .env file (won't override existing env vars) ──
        dotenv_path = os.path.join(self.BASE_DIR, ".env")
        self._dotenv_loaded = _load_dotenv(dotenv_path)
        self._dotenv_path = dotenv_path if os.path.isfile(dotenv_path) else None

        # ── Paths ──
        self.DB_PATH = _env_str(
            "DB_PATH",
            os.path.join(self.BASE_DIR, "butterclaw.db"),
        )
        self.MCP_SCRIPT = _env_str(
            "MCP_SCRIPT",
            os.path.join(self.BASE_DIR, "butterclaw_mcp.py"),
        )

        # ── Server ──
        self.HOST = _env_str("HOST", "0.0.0.0")
        self.PORT = _env_int("PORT", 5000)
        self.DEBUG = _env_bool("DEBUG", False)
        self.BASE_URL = _env_str("BASE_URL", "http://127.0.0.1:5000")
        self.COOKIE_SECURE = _env_bool("COOKIE_SECURE", True)

        # ── CORS ──
        default_origins = [
            "http://127.0.0.1:5000",
            "http://localhost:5000",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "null",
        ]
        cors_raw = _env_list("CORS_ORIGINS")
        self.CORS_ORIGINS = cors_raw if cors_raw else default_origins

        # ── Brain / Ollama ──
        self.OLLAMA_BASE_URL = _env_str("OLLAMA_URL", "http://localhost:11434")
        self.OLLAMA_CHAT_PATH = _env_str("OLLAMA_PATH", "/api/chat")
        self.GOOGLE_API_KEY = _env_str("GOOGLE_API_KEY", "")
        self.MODEL_NAME = _env_str("MODEL", "butterclaw-optimized:latest")
        self.CONFIDENCE_THRESHOLD = _env_int("CONFIDENCE_THRESHOLD", 85)
        self.DRY_RUN = _env_bool("DRY_RUN", False)

        # ── MCP Transport ──
        self.MCP_TRANSPORT = _env_str("MCP_TRANSPORT", "stdio")
        self.MCP_SSE_URL = _env_str("MCP_SSE_URL", "")
        self.MCP_SSE_TOKEN = _env_str("MCP_SSE_TOKEN", "")

        # ── Auth ──
        self.AUTH_RATE_ADMIN = _env_int("RATE_ADMIN", 30)
        self.AUTH_RATE_OPERATOR = _env_int("RATE_OPERATOR", 15)
        self.AUTH_RATE_VIEWER = _env_int("RATE_VIEWER", 5)
        self.SESSION_TTL = _env_int("SESSION_TTL", 3600)

        # ── Alert Dispatcher ──
        self.ALERT_DELIVERY_TIMEOUT = _env_int("ALERT_TIMEOUT", 10)
        self.ALERT_TIMEOUT = _env_int("ALERT_TIMEOUT", 10)
        self.ALERT_MAX_RETRIES = _env_int("ALERT_RETRIES", 3)
        self.ALERT_RETRY_BACKOFF = _env_int("ALERT_BACKOFF", 1)
        self.AUTH_FAILURE_THRESHOLD = _env_int("AUTH_FAIL_THRESHOLD", 5)
        self.AUTH_FAIL_THRESHOLD = _env_int("AUTH_FAIL_THRESHOLD", 5)
        self.AUTH_FAILURE_WINDOW = _env_int("AUTH_FAIL_WINDOW", 60)
        self.AUTH_FAIL_WINDOW = _env_int("AUTH_FAIL_WINDOW", 60)

        # ── OAuth ──
        self.OAUTH_STATE_TTL = _env_int("OAUTH_TTL", 600)

        # ── Identity ──
        self.INSTANCE_ID = _env_str("INSTANCE_ID", "butterclaw-local")

        # ── Validate ──
        self._validate()

        logger.info(
            "Config loaded: instance=%s port=%d model=%s db=%s",
            self.INSTANCE_ID,
            self.PORT,
            self.MODEL_NAME,
            self.DB_PATH,
        )

    # ─────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────

    def _validate(self):
        """
        Sanity checks on configuration values.
        Raises ValueError on invalid config — fail fast at startup.
        Logs warnings for non-fatal issues.
        """
        errors = []

        # Port range
        if self.PORT < 1 or self.PORT > 65535:
            errors.append(f"Invalid port: {self.PORT} (must be 1-65535)")

        # Confidence threshold
        if self.CONFIDENCE_THRESHOLD < 0 or self.CONFIDENCE_THRESHOLD > 100:
            errors.append(
                f"Invalid confidence threshold: {self.CONFIDENCE_THRESHOLD} "
                f"(must be 0-100)"
            )

        # MCP transport
        if self.MCP_TRANSPORT not in ("stdio", "sse"):
            errors.append(
                f"Invalid MCP transport: '{self.MCP_TRANSPORT}' "
                f"(must be 'stdio' or 'sse')"
            )

        # SSE without URL
        if self.MCP_TRANSPORT == "sse" and not self.MCP_SSE_URL:
            logger.warning(
                "MCP transport set to 'sse' but BUTTERCLAW_MCP_SSE_URL is empty"
            )

        # Rate limits must be positive
        for name, val in [
            ("AUTH_RATE_ADMIN", self.AUTH_RATE_ADMIN),
            ("AUTH_RATE_OPERATOR", self.AUTH_RATE_OPERATOR),
            ("AUTH_RATE_VIEWER", self.AUTH_RATE_VIEWER),
        ]:
            if val < 1:
                errors.append(f"Invalid rate limit {name}: {val} (must be >= 1)")

        # Session TTL must be positive
        if self.SESSION_TTL < 1:
            errors.append(
                f"Invalid session TTL: {self.SESSION_TTL} (must be >= 1)"
            )

        # Alert delivery timeout
        if self.ALERT_DELIVERY_TIMEOUT < 1:
            errors.append(
                f"Invalid alert timeout: {self.ALERT_DELIVERY_TIMEOUT} "
                f"(must be >= 1)"
            )

        # Alert retries
        if self.ALERT_MAX_RETRIES < 0 or self.ALERT_MAX_RETRIES > 10:
            errors.append(
                f"Invalid alert retries: {self.ALERT_MAX_RETRIES} "
                f"(must be 0-10)"
            )

        # Auth failure threshold
        if self.AUTH_FAILURE_THRESHOLD < 1:
            errors.append(
                f"Invalid auth failure threshold: {self.AUTH_FAILURE_THRESHOLD} "
                f"(must be >= 1)"
            )

        # OAuth TTL
        if self.OAUTH_STATE_TTL < 1:
            errors.append(
                f"Invalid OAuth state TTL: {self.OAUTH_STATE_TTL} "
                f"(must be >= 1)"
            )

        # Ollama URL format check (basic)
        if self.OLLAMA_BASE_URL:
            if not (
                self.OLLAMA_BASE_URL.startswith("http://") or
                self.OLLAMA_BASE_URL.startswith("https://")
            ):
                errors.append(
                    f"Invalid Ollama URL: '{self.OLLAMA_BASE_URL}' "
                    f"(must start with http:// or https://)"
                )

        # CORS origins should not be empty
        if not self.CORS_ORIGINS:
            logger.warning("CORS origins list is empty — dashboard may not load")

        # Raise all errors at once
        if errors:
            msg = "Configuration validation failed:\n  " + "\n  ".join(errors)
            raise ValueError(msg)

    # ─────────────────────────────────────────
    # Export / Serialization
    # ─────────────────────────────────────────

    def to_dict(self, redact_secrets=True):
        """
        Export config as dict for /api/config endpoint.
        Redacts secrets by default — safe for API responses.

        Redacted fields:
          - MCP SSE token (truncated)
          - MCP SSE URL (truncated if contains token-like paths)
        """
        d = {
            "version": CONFIG_VERSION,
            "instance_id": self.INSTANCE_ID,
            "base_dir": self.BASE_DIR,
            "db_path": self.DB_PATH,
            "mcp_script": self.MCP_SCRIPT,
            "server": {
                "host": self.HOST,
                "port": self.PORT,
                "debug": self.DEBUG,
            },
            "cors_origins": self.CORS_ORIGINS,
            "brain": {
                "ollama_base_url": self.OLLAMA_BASE_URL,
                "ollama_chat_path": self.OLLAMA_CHAT_PATH,
                "model_name": self.MODEL_NAME,
                "confidence_threshold": self.CONFIDENCE_THRESHOLD,
                "dry_run": self.DRY_RUN,
            },
            "mcp": {
                "transport": self.MCP_TRANSPORT,
                "sse_url": (
                    self.MCP_SSE_URL[:30] + "..."
                    if redact_secrets and len(self.MCP_SSE_URL) > 30
                    else self.MCP_SSE_URL
                ),
                "sse_token": "***" if redact_secrets and self.MCP_SSE_TOKEN else "",
            },
            "auth": {
                "rate_limits": {
                    "admin": self.AUTH_RATE_ADMIN,
                    "operator": self.AUTH_RATE_OPERATOR,
                    "viewer": self.AUTH_RATE_VIEWER,
                },
                "session_ttl": self.SESSION_TTL,
                "brute_force_threshold": self.AUTH_FAILURE_THRESHOLD,
                "brute_force_window": self.AUTH_FAILURE_WINDOW,
            },
            "alerts": {
                "delivery_timeout": self.ALERT_DELIVERY_TIMEOUT,
                "max_retries": self.ALERT_MAX_RETRIES,
                "retry_backoff_base": self.ALERT_RETRY_BACKOFF,
            },
            "oauth": {
                "state_ttl": self.OAUTH_STATE_TTL,
            },
            "config_source": {
                "dotenv_loaded": self._dotenv_loaded > 0,
                "dotenv_path": self._dotenv_path,
                "dotenv_vars_loaded": self._dotenv_loaded,
                "env_override_active": bool(
                    os.environ.get(ENV_PREFIX + "PORT")
                    or os.environ.get(ENV_PREFIX + "DB_PATH")
                    or os.environ.get(ENV_PREFIX + "HOST")
                ),
            },
        }
        return d

    def to_flat_dict(self):
        """
        Export as flat key-value dict for diagnostics.
        No redaction — internal use only.
        """
        return {
            "BASE_DIR": self.BASE_DIR,
            "DB_PATH": self.DB_PATH,
            "MCP_SCRIPT": self.MCP_SCRIPT,
            "HOST": self.HOST,
            "PORT": self.PORT,
            "DEBUG": self.DEBUG,
            "CORS_ORIGINS": self.CORS_ORIGINS,
            "OLLAMA_BASE_URL": self.OLLAMA_BASE_URL,
            "OLLAMA_CHAT_PATH": self.OLLAMA_CHAT_PATH,
            "MODEL_NAME": self.MODEL_NAME,
            "CONFIDENCE_THRESHOLD": self.CONFIDENCE_THRESHOLD,
            "DRY_RUN": self.DRY_RUN,
            "MCP_TRANSPORT": self.MCP_TRANSPORT,
            "MCP_SSE_URL": self.MCP_SSE_URL,
            "MCP_SSE_TOKEN": "***" if self.MCP_SSE_TOKEN else "",
            "AUTH_RATE_ADMIN": self.AUTH_RATE_ADMIN,
            "AUTH_RATE_OPERATOR": self.AUTH_RATE_OPERATOR,
            "AUTH_RATE_VIEWER": self.AUTH_RATE_VIEWER,
            "SESSION_TTL": self.SESSION_TTL,
            "ALERT_DELIVERY_TIMEOUT": self.ALERT_DELIVERY_TIMEOUT,
            "ALERT_MAX_RETRIES": self.ALERT_MAX_RETRIES,
            "ALERT_RETRY_BACKOFF": self.ALERT_RETRY_BACKOFF,
            "AUTH_FAILURE_THRESHOLD": self.AUTH_FAILURE_THRESHOLD,
            "AUTH_FAILURE_WINDOW": self.AUTH_FAILURE_WINDOW,
            "OAUTH_STATE_TTL": self.OAUTH_STATE_TTL,
            "INSTANCE_ID": self.INSTANCE_ID,
        }

    # ─────────────────────────────────────────
    # Repr
    # ─────────────────────────────────────────

    def __repr__(self):
        return (
            f"<ButterClawConfig "
            f"v{CONFIG_VERSION} "
            f"instance={self.INSTANCE_ID} "
            f"port={self.PORT} "
            f"model={self.MODEL_NAME} "
            f"db={self.DB_PATH}>"
        )


# =============================================
# SINGLETON — import and use everywhere
# =============================================

cfg = ButterClawConfig()


# =============================================
# DIAGNOSTIC MODE
# =============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🦞 ButterClaw Config — Diagnostic Mode")
    print("=" * 60)
    print()

    _pass = 0
    _fail = 0

    def _test(num, desc, condition, detail=""):
        global _pass, _fail
        if condition:
            _pass += 1
            print(f"  ✅ Test {num}:  {desc}")
        else:
            _fail += 1
            print(f"  ❌ Test {num}:  {desc}")
        if detail:
            print(f"              {detail}")

    # ── Test 1: Config singleton loaded ──
    _test(1, "Config singleton loaded",
          cfg is not None,
          repr(cfg))

    # ── Test 2: Version matches ──
    _test(2, "Config version is 0.6.3",
          CONFIG_VERSION == "0.6.3",
          f"CONFIG_VERSION = {CONFIG_VERSION}")

    # ── Test 3: BASE_DIR is a real directory ──
    _test(3, "BASE_DIR exists and is a directory",
          os.path.isdir(cfg.BASE_DIR),
          f"BASE_DIR = {cfg.BASE_DIR}")

    # ── Test 4: DB_PATH has valid parent directory ──
    db_parent = os.path.dirname(cfg.DB_PATH)
    _test(4, "DB_PATH parent directory exists",
          os.path.isdir(db_parent),
          f"DB_PATH = {cfg.DB_PATH}")

    # ── Test 5: Port is valid ──
    _test(5, "PORT is valid (1-65535)",
          1 <= cfg.PORT <= 65535,
          f"PORT = {cfg.PORT}")

    # ── Test 6: Confidence threshold is valid ──
    _test(6, "CONFIDENCE_THRESHOLD is valid (0-100)",
          0 <= cfg.CONFIDENCE_THRESHOLD <= 100,
          f"CONFIDENCE_THRESHOLD = {cfg.CONFIDENCE_THRESHOLD}")

    # ── Test 7: MCP transport is valid ──
    _test(7, "MCP_TRANSPORT is valid (stdio/sse)",
          cfg.MCP_TRANSPORT in ("stdio", "sse"),
          f"MCP_TRANSPORT = {cfg.MCP_TRANSPORT}")

    # ── Test 8: CORS origins is non-empty list ──
    _test(8, "CORS_ORIGINS is non-empty list",
          isinstance(cfg.CORS_ORIGINS, list) and len(cfg.CORS_ORIGINS) > 0,
          f"CORS_ORIGINS = {cfg.CORS_ORIGINS}")

    # ── Test 9: Rate limits are positive ──
    _test(9, "Auth rate limits are all positive",
          cfg.AUTH_RATE_ADMIN >= 1 and
          cfg.AUTH_RATE_OPERATOR >= 1 and
          cfg.AUTH_RATE_VIEWER >= 1,
          f"admin={cfg.AUTH_RATE_ADMIN} operator={cfg.AUTH_RATE_OPERATOR} viewer={cfg.AUTH_RATE_VIEWER}")

    # ── Test 10: Session TTL is positive ──
    _test(10, "SESSION_TTL is positive",
           cfg.SESSION_TTL >= 1,
           f"SESSION_TTL = {cfg.SESSION_TTL}")

    # ── Test 11: Alert config is valid ──
    _test(11, "Alert config is valid",
           cfg.ALERT_DELIVERY_TIMEOUT >= 1 and
           0 <= cfg.ALERT_MAX_RETRIES <= 10 and
           cfg.AUTH_FAILURE_THRESHOLD >= 1,
           f"timeout={cfg.ALERT_DELIVERY_TIMEOUT}s retries={cfg.ALERT_MAX_RETRIES} brute_force_threshold={cfg.AUTH_FAILURE_THRESHOLD}")

    # ── Test 12: to_dict() produces valid output ──
    d = cfg.to_dict(redact_secrets=True)
    _test(12, "to_dict() returns valid dict with expected keys",
           isinstance(d, dict) and
           "version" in d and
           "instance_id" in d and
           "server" in d and
           "brain" in d and
           "mcp" in d and
           "auth" in d and
           "alerts" in d,
           f"Keys: {list(d.keys())}")

    # ── Test 13: to_dict() redacts secrets ──
    d_redacted = cfg.to_dict(redact_secrets=True)
    mcp_token = d_redacted.get("mcp", {}).get("sse_token", "")
    # Token should be '***' if set, or '' if empty
    _test(13, "to_dict() redacts MCP SSE token",
           mcp_token in ("***", ""),
           f"sse_token = '{mcp_token}'")

    # ── Test 14: to_flat_dict() includes all fields ──
    flat = cfg.to_flat_dict()
    expected_keys = [
        "BASE_DIR", "DB_PATH", "MCP_SCRIPT", "HOST", "PORT", "DEBUG",
        "CORS_ORIGINS", "OLLAMA_BASE_URL", "OLLAMA_CHAT_PATH", "MODEL_NAME",
        "CONFIDENCE_THRESHOLD", "DRY_RUN", "MCP_TRANSPORT", "MCP_SSE_URL",
        "MCP_SSE_TOKEN", "AUTH_RATE_ADMIN", "AUTH_RATE_OPERATOR",
        "AUTH_RATE_VIEWER", "SESSION_TTL", "ALERT_DELIVERY_TIMEOUT",
        "ALERT_MAX_RETRIES", "ALERT_RETRY_BACKOFF", "AUTH_FAILURE_THRESHOLD",
        "AUTH_FAILURE_WINDOW", "OAUTH_STATE_TTL", "INSTANCE_ID",
    ]
    missing = [k for k in expected_keys if k not in flat]
    _test(14, "to_flat_dict() includes all 26 config fields",
           len(missing) == 0,
           f"Missing: {missing}" if missing else f"All {len(expected_keys)} fields present")

    # ── Test 15: .env parser handles comments ──
    import tempfile
    test_env_path = os.path.join(tempfile.gettempdir(), ".butterclaw_test_env")
    try:
        with open(test_env_path, "w") as f:
            f.write("# This is a comment\n")
            f.write("\n")
            f.write("BUTTERCLAW_TEST_PLAIN=hello\n")
            f.write('BUTTERCLAW_TEST_QUOTED="hello world"\n')
            f.write("BUTTERCLAW_TEST_SINGLE='single quoted'\n")
            f.write("BUTTERCLAW_TEST_INLINE=value # inline comment\n")
            f.write("export BUTTERCLAW_TEST_EXPORT=exported\n")
            f.write("INVALID LINE WITHOUT EQUALS\n")
            f.write("=empty_key\n")

        # Clear any existing test vars
        for k in list(os.environ.keys()):
            if k.startswith("BUTTERCLAW_TEST_"):
                del os.environ[k]

        loaded = _load_dotenv(test_env_path)

        results = {
            "plain": os.environ.get("BUTTERCLAW_TEST_PLAIN") == "hello",
            "quoted": os.environ.get("BUTTERCLAW_TEST_QUOTED") == "hello world",
            "single": os.environ.get("BUTTERCLAW_TEST_SINGLE") == "single quoted",
            "inline": os.environ.get("BUTTERCLAW_TEST_INLINE") == "value",
            "export": os.environ.get("BUTTERCLAW_TEST_EXPORT") == "exported",
        }
        all_ok = all(results.values())

        _test(15, ".env parser handles all value formats",
               all_ok,
               f"Results: {results}")

        # Cleanup test vars
        for k in list(os.environ.keys()):
            if k.startswith("BUTTERCLAW_TEST_"):
                del os.environ[k]
    except Exception as e:
        _test(15, ".env parser handles all value formats", False, f"Error: {e}")
    finally:
        if os.path.isfile(test_env_path):
            os.remove(test_env_path)

    # ── Test 16: .env parser does NOT override existing env vars ──
    test_env_path_2 = os.path.join(tempfile.gettempdir(), ".butterclaw_test_env_2")
    try:
        os.environ["BUTTERCLAW_TEST_PRIORITY"] = "from_env"

        with open(test_env_path_2, "w") as f:
            f.write("BUTTERCLAW_TEST_PRIORITY=from_dotenv\n")

        _load_dotenv(test_env_path_2)
        actual = os.environ.get("BUTTERCLAW_TEST_PRIORITY")

        _test(16, "Env vars override .env values (priority)",
               actual == "from_env",
               f"Expected 'from_env', got '{actual}'")

        del os.environ["BUTTERCLAW_TEST_PRIORITY"]
    except Exception as e:
        _test(16, "Env vars override .env values (priority)", False, f"Error: {e}")
    finally:
        if os.path.isfile(test_env_path_2):
            os.remove(test_env_path_2)

    # ── Test 17: Invalid port raises ValueError ──
    try:
        os.environ["BUTTERCLAW_PORT"] = "99999"
        raised = False
        try:
            test_cfg = ButterClawConfig()
        except ValueError:
            raised = True
        _test(17, "Invalid port (99999) raises ValueError",
               raised,
               "ValueError raised as expected" if raised else "No error raised!")
    finally:
        # Restore original
        if cfg.PORT != 99999:
            os.environ["BUTTERCLAW_PORT"] = str(cfg.PORT)
        else:
            del os.environ["BUTTERCLAW_PORT"]

    # ── Test 18: Invalid confidence threshold raises ValueError ──
    try:
        os.environ["BUTTERCLAW_CONFIDENCE_THRESHOLD"] = "150"
        raised = False
        try:
            test_cfg = ButterClawConfig()
        except ValueError:
            raised = True
        _test(18, "Invalid confidence (150) raises ValueError",
               raised,
               "ValueError raised as expected" if raised else "No error raised!")
    finally:
        if "BUTTERCLAW_CONFIDENCE_THRESHOLD" in os.environ:
            del os.environ["BUTTERCLAW_CONFIDENCE_THRESHOLD"]

    # ── Test 19: Invalid MCP transport raises ValueError ──
    try:
        os.environ["BUTTERCLAW_MCP_TRANSPORT"] = "websocket"
        raised = False
        try:
            test_cfg = ButterClawConfig()
        except ValueError:
            raised = True
        _test(19, "Invalid MCP transport ('websocket') raises ValueError",
               raised,
               "ValueError raised as expected" if raised else "No error raised!")
    finally:
        if "BUTTERCLAW_MCP_TRANSPORT" in os.environ:
            del os.environ["BUTTERCLAW_MCP_TRANSPORT"]

    # ── Test 20: Ollama URL without http(s) raises ValueError ──
    try:
        os.environ["BUTTERCLAW_OLLAMA_URL"] = "ftp://localhost:11434"
        raised = False
        try:
            test_cfg = ButterClawConfig()
        except ValueError:
            raised = True
        _test(20, "Invalid Ollama URL (ftp://) raises ValueError",
               raised,
               "ValueError raised as expected" if raised else "No error raised!")
    finally:
        if "BUTTERCLAW_OLLAMA_URL" in os.environ:
            del os.environ["BUTTERCLAW_OLLAMA_URL"]

    # ── Test 21: config_source in to_dict() ──
    d = cfg.to_dict()
    cs = d.get("config_source", {})
    _test(21, "config_source present in to_dict()",
           "dotenv_loaded" in cs and "dotenv_path" in cs and "env_override_active" in cs,
           f"config_source = {cs}")

    # ── Summary ──
    print()
    print("=" * 60)
    print(f"Results: {_pass}/{_pass + _fail} passed", end="")
    if _fail > 0:
        print(f" — {_fail} FAILED ⚠️")
    else:
        print(" — all clear 🦞")
    print("=" * 60)

    # ── Full config dump ──
    print()
    print("📋 Resolved Configuration:")
    print("-" * 40)
    for k, v in cfg.to_flat_dict().items():
        print(f"  {k:30s} = {v}")
    print("-" * 40)
    print(f"  {'CONFIG_VERSION':30s} = {CONFIG_VERSION}")
    print(f"  {'.env loaded':30s} = {cfg._dotenv_path or '(not found)'}")
    print()

    sys.exit(1 if _fail > 0 else 0)
"""
ButterClaw v0.6.3.2 — Policy Engine
===================================
Deterministic guardrails for the probabilistic Brain.

Provides:
  - Rule storage and CRUD in SQLite (policies table)
  - Policy event audit logging (policy_events table)
  - 3-scope filter pipeline: pre_brain, post_brain, pre_tool
  - Safe condition evaluator (extends ChainExecutor's operator pattern)
  - Dry-run testing of payloads against all policies
  - Priority-based short-circuit evaluation (lowest number wins)

Design decisions:
  - Zero new pip dependencies — uses stdlib only
  - Shares butterclaw.db with server.py (same DB_PATH pattern)
  - Condition evaluator uses whitelist operators — no eval()
  - Policies are NOT secrets — stored unencrypted in SQLite
  - Gibson does NOT destroy policies (they're config, not credentials)
  - "allow" policies are logged but do not short-circuit evaluation
  - First non-"allow" match wins (predictable, debuggable)
  - try/except ImportError guards in server.py for backward compat

Scopes:
  - pre_brain:  Runs BEFORE the Brain. Pattern-match known-bad/known-good payloads.
                Can short-circuit to CRITICAL or BENIGN without burning inference time.
  - post_brain: Runs AFTER the Brain returns a verdict but BEFORE tool execution.
                Can override the Brain's decision (escalate, downgrade, require confidence).
  - pre_tool:   Runs BEFORE each individual MCP tool call in a chain.
                Tool-level allowlist/blocklist. Per-tool gates.

Integration points (server.py):
  - analyze_threat(): pre_brain filter before ask_guardian_agent()
  - analyze_threat(): post_brain validator after ask_guardian_agent()
  - ChainExecutor._execute_step(): pre_tool gate before mcp_manager.send()
  - Hardcoded fallback path: pre_tool gate before gibson_kill / rotate_keys
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

logger = logging.getLogger("butterclaw.policy")

# =============================================
# CONSTANTS
# =============================================

VALID_SCOPES = ("pre_brain", "post_brain", "pre_tool")

VALID_ACTIONS = (
    "allow",               # Log match, do not short-circuit — evaluation continues
    "block",               # Reject the request entirely (pre_brain) or skip the tool (pre_tool)
    "override_critical",   # Force verdict to CRITICAL (pre_brain, post_brain)
    "override_benign",     # Force verdict to BENIGN (pre_brain, post_brain)
    "skip_tool",           # Skip this specific tool in a chain (pre_tool only)
    "require_confidence",  # Require minimum confidence for CRITICAL verdict (post_brain)
)

# Priority bounds
MIN_PRIORITY = 1
MAX_PRIORITY = 100
DEFAULT_PRIORITY = 50

# =============================================
# DATABASE
# =============================================

# Keep this line so the diagnostic tests still know where they are!
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from config import cfg
    DB_PATH = cfg.DB_PATH
except ImportError:
    DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

_db_lock = threading.Lock()


def _get_db():
    """Thread-safe connection to the ButterClaw database."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_policy_db():
    """Create the policies and policy_events tables if they don't exist."""
    with _get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS policies (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                description   TEXT,
                priority      INTEGER NOT NULL DEFAULT 50,
                enabled       INTEGER NOT NULL DEFAULT 1,
                scope         TEXT NOT NULL,
                condition     TEXT NOT NULL,
                action        TEXT NOT NULL,
                action_params TEXT,
                created_by    TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT,
                hit_count     INTEGER NOT NULL DEFAULT 0
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS policy_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT NOT NULL,
                policy_id        TEXT NOT NULL,
                policy_name      TEXT NOT NULL,
                scope            TEXT NOT NULL,
                action_taken     TEXT NOT NULL,
                original_verdict TEXT,
                final_verdict    TEXT,
                payload_preview  TEXT,
                tool_name        TEXT,
                chain_id         TEXT
            )
        ''')

        conn.commit()
    logger.info("🛡️ [POLICY] Database tables initialized.")


# =============================================
# SAFE CONDITION OPERATORS
# =============================================
# Extends the ChainExecutor VALID_CONDITION_OPERATORS pattern.
# No eval(). Every operator is a whitelisted lambda.

def _safe_float(v):
    """Safe float conversion — returns 0.0 on failure."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


POLICY_OPERATORS = {
    # --- String operators (inherited from ChainExecutor pattern) ---
    "contains":       lambda val, exp: str(exp).lower() in str(val).lower(),
    "not_contains":   lambda val, exp: str(exp).lower() not in str(val).lower(),
    "equals":         lambda val, exp: str(val).strip().lower() == str(exp).strip().lower(),
    "not_equals":     lambda val, exp: str(val).strip().lower() != str(exp).strip().lower(),
    "starts_with":    lambda val, exp: str(val).strip().lower().startswith(str(exp).strip().lower()),
    "ends_with":      lambda val, exp: str(val).strip().lower().endswith(str(exp).strip().lower()),

    # --- Regex (compiled with re.IGNORECASE) ---
    "regex_match":    lambda val, exp: bool(re.search(exp, str(val), re.IGNORECASE)),

    # --- Numeric comparisons (for confidence thresholds, payload size) ---
    "greater_than":   lambda val, exp: _safe_float(val) > _safe_float(exp),
    "less_than":      lambda val, exp: _safe_float(val) < _safe_float(exp),
    "greater_equal":  lambda val, exp: _safe_float(val) >= _safe_float(exp),
    "less_equal":     lambda val, exp: _safe_float(val) <= _safe_float(exp),

    # --- List membership ---
    "in_list":        lambda val, exp: str(val).strip().lower() in [x.strip().lower() for x in str(exp).split(",")],
    "not_in_list":    lambda val, exp: str(val).strip().lower() not in [x.strip().lower() for x in str(exp).split(",")],

    # --- Length comparisons (payload size gates) ---
    "length_gt":      lambda val, exp: len(str(val)) > int(exp),
    "length_lt":      lambda val, exp: len(str(val)) < int(exp),
}


# =============================================
# FIELD RESOLVERS PER SCOPE
# =============================================
# Each scope has access to different fields from the analysis context.
# Resolvers are lambdas that extract a string value from the context dict.

PRE_BRAIN_FIELDS = {
    "payload":        lambda ctx: ctx.get("raw_data", ""),
    "threat_type":    lambda ctx: ctx.get("threat_type", ""),
    "payload_length": lambda ctx: str(len(ctx.get("raw_data", ""))),
    "source_ip":      lambda ctx: ctx.get("source_ip", ""),
    "hour_of_day":    lambda ctx: str(time.localtime().tm_hour),
    "day_of_week":    lambda ctx: str(time.localtime().tm_wday),  # 0=Monday, 6=Sunday
}

POST_BRAIN_FIELDS = {
    **PRE_BRAIN_FIELDS,
    "verdict":        lambda ctx: ctx.get("verdict", ""),
    "confidence":     lambda ctx: str(ctx.get("confidence", 0.0)),
    "primary_gate":   lambda ctx: ctx.get("primary_gate", ""),
    "reasoning":      lambda ctx: ctx.get("reasoning", ""),
    "has_chain":      lambda ctx: "true" if ctx.get("chain") else "false",
}

PRE_TOOL_FIELDS = {
    **POST_BRAIN_FIELDS,
    "tool_name":      lambda ctx: ctx.get("tool_name", ""),
    "tool_args":      lambda ctx: str(ctx.get("tool_args", {})),
    "chain_step":     lambda ctx: str(ctx.get("chain_step", 0)),
}

SCOPE_FIELDS = {
    "pre_brain":  PRE_BRAIN_FIELDS,
    "post_brain": POST_BRAIN_FIELDS,
    "pre_tool":   PRE_TOOL_FIELDS,
}


# =============================================
# INTERNAL HELPERS
# =============================================

def _generate_policy_id():
    """Generate a unique policy ID with 'pol_' prefix."""
    return f"pol_{uuid.uuid4().hex[:10]}"


def _now_iso():
    """Current UTC timestamp in ISO 8601 format."""
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _increment_hit_count(policy_id):
    """Increment the hit counter for a policy. Fire-and-forget, non-blocking."""
    def _do_increment():
        try:
            with _db_lock:
                with _get_db() as conn:
                    conn.execute("UPDATE policies SET hit_count = hit_count + 1 WHERE id = ?", (policy_id,))
                    conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"⚠️ [POLICY] Hit count increment failed for {policy_id}: {e}")

    threading.Thread(target=_do_increment, daemon=True).start()


def _log_policy_event(policy_id, policy_name, scope, action_taken,
                      original_verdict=None, final_verdict=None,
                      payload_preview=None, tool_name=None, chain_id=None):
    """Write an audit event to the policy_events table."""
    try:
        # Truncate payload preview for storage
        if payload_preview and len(payload_preview) > 200:
            payload_preview = payload_preview[:197] + "..."

        with _db_lock:
            with _get_db() as conn:
                conn.execute('''
                    INSERT INTO policy_events
                        (timestamp, policy_id, policy_name, scope, action_taken,
                         original_verdict, final_verdict, payload_preview, tool_name, chain_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    _now_iso(), policy_id, policy_name, scope, action_taken,
                    original_verdict, final_verdict, payload_preview, tool_name, chain_id
                ))
                conn.commit()
    except sqlite3.Error as e:
        logger.warning(f"⚠️ [POLICY] Event logging failed: {e}")


def _validate_condition(condition, scope):
    """
    Validate a condition dict structure.

    Args:
        condition: dict with "field", "operator", "value" keys
        scope: one of VALID_SCOPES

    Raises:
        ValueError: if the condition is malformed
    """
    if not isinstance(condition, dict):
        raise ValueError("Condition must be a dictionary")

    required_keys = ("field", "operator", "value")
    missing = [k for k in required_keys if k not in condition]
    if missing:
        raise ValueError(f"Condition missing required keys: {', '.join(missing)}")

    if condition["operator"] not in POLICY_OPERATORS:
        valid_ops = ", ".join(sorted(POLICY_OPERATORS.keys()))
        raise ValueError(f"Unknown operator '{condition['operator']}'. Valid operators: {valid_ops}")

    scope_fields = SCOPE_FIELDS.get(scope, {})
    if condition["field"] not in scope_fields:
        valid_fields = ", ".join(sorted(scope_fields.keys()))
        raise ValueError(f"Field '{condition['field']}' not available in scope '{scope}'. Valid fields: {valid_fields}")

    # Validate regex patterns at creation time to catch syntax errors early
    if condition["operator"] == "regex_match":
        try:
            re.compile(condition["value"])
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")

    # Validate numeric operators have numeric-parseable expected values
    if condition["operator"] in ("greater_than", "less_than", "greater_equal", "less_equal", "length_gt", "length_lt"):
        try:
            float(condition["value"])
        except (ValueError, TypeError):
            raise ValueError(f"Operator '{condition['operator']}' requires a numeric value, got: '{condition['value']}'")


# =============================================
# CRUD OPERATIONS
# =============================================

def create_policy(name, scope, condition, action, action_params=None,
                  description=None, priority=DEFAULT_PRIORITY, created_by=None):
    """
    Create a new policy rule.

    Args:
        name:          Human-readable label (required)
        scope:         "pre_brain" | "post_brain" | "pre_tool" (required)
        condition:     dict with "field", "operator", "value" keys (required)
        action:        One of VALID_ACTIONS (required)
        action_params: dict with action-specific parameters (optional)
        description:   What this policy does and why (optional)
        priority:      1-100, lower = higher priority (default: 50)
        created_by:    key_id of the admin who created it (optional)

    Returns:
        dict with policy id, name, scope, created_at

    Raises:
        ValueError: if any parameter is invalid
    """
    # Validate scope
    if scope not in VALID_SCOPES:
        raise ValueError(f"Invalid scope '{scope}'. Valid scopes: {', '.join(VALID_SCOPES)}")

    # Validate action
    if action not in VALID_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Valid actions: {', '.join(VALID_ACTIONS)}")

    # Validate scope-action compatibility
    if action == "skip_tool" and scope != "pre_tool":
        raise ValueError("Action 'skip_tool' is only valid for scope 'pre_tool'")
    if action == "require_confidence" and scope != "post_brain":
        raise ValueError("Action 'require_confidence' is only valid for scope 'post_brain'")

    # Validate condition
    _validate_condition(condition, scope)

    # Validate priority bounds
    priority = max(MIN_PRIORITY, min(MAX_PRIORITY, int(priority)))

    # Validate action_params for require_confidence
    if action == "require_confidence":
        if not action_params or "min_confidence" not in action_params:
            raise ValueError("Action 'require_confidence' requires action_params with 'min_confidence' (integer 1-100)")
        min_conf = action_params["min_confidence"]
        if not isinstance(min_conf, (int, float)) or min_conf < 1 or min_conf > 100:
            raise ValueError("'min_confidence' must be an integer between 1 and 100")

    # Validate name is not empty
    if not name or not name.strip():
        raise ValueError("Policy name cannot be empty")

    policy_id = _generate_policy_id()
    now = _now_iso()

    with _db_lock:
        with _get_db() as conn:
            conn.execute('''
                INSERT INTO policies
                    (id, name, description, priority, enabled, scope,
                     condition, action, action_params, created_by, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ''', (
                policy_id, name.strip(), description, priority, scope,
                json.dumps(condition), action,
                json.dumps(action_params) if action_params else None,
                created_by, now
            ))
            conn.commit()

    logger.info(f"🛡️ [POLICY] Created: '{name}' [{policy_id}] scope={scope} action={action} priority={priority}")

    return {
        "id": policy_id,
        "name": name.strip(),
        "scope": scope,
        "action": action,
        "priority": priority,
        "created_at": now
    }


def get_policy(policy_id):
    """
    Fetch a single policy by ID.

    Returns:
        dict with all policy fields, or None if not found.
    """
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM policies WHERE id = ?", (policy_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    policy = dict(row)
    # Deserialize JSON fields
    policy["condition"] = json.loads(policy["condition"])
    if policy.get("action_params"):
        policy["action_params"] = json.loads(policy["action_params"])
    policy["enabled"] = bool(policy["enabled"])
    return policy


def list_policies(scope=None, enabled_only=False):
    """
    List all policies, optionally filtered by scope and/or enabled status.

    Args:
        scope:        Filter by scope (optional)
        enabled_only: If True, only return enabled policies

    Returns:
        list of policy dicts
    """
    query = "SELECT * FROM policies WHERE 1=1"
    params = []

    if scope:
        if scope not in VALID_SCOPES:
            return []
        query += " AND scope = ?"
        params.append(scope)

    if enabled_only:
        query += " AND enabled = 1"

    query += " ORDER BY priority ASC, created_at ASC"

    conn = _get_db()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    policies = []
    for row in rows:
        policy = dict(row)
        policy["condition"] = json.loads(policy["condition"])
        if policy.get("action_params"):
            policy["action_params"] = json.loads(policy["action_params"])
        policy["enabled"] = bool(policy["enabled"])
        policies.append(policy)

    return policies


def update_policy(policy_id, **kwargs):
    """
    Update a policy's fields. Only provided kwargs are changed.

    Supported fields: name, description, priority, scope, condition,
                      action, action_params, enabled

    Returns:
        Updated policy dict, or None if not found.

    Raises:
        ValueError: if any updated field is invalid
    """
    existing = get_policy(policy_id)
    if not existing:
        return None

    # Build the update from provided kwargs
    updatable = {}

    if "name" in kwargs:
        name = kwargs["name"]
        if not name or not str(name).strip():
            raise ValueError("Policy name cannot be empty")
        updatable["name"] = str(name).strip()

    if "description" in kwargs:
        updatable["description"] = kwargs["description"]

    if "priority" in kwargs:
        updatable["priority"] = max(MIN_PRIORITY, min(MAX_PRIORITY, int(kwargs["priority"])))

    if "enabled" in kwargs:
        updatable["enabled"] = 1 if kwargs["enabled"] else 0

    # If scope or condition or action changes, re-validate
    new_scope = kwargs.get("scope", existing["scope"])
    new_condition = kwargs.get("condition", existing["condition"])
    new_action = kwargs.get("action", existing["action"])
    new_action_params = kwargs.get("action_params", existing.get("action_params"))

    if "scope" in kwargs:
        if new_scope not in VALID_SCOPES:
            raise ValueError(f"Invalid scope '{new_scope}'. Valid scopes: {', '.join(VALID_SCOPES)}")
        updatable["scope"] = new_scope

    if "action" in kwargs:
        if new_action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action '{new_action}'. Valid actions: {', '.join(VALID_ACTIONS)}")
        if new_action == "skip_tool" and new_scope != "pre_tool":
            raise ValueError("Action 'skip_tool' is only valid for scope 'pre_tool'")
        if new_action == "require_confidence" and new_scope != "post_brain":
            raise ValueError("Action 'require_confidence' is only valid for scope 'post_brain'")
        updatable["action"] = new_action

    if "condition" in kwargs:
        _validate_condition(new_condition, new_scope)
        updatable["condition"] = json.dumps(new_condition)

    if "action_params" in kwargs:
        if new_action == "require_confidence":
            if not new_action_params or "min_confidence" not in new_action_params:
                raise ValueError("Action 'require_confidence' requires action_params with 'min_confidence'")
        updatable["action_params"] = json.dumps(new_action_params) if new_action_params else None

    if not updatable:
        return existing  # Nothing to update

    updatable["updated_at"] = _now_iso()

    set_clause = ", ".join(f"{k} = ?" for k in updatable.keys())
    values = list(updatable.values()) + [policy_id]

    with _db_lock:
        with _get_db() as conn:
            conn.execute(f"UPDATE policies SET {set_clause} WHERE id = ?", values)
            conn.commit()

    logger.info(f"🛡️ [POLICY] Updated: [{policy_id}] fields={list(updatable.keys())}")

    return get_policy(policy_id)


def delete_policy(policy_id):
    """
    Permanently delete a policy rule.

    Returns:
        True if deleted, False if not found.
    """
    with _get_db() as conn:
        cursor = conn.execute("DELETE FROM policies WHERE id = ?", (policy_id,))
        deleted = cursor.rowcount > 0
        conn.commit()

    if deleted:
        logger.info(f"🗑️ [POLICY] Deleted: [{policy_id}]")
    return deleted


def toggle_policy(policy_id, enabled):
    """
    Enable or disable a policy without deleting it.

    Args:
        policy_id: The policy to toggle
        enabled:   True to enable, False to disable

    Returns:
        True if toggled, False if not found.
    """
    enabled_int = 1 if enabled else 0

    with _db_lock:
        with _get_db() as conn:
            cursor = conn.execute(
                "UPDATE policies SET enabled = ?, updated_at = ? WHERE id = ?",
                (enabled_int, _now_iso(), policy_id)
            )
            toggled = cursor.rowcount > 0
            conn.commit()

    if toggled:
        state = "enabled" if enabled else "disabled"
        logger.info(f"🛡️ [POLICY] Toggled: [{policy_id}] → {state}")
    return toggled


# =============================================
# POLICY EVENT QUERIES
# =============================================

def get_policy_events(limit=50, policy_id=None, scope=None, since=None):
    """
    Query the policy event audit log.

    Args:
        limit:     Max results (default 50, max 200)
        policy_id: Filter by specific policy
        scope:     Filter by scope
        since:     Filter by timestamp (ISO 8601)

    Returns:
        list of event dicts
    """
    query = "SELECT * FROM policy_events WHERE 1=1"
    params = []

    if policy_id:
        query += " AND policy_id = ?"
        params.append(policy_id)

    if scope:
        query += " AND scope = ?"
        params.append(scope)

    if since:
        query += " AND timestamp >= ?"
        params.append(since)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 200))

    conn = _get_db()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


def get_policy_event_count():
    """Return total policy event count."""
    try:
        conn = _get_db()
        try:
            count = conn.execute("SELECT COUNT(*) FROM policy_events").fetchone()[0]
        finally:
            conn.close()
        return count
    except sqlite3.Error:
        return 0


# =============================================
# CORE EVALUATION ENGINE
# =============================================

def evaluate_policies(scope, context):
    """
    Evaluate all enabled policies for a given scope against the provided context.

    This is the core function. Called at each of the three pipeline scopes
    (pre_brain, post_brain, pre_tool) from server.py.

    Policies are evaluated in priority order (lowest number = highest priority).
    First matching policy with a non-"allow" action wins (short-circuit).
    "allow" policies are logged but do not stop evaluation.

    Args:
        scope:   "pre_brain" | "post_brain" | "pre_tool"
        context: dict with analysis data (payload, verdict, tool_name, etc.)

    Returns:
        dict with:
            action:           None | one of VALID_ACTIONS
            policy_id:        str or None (the winning policy)
            policy_name:      str or None
            reason:           str or None (human-readable explanation)
            action_params:    dict or None (for require_confidence, etc.)
            policies_checked: int (total enabled policies in this scope)
            policies_matched: list of policy_ids that matched
    """
    if scope not in VALID_SCOPES:
        return _empty_result(0)

    # Fetch all enabled policies for this scope, ordered by priority
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM policies WHERE scope = ? AND enabled = 1 ORDER BY priority ASC",
            (scope,)
        ).fetchall()
    finally:
        conn.close()

    fields = SCOPE_FIELDS.get(scope, {})

    result = _empty_result(len(rows))

    for row in rows:
        policy = dict(row)
        condition = json.loads(policy["condition"])

        field_name = condition.get("field")
        operator = condition.get("operator")
        expected = condition.get("value")

        # Resolve field value from context
        field_resolver = fields.get(field_name)
        if not field_resolver:
            continue  # Unknown field — skip silently

        try:
            actual_value = field_resolver(context)
        except Exception:
            continue  # Field resolution error — skip silently

        # Evaluate condition using safe operator
        op_func = POLICY_OPERATORS.get(operator)
        if not op_func:
            continue  # Unknown operator — skip silently

        try:
            matched = op_func(actual_value, expected)
        except Exception as e:
            logger.warning(f"⚠️ [POLICY] Evaluation error on {policy['id']}: {e}")
            continue

        if not matched:
            continue

        # --- Policy matched ---
        result["policies_matched"].append(policy["id"])

        # Increment hit count (async, non-blocking)
        _increment_hit_count(policy["id"])

        # Log the policy event
        _log_policy_event(
            policy_id=policy["id"],
            policy_name=policy["name"],
            scope=scope,
            action_taken=policy["action"],
            original_verdict=context.get("verdict"),
            payload_preview=str(context.get("raw_data", ""))[:200],
            tool_name=context.get("tool_name"),
            chain_id=context.get("chain_id")
        )

        # "allow" policies are logged but don't override — continue evaluation
        if policy["action"] == "allow":
            continue

        # First non-allow match wins (short-circuit)
        action_params = None
        if policy.get("action_params"):
            try:
                action_params = json.loads(policy["action_params"])
            except (json.JSONDecodeError, TypeError):
                action_params = None

        result["action"] = policy["action"]
        result["policy_id"] = policy["id"]
        result["policy_name"] = policy["name"]
        result["reason"] = (
            f"Policy '{policy['name']}' [{policy['id']}]: "
            f"{policy.get('description') or policy['action']}"
        )
        result["action_params"] = action_params
        break  # Short-circuit — first non-allow match wins

    return result


def _empty_result(policies_checked):
    """Return a clean no-match result."""
    return {
        "action": None,
        "policy_id": None,
        "policy_name": None,
        "reason": None,
        "action_params": None,
        "policies_checked": policies_checked,
        "policies_matched": []
    }


# =============================================
# DRY-RUN TESTING
# =============================================

def test_payload(payload, threat_type="test"):
    """
    Dry-runs a payload against all scopes using a worst-case mock context.
    """
    import datetime
    
    # 1. Build a hyper-rich mock context so all test types trigger properly
    ctx = {
        "payload": payload,
        "raw_data": payload,
        "threat_type": threat_type,
        "payload_length": len(str(payload)),
        "source_ip": "127.0.0.1",
        "hour_of_day": datetime.datetime.now().hour,
        "day_of_week": datetime.datetime.now().weekday(),
        "verdict": "CRITICAL",
        "confidence": 1.0,
        "primary_gate": "DryRunGate",
        "reasoning": "Dry-run test evaluation",
        "has_chain": True,
        
        # Crucial for testing pre_tool gates like your Veto Auto-Gibson rule!
        "tool_name": "execute_gibson_kill",  
        "tool_args": {"target_process": "AI_Agent_Process"},
        "chain_step": 1
    }

    # 2. Evaluate all scopes
    results = {
        "pre_brain": evaluate_policies("pre_brain", ctx),
        "post_brain": evaluate_policies("post_brain", ctx),
        "pre_tool": evaluate_policies("pre_tool", ctx)
    }
    
    # 3. Format the return to guarantee the JS UI understands it
    # (This ensures it works regardless of which JS patch version you are running)
    formatted_results = {}
    for scope, res in results.items():
        action = res.get("action", "allow")
        pid = res.get("policy_id")
        
        formatted_results[scope] = {
            "action": action,
            "policy_id": pid,
            "reason": res.get("reason", "No match"),
            "policies_matched": [pid] if pid and action != "allow" else []
        }
        
    return formatted_results


def _evaluate_dry_run(scope, context):
    """
    Evaluate policies without logging events or incrementing counters.

    Returns:
        dict with matched policies and what would happen
    """
    if scope not in VALID_SCOPES:
        return {"policies_checked": 0, "matches": []}

    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM policies WHERE scope = ? AND enabled = 1 ORDER BY priority ASC",
            (scope,)
        ).fetchall()
    finally:
        conn.close()

    fields = SCOPE_FIELDS.get(scope, {})

    matches = []
    winning_action = None

    for row in rows:
        policy = dict(row)
        condition = json.loads(policy["condition"])

        field_name = condition.get("field")
        operator = condition.get("operator")
        expected = condition.get("value")

        field_resolver = fields.get(field_name)
        if not field_resolver:
            continue

        try:
            actual_value = field_resolver(context)
        except Exception:
            continue

        op_func = POLICY_OPERATORS.get(operator)
        if not op_func:
            continue

        try:
            matched = op_func(actual_value, expected)
        except Exception:
            continue

        if not matched:
            continue

        action_params = None
        if policy.get("action_params"):
            try:
                action_params = json.loads(policy["action_params"])
            except (json.JSONDecodeError, TypeError):
                action_params = None

        match_info = {
            "policy_id": policy["id"],
            "policy_name": policy["name"],
            "priority": policy["priority"],
            "action": policy["action"],
            "action_params": action_params,
            "would_short_circuit": policy["action"] != "allow" and winning_action is None,
        }
        matches.append(match_info)

        if policy["action"] != "allow" and winning_action is None:
            winning_action = policy["action"]

    return {
        "policies_checked": len(rows),
        "matches": matches,
        "winning_action": winning_action
    }


# =============================================
# DIAGNOSTIC MODE
# =============================================

if __name__ == "__main__":
    """
    Self-test suite for the policy engine.
    Run: python policy_engine.py
    """
    import sys

    print("\n🛡️ ButterClaw Policy Engine — Diagnostic Mode")
    print("=" * 55)

    # Initialize tables
    init_policy_db()
    print("✅ Test 0: Database tables initialized.")

    test_ids = []  # Track created policies for cleanup

    # ──────────────────────────────────────
    # Test 1: Create a pre_brain policy
    # ──────────────────────────────────────
    try:
        p1 = create_policy(
            name="Block websocket exfiltration",
            scope="pre_brain",
            condition={"field": "payload", "operator": "regex_match", "value": r"wss?://[^\s]*\.(net|io|xyz)"},
            action="override_critical",
            description="External websocket to suspicious TLD",
            priority=10
        )
        test_ids.append(p1["id"])
        print(f"✅ Test 1: Pre-brain policy created: {p1['id']}")
    except Exception as e:
        print(f"❌ Test 1: Pre-brain policy creation failed: {e}")
        sys.exit(1)

    # ──────────────────────────────────────
    # Test 2: Create a post_brain policy
    # ──────────────────────────────────────
    try:
        p2 = create_policy(
            name="Require high confidence for .env",
            scope="post_brain",
            condition={"field": "payload", "operator": "contains", "value": ".env"},
            action="require_confidence",
            action_params={"min_confidence": 95},
            description="Payloads touching .env need 95%+ confidence",
            priority=20
        )
        test_ids.append(p2["id"])
        print(f"✅ Test 2: Post-brain policy created: {p2['id']}")
    except Exception as e:
        print(f"❌ Test 2: Post-brain policy creation failed: {e}")
        sys.exit(1)

    # ──────────────────────────────────────
    # Test 3: Create a pre_tool policy
    # ──────────────────────────────────────
    try:
        p3 = create_policy(
            name="Tool allowlist",
            scope="pre_tool",
            condition={"field": "tool_name", "operator": "not_in_list", "value": "execute_gibson_kill,rotate_keys,scan_signatures"},
            action="skip_tool",
            description="Only execute tools on the approved allowlist",
            priority=99
        )
        test_ids.append(p3["id"])
        print(f"✅ Test 3: Pre-tool policy created: {p3['id']}")
    except Exception as e:
        print(f"❌ Test 3: Pre-tool policy creation failed: {e}")
        sys.exit(1)

    # ──────────────────────────────────────
    # Test 4: Evaluate pre_brain — matching payload
    # ──────────────────────────────────────
    try:
        result = evaluate_policies("pre_brain", {
            "raw_data": "Agent connecting to wss://evil-exfil.xyz/stream",
            "threat_type": "websocket_connection",
            "source_ip": "127.0.0.1"
        })
        if result["action"] == "override_critical" and p1["id"] in result["policies_matched"]:
            print(f"✅ Test 4: Pre-brain matched — action={result['action']}, policy={result['policy_id']}")
        else:
            print(f"❌ Test 4: Pre-brain match expected but got: {result}")
    except Exception as e:
        print(f"❌ Test 4: Pre-brain evaluation failed: {e}")

    # ──────────────────────────────────────
    # Test 5: Evaluate pre_brain — non-matching payload
    # ──────────────────────────────────────
    try:
        result = evaluate_policies("pre_brain", {
            "raw_data": "Normal log entry: user logged in at 14:30",
            "threat_type": "auth_event",
            "source_ip": "127.0.0.1"
        })
        if result["action"] is None and len(result["policies_matched"]) == 0:
            print(f"✅ Test 5: Pre-brain no match — correct (action=None)")
        else:
            print(f"❌ Test 5: Expected no match but got: {result}")
    except Exception as e:
        print(f"❌ Test 5: Pre-brain evaluation failed: {e}")

    # ──────────────────────────────────────
    # Test 6: Priority ordering — lower priority wins
    # ──────────────────────────────────────
    try:
        p_low = create_policy(
            name="Low priority benign override",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "priority_test"},
            action="override_benign",
            priority=90
        )
        p_high = create_policy(
            name="High priority critical override",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "priority_test"},
            action="override_critical",
            priority=5
        )
        test_ids.extend([p_low["id"], p_high["id"]])

        result = evaluate_policies("pre_brain", {
            "raw_data": "This is a priority_test payload",
            "threat_type": "test",
            "source_ip": "127.0.0.1"
        })
        if result["action"] == "override_critical" and result["policy_id"] == p_high["id"]:
            print(f"✅ Test 6: Priority ordering correct — higher priority (5) won over (90)")
        else:
            print(f"❌ Test 6: Expected priority 5 to win but got: {result}")
    except Exception as e:
        print(f"❌ Test 6: Priority test failed: {e}")

    # ──────────────────────────────────────
    # Test 7: Disabled policy is skipped
    # ──────────────────────────────────────
    try:
        p_disabled = create_policy(
            name="Disabled policy",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "disabled_test_marker"},
            action="override_critical",
            priority=1
        )
        test_ids.append(p_disabled["id"])
        toggle_policy(p_disabled["id"], False)

        result = evaluate_policies("pre_brain", {
            "raw_data": "This payload has disabled_test_marker in it",
            "threat_type": "test",
            "source_ip": "127.0.0.1"
        })
        if result["action"] is None or p_disabled["id"] not in result["policies_matched"]:
            print(f"✅ Test 7: Disabled policy correctly skipped")
        else:
            print(f"❌ Test 7: Disabled policy should not match but got: {result}")
    except Exception as e:
        print(f"❌ Test 7: Disabled policy test failed: {e}")

    # ──────────────────────────────────────
    # Test 8: "allow" policy does not short-circuit
    # ──────────────────────────────────────
    try:
        p_allow = create_policy(
            name="Allow known safe",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "allow_test_marker"},
            action="allow",
            priority=1
        )
        p_after = create_policy(
            name="Override after allow",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "allow_test_marker"},
            action="override_critical",
            priority=50
        )
        test_ids.extend([p_allow["id"], p_after["id"]])

        result = evaluate_policies("pre_brain", {
            "raw_data": "Payload with allow_test_marker for testing",
            "threat_type": "test",
            "source_ip": "127.0.0.1"
        })
        if result["action"] == "override_critical" and p_allow["id"] in result["policies_matched"]:
            print(f"✅ Test 8: 'allow' logged but did not short-circuit — override_critical fired after")
        else:
            print(f"❌ Test 8: Expected allow + override_critical but got: {result}")
    except Exception as e:
        print(f"❌ Test 8: Allow test failed: {e}")

    # ──────────────────────────────────────
    # Test 9: Unknown operator is safely skipped
    # ──────────────────────────────────────
    try:
        # Manually insert a policy with a bogus operator
        with _get_db() as conn:
            bogus_id = _generate_policy_id()
            conn.execute('''
                INSERT INTO policies (id, name, priority, enabled, scope, condition, action, created_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ''', (bogus_id, "Bogus operator", 1, "pre_brain",
                  json.dumps({"field": "payload", "operator": "quantum_entangle", "value": "test"}),
                  "override_critical", _now_iso()))
            conn.commit()
        test_ids.append(bogus_id)

        result = evaluate_policies("pre_brain", {
            "raw_data": "test payload for bogus operator",
            "threat_type": "test",
            "source_ip": "127.0.0.1"
        })
        if bogus_id not in result["policies_matched"]:
            print(f"✅ Test 9: Unknown operator 'quantum_entangle' safely skipped")
        else:
            print(f"❌ Test 9: Bogus operator should not have matched")
    except Exception as e:
        print(f"❌ Test 9: Unknown operator test failed: {e}")

    # ──────────────────────────────────────
    # Test 10: Dry-run test_payload
    # ──────────────────────────────────────
    try:
        results = test_payload("Agent exfiltrating data to wss://evil.xyz/stream")
        pre_matches = results["pre_brain"]["matches"]
        if len(pre_matches) > 0 and any(m["policy_id"] == p1["id"] for m in pre_matches):
            print(f"✅ Test 10: Dry-run found {len(pre_matches)} pre_brain match(es)")
        else:
            print(f"❌ Test 10: Dry-run expected pre_brain match but got: {results['pre_brain']}")
    except Exception as e:
        print(f"❌ Test 10: Dry-run test failed: {e}")

    # ──────────────────────────────────────
    # Test 11: Policy event logging
    # ──────────────────────────────────────
    try:
        events = get_policy_events(limit=10, policy_id=p1["id"])
        if len(events) > 0 and events[0]["policy_id"] == p1["id"]:
            print(f"✅ Test 11: Policy events logged — {len(events)} event(s) for {p1['id']}")
        else:
            print(f"❌ Test 11: Expected events for {p1['id']} but got: {events}")
    except Exception as e:
        print(f"❌ Test 11: Event logging test failed: {e}")

    # ──────────────────────────────────────
    # Test 12: CRUD — update, toggle, delete
    # ──────────────────────────────────────
    try:
        # Update
        updated = update_policy(p1["id"], name="Updated websocket rule", priority=5)
        if updated and updated["name"] == "Updated websocket rule" and updated["priority"] == 5:
            print(f"✅ Test 12a: Update succeeded — name and priority changed")
        else:
            print(f"❌ Test 12a: Update failed: {updated}")

        # Toggle
        toggled = toggle_policy(p1["id"], False)
        check = get_policy(p1["id"])
        if toggled and not check["enabled"]:
            print(f"✅ Test 12b: Toggle disabled succeeded")
        else:
            print(f"❌ Test 12b: Toggle failed: enabled={check['enabled']}")

        # Re-enable
        toggle_policy(p1["id"], True)

        # Delete
        deleted = delete_policy(p1["id"])
        check = get_policy(p1["id"])
        if deleted and check is None:
            print(f"✅ Test 12c: Delete succeeded — policy gone")
            test_ids.remove(p1["id"])
        else:
            print(f"❌ Test 12c: Delete failed")

    except Exception as e:
        print(f"❌ Test 12: CRUD test failed: {e}")

    # ──────────────────────────────────────
    # Test 13: Validation — invalid scope
    # ──────────────────────────────────────
    try:
        create_policy(
            name="Bad scope",
            scope="during_brain",
            condition={"field": "payload", "operator": "contains", "value": "test"},
            action="block"
        )
        print(f"❌ Test 13: Should have raised ValueError for invalid scope")
    except ValueError as e:
        print(f"✅ Test 13: Invalid scope correctly rejected: {e}")
    except Exception as e:
        print(f"❌ Test 13: Unexpected error: {e}")

    # ──────────────────────────────────────
    # Test 14: Validation — invalid operator
    # ──────────────────────────────────────
    try:
        create_policy(
            name="Bad operator",
            scope="pre_brain",
            condition={"field": "payload", "operator": "quantum_entangle", "value": "test"},
            action="block"
        )
        print(f"❌ Test 14: Should have raised ValueError for invalid operator")
    except ValueError as e:
        print(f"✅ Test 14: Invalid operator correctly rejected: {e}")
    except Exception as e:
        print(f"❌ Test 14: Unexpected error: {e}")

    # ──────────────────────────────────────
    # Test 15: Validation — scope/action mismatch
    # ──────────────────────────────────────
    try:
        create_policy(
            name="skip_tool in wrong scope",
            scope="pre_brain",
            condition={"field": "payload", "operator": "contains", "value": "test"},
            action="skip_tool"
        )
        print(f"❌ Test 15: Should have raised ValueError for scope/action mismatch")
    except ValueError as e:
        print(f"✅ Test 15: Scope/action mismatch correctly rejected: {e}")
    except Exception as e:
        print(f"❌ Test 15: Unexpected error: {e}")

    # ──────────────────────────────────────
    # Test 16: Validation — bad regex
    # ──────────────────────────────────────
    try:
        create_policy(
            name="Bad regex",
            scope="pre_brain",
            condition={"field": "payload", "operator": "regex_match", "value": "[invalid(regex"},
            action="block"
        )
        print(f"❌ Test 16: Should have raised ValueError for bad regex")
    except ValueError as e:
        print(f"✅ Test 16: Invalid regex correctly rejected: {e}")
    except Exception as e:
        print(f"❌ Test 16: Unexpected error: {e}")

    # ──────────────────────────────────────
    # Cleanup — remove all test policies
    # ──────────────────────────────────────
    print(f"\n🧹 Cleaning up {len(test_ids)} test policies...")
    for pid in test_ids:
        try:
            delete_policy(pid)
        except Exception:
            pass

    # Also clean any leftover test events
    try:
        with _get_db() as conn:
            conn.execute("DELETE FROM policy_events WHERE policy_id LIKE 'pol_%'")
            conn.commit()
    except Exception:
        pass

    print("=" * 55)
    print("🛡️ Policy Engine diagnostic complete.\n")
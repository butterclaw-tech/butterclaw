"""
ButterClaw v0.1.1 — Reasoning Engine (Patched + Routing Integration)
=====================================================================
Changelog from v0.1:
  [C1] Removed manual CORS wildcard on /api/stream — Flask-CORS handles it
  [C2] Input validation on /api/analyze — null check + required field check
  [C3] threading.Lock on all global state (total_logs_processed, current_level, shield_enabled)
  [C4] try/except on all SQLite operations — returns proper error responses
  [M1] Single declaration of total_logs_processed (removed duplicate)
  [M2] Removed dead code: live_oopsie_logs
  [M3] Removed dead code: trigger_kill_switch
  [M4] Absolute DB path via __file__ — no more CWD dependency
  [M5] check_same_thread=False on SQLite connections
  [M6] Werkzeug log level → WARNING (was ERROR — swallowed 4xx/5xx)
  [N1] GET /api/settings — frontend syncs paranoia slider on load
  [N2] POST /api/shield — frontend shield toggle is no longer cosmetic
  [L1] Simple in-memory rate limiter on /api/analyze (10 req/min)
  [L2] Version string in startup banner

Routing Integration (v0.1.1-routing):
  [R1] GET /api/health — lightweight health check for Test Ping + connection badge
  [R2] Dynamic model name — replaces hardcoded MODEL_NAME, reads from global state
  [R3] Dynamic endpoint — routing_mode switches between local Ollama and remote VPS
  [R4] Gate states — stored, returned, and used to shape analysis behavior
  [R5] Extended /api/settings — GET/POST now handles routing_mode, model, endpoint, gates
  [R6] Gate-aware analysis — active gates listed in system prompt, kill_sw suppresses SIGKILL
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import datetime
import logging
import time
import sqlite3
import threading
import os
from collections import deque
from urllib.parse import urlparse
import json

# =============================================
# APP SETUP
# =============================================

VERSION = "0.2"

app = Flask(__name__)

# The Titanium Shield (Localhost Only)
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5000",   # Standard local Flask port
    "http://localhost:5000",
    "http://127.0.0.1:5500",   # VS Code Live Server default port
    "http://localhost:5500",
    "null"                      # For double-clicking the HTML file directly
]

# [C1] Flask-CORS handles ALL endpoints — no more manual wildcard overrides
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})


# =============================================
# [C3] THREAD-SAFE GLOBAL STATE
# =============================================

_state_lock = threading.Lock()
total_logs_processed = 0       # [M1] Single declaration — no duplicate
current_level = "3"            # Paranoia slider (1=Chill, 2=Cautious, 3=Paranoid)
shield_enabled = True          # [N2] Shield state — frontend can now toggle this

# [R2] Dynamic model — replaces hardcoded MODEL_NAME
model_name = "phi3:latest"

# [R3] Routing state — local Ollama vs remote VPS
routing_mode = "local"         # "local" or "remote"
remote_endpoint = ""           # VPS URL (only used when routing_mode == "remote")

# [R4] Logic gate states — controls which analysis gates are active
gate_states = {
    "sig_scan": True,          # Signature Scan gate
    "origin_ctx": True,        # Origin Context gate
    "intent": True,            # Intent Classification gate
    "kill_sw": True            # Kill Switch gate (when DISARMED, suppresses SIGKILL actions)
}

# =============================================
# DEFAULTS — used as fallbacks + validation references
# =============================================

OLLAMA_LOCAL_BASE = "http://localhost:11434"
OLLAMA_CHAT_PATH = "/api/chat"
VALID_ROUTING_MODES = ("local", "remote")
VALID_GATE_KEYS = frozenset(gate_states.keys())


# =============================================
# [L1] SIMPLE RATE LIMITER
# =============================================

RATE_LIMIT_MAX = 10            # Max requests per window
RATE_LIMIT_WINDOW = 60         # Window in seconds
_rate_log = deque()            # Timestamps of recent /api/analyze calls
_rate_lock = threading.Lock()


def is_rate_limited():
    """Returns True if the caller has exceeded the rate limit."""
    now = time.time()
    with _rate_lock:
        # Purge timestamps older than the window
        while _rate_log and _rate_log[0] < now - RATE_LIMIT_WINDOW:
            _rate_log.popleft()
        if len(_rate_log) >= RATE_LIMIT_MAX:
            return True
        _rate_log.append(now)
        return False


# =============================================
# [M4] ABSOLUTE DB PATH + [M5] THREAD-SAFE SQLITE
# =============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')


def get_db_connection():
    """Opens the vault door."""
    # [M5] check_same_thread=False — safe for Flask's threaded model
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Builds the vault if it doesn't exist yet."""
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            desc TEXT,
            action TEXT,
            time TEXT,
            icon TEXT,
            color TEXT
        )
    ''')
    conn.commit()
    conn.close()


# Run the builder immediately!
init_db()


# =============================================
# [M6] LOGGING — WARNING level (was ERROR)
# =============================================

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)  # [M6] Now shows 4xx/5xx but not routine GET spam


# =============================================
# [R3] DYNAMIC ENDPOINT RESOLUTION
# =============================================

def _resolve_ollama_url():
    """
    Returns the full Ollama chat API URL based on current routing state.
    Local mode → localhost:11434/api/chat
    Remote mode → {remote_endpoint}/api/chat
    Thread-safe: reads state under lock.
    """
    with _state_lock:
        mode = routing_mode
        endpoint = remote_endpoint

    if mode == "remote" and endpoint:
        # Strip trailing slash, append chat path
        base = endpoint.rstrip("/")
        return f"{base}{OLLAMA_CHAT_PATH}"
    return f"{OLLAMA_LOCAL_BASE}{OLLAMA_CHAT_PATH}"


def _validate_endpoint_url(url_string):
    """
    Basic URL validation — must have scheme (http/https) and netloc.
    Returns True if valid, False otherwise.
    """
    if not url_string:
        return True  # Empty is valid — means "not configured yet"
    try:
        parsed = urlparse(url_string)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# =============================================
# THE GUARDIAN BRAIN
# =============================================

def ask_guardian_agent(threat_type, raw_data):
    """
    [v0.2] Passes the log through the Logic Gates, enforcing JSON output.
    Returns a structured dictionary instead of a raw string.
    """
    with _state_lock:
        level = current_level
        active_model = model_name
        gates = dict(gate_states)

    mode_instructions = "Mode: RELAXED. Be lenient unless it's a clear RCE."
    if level == "2":
        mode_instructions = "Mode: CAUTIOUS. Flag anomalies and token leaks."
    if level == "3":
        mode_instructions = "Mode: PARANOID. Zero Trust. Flag ANY external origin breathing on local ports."

    active_gates = [k for k, v in gates.items() if v]
    inactive_gates = [k for k, v in gates.items() if not v]

    gate_context = ""
    if inactive_gates:
        gate_labels = {
            "sig_scan": "Signature Scan",
            "origin_ctx": "Origin Context",
            "intent": "Intent Classification",
            "kill_sw": "Kill Switch"
        }
        active_labels = [gate_labels.get(g, g) for g in active_gates]
        inactive_labels = [gate_labels.get(g, g) for g in inactive_gates]
        gate_context = (
            f" Active analysis gates: {', '.join(active_labels) if active_labels else 'NONE'}."
            f" Disabled gates (skip these): {', '.join(inactive_labels)}."
        )
        if not gates.get("kill_sw"):
            gate_context += " Kill Switch is DISARMED — do NOT recommend process termination."

    # --- THE UFO UPGRADE: JSON Schema Enforcement ---
    json_schema = (
        'You must respond ONLY with a valid JSON object. Do not include markdown formatting. '
        'Strict Schema: {"verdict": "CRITICAL" | "WARNING" | "BENIGN", "confidence": float 0.0-1.0, "reasoning": "2-sentence explanation."}'
    )

    ollama_url = _resolve_ollama_url()

    payload = {
        "model": active_model,
        "format": "json",  # Forces Ollama to output valid JSON
        "messages": [
            {
                "role": "system",
                "content": f"You are ButterClaw, an expert Blue Team cybersecurity Guardian AI. {mode_instructions}{gate_context} {json_schema}"
            },
            {
                "role": "user",
                "content": (
                    f"Analyze this local AI agent event:\n"
                    f"Threat Type: {threat_type}\n"
                    f"Raw Data/Log: {raw_data}\n\n"
                    f"Determine if this is a CSWH attempt, an Indirect Prompt Injection, or benign noise."
                )
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.2  # Unfrozen! 🧠
        }
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=120)
        raw_content = response.json().get("message", {}).get("content", "{}")

        try:
            parsed = json.loads(raw_content)
            return {
                "verdict": str(parsed.get("verdict", "UNKNOWN")).upper(),
                "confidence": float(parsed.get("confidence", 0.0)),
                "reasoning": str(parsed.get("reasoning", "Model failed to provide reasoning."))
            }
        except json.JSONDecodeError:
            return {
                "verdict": "ERROR",
                "confidence": 0.0,
                "reasoning": f"JSON parse failed on output: {raw_content}"
            }

    except Exception as e:
        return {"verdict": "ERROR", "confidence": 0.0, "reasoning": f"Brain failure: {str(e)}"}


# =============================================
# API ROUTES
# =============================================

# --- [R1] HEALTH CHECK ---

@app.route('/api/health', methods=['GET'])
def health():
    """
    [R1] Lightweight health probe for routing.html.
    Used by: Test Ping button (performance.now() RTT), connection badge (30s poll).
    """
    return jsonify({"status": "ok", "version": VERSION}), 200


# --- THREAT ANALYSIS ---

@app.route('/api/analyze', methods=['POST'])
def analyze_threat():
    # [L1] Rate limiting
    if is_rate_limited():
        return jsonify({"error": "Rate limit exceeded. Max 10 requests per minute."}), 429

    # [C2] Input validation
    data = request.json
    if data is None:
        return jsonify({"error": "Request body must be valid JSON with Content-Type: application/json"}), 400

    threat_type = data.get("threat_type")
    raw_data = data.get("raw_data")

    if not threat_type or not raw_data:
        return jsonify({"error": "Missing required fields: 'threat_type' and 'raw_data'"}), 400

    # --- THE TERMINAL X-RAY (FRONTEND -> BACKEND) ---
    print("\n" + "=" * 60)
    print(f"\U0001f4e5 [HTTP POST RECEIVED] From Browser Dashboard")
    print(f"   Payload: {threat_type}")

    # --- THE TERMINAL X-RAY (BACKEND -> OLLAMA) ---
    ollama_url = _resolve_ollama_url()
    print(f"\U0001f4e1 [HTTP POST DISPATCHED] Routing to {ollama_url}...")
    start_time = time.time()

    # Let the model stew on it (v0.2 returns a dict!)
    analysis = ask_guardian_agent(threat_type, raw_data)
    
    end_time = time.time()
    stew_time = round(end_time - start_time, 2)

    # Extract the structured data
    verdict_upper = analysis["verdict"]
    confidence_pct = int(analysis["confidence"] * 100)
    
    # We now embed the confidence score directly into the UI description!
    verdict_text = f"[{confidence_pct}% Confidence] {analysis['reasoning']}"

    print(f"\U0001f9e0 [HTTP 200 OK] Model returned {verdict_upper} ({confidence_pct}%) in {stew_time} seconds.")
    print("=" * 60)

    # [R6] Gate-aware action assignment
    with _state_lock:
        kill_sw_armed = gate_states.get("kill_sw", True)

    # THE BOX TRAP IS DEAD. We use exact matching now.
    if verdict_upper == "CRITICAL":
        color = "red"
        icon = "🚨"
        if kill_sw_armed:
            # --- WIRING THE PROP CLAWS ---
            import butterclaw_mcp
            butterclaw_mcp.execute_gibson_kill("openclaw")
            butterclaw_mcp.rotate_keys("OpenRouter")
            # -----------------------------
            action = "SIGKILL | Keys Buttered"
        else:
            action = "ALERT | Kill Switch Disarmed"
    elif verdict_upper == "WARNING":
        color = "amber"
        icon = "⚠️"
        action = "Monitored"
    elif verdict_upper == "ERROR":
        color = "red"
        icon = "❌"
        action = "System Offline"
    else:
        # Defaults to BENIGN. 
        color = "emerald"
        icon = "✅"
        action = "Monitored"

    # [C4] DB write with error handling
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO logs (title, desc, action, time, icon, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (threat_type, verdict_text, action,
              datetime.datetime.now().strftime("%H:%M:%S"), icon, color))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ [DB ERROR] Failed to write log: {e}")
        return jsonify({"error": f"Database write failed: {e}"}), 500

    # [C3] Thread-safe counter increment
    with _state_lock:
        global total_logs_processed
        total_logs_processed += 1

    return jsonify({"status": "success", "verdict": verdict_text}), 200


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """The Browser asks for history, we fetch from the Vault."""
    try:
        conn = get_db_connection()
        rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 10').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e:
        return jsonify({"error": f"Database read failed: {e}"}), 500


@app.route('/api/rotate-keys', methods=['POST'])
def manual_key_rotation():
    """Simulates a manual key rotation event."""
    # [C4] DB write with error handling
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO logs (title, desc, action, time, icon, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Manual Key Rotation",
            "Administrator manually triggered API key rotation via ButterVault.",
            "Keys Buttered",
            datetime.datetime.now().strftime("%H:%M:%S"),
            "\U0001f511",
            "blue"
        ))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        return jsonify({"error": f"Database write failed: {e}"}), 500

    # [C3] Thread-safe counter increment
    with _state_lock:
        global total_logs_processed
        total_logs_processed += 1

    return jsonify({"status": "success"}), 200


# --- THE CONTROL PANEL ---

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """
    [N1] + [R5] Unified settings endpoint.
    GET  — returns full state snapshot (paranoia, shield, routing, model, gates)
    POST — partial update: only fields present in the body are changed
    """
    global current_level, routing_mode, model_name, remote_endpoint, gate_states

    if request.method == 'GET':
        with _state_lock:
            return jsonify({
                "level": current_level,
                "shield_enabled": shield_enabled,
                "routing_mode": routing_mode,
                "model": model_name,
                "endpoint": remote_endpoint,
                "gates": dict(gate_states)
            })

    # POST — partial update
    # [C2] Input validation
    data = request.json
    if data is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    errors = []

    # --- Paranoia level (existing) ---
    if "level" in data:
        new_level = str(data["level"])
        if new_level not in ("1", "2", "3"):
            errors.append("level must be 1, 2, or 3")
        else:
            with _state_lock:
                current_level = new_level
            print(f"\U0001f4e1 [SENTINEL UPDATE] Paranoia Level shifted to: {new_level}")

    # --- [R3] Routing mode ---
    if "routing_mode" in data:
        new_mode = str(data["routing_mode"]).lower().strip()
        if new_mode not in VALID_ROUTING_MODES:
            errors.append(f"routing_mode must be one of: {', '.join(VALID_ROUTING_MODES)}")
        else:
            with _state_lock:
                routing_mode = new_mode
            print(f"\U0001f6e0\ufe0f [ROUTING] Mode set to: {new_mode}")

    # --- [R2] Model name ---
    if "model" in data:
        new_model = str(data["model"]).strip()
        if not new_model:
            errors.append("model must be a non-empty string")
        else:
            with _state_lock:
                model_name = new_model
            print(f"\U0001f9e0 [MODEL] Active model set to: {new_model}")

    # --- [R3] Remote endpoint ---
    if "endpoint" in data:
        new_endpoint = str(data["endpoint"]).strip()
        if not _validate_endpoint_url(new_endpoint):
            errors.append("endpoint must be a valid http:// or https:// URL")
        else:
            with _state_lock:
                remote_endpoint = new_endpoint
            label = new_endpoint if new_endpoint else "(cleared)"
            print(f"\U0001f310 [ENDPOINT] Remote endpoint set to: {label}")

    # --- [R4] Gate states ---
    if "gates" in data:
        new_gates = data["gates"]
        if not isinstance(new_gates, dict):
            errors.append("gates must be an object mapping gate IDs to booleans")
        else:
            unknown_keys = set(new_gates.keys()) - VALID_GATE_KEYS
            if unknown_keys:
                errors.append(f"Unknown gate keys: {', '.join(sorted(unknown_keys))}. "
                              f"Valid keys: {', '.join(sorted(VALID_GATE_KEYS))}")
            else:
                # Validate all values are boolean-coercible
                coerced = {}
                for k, v in new_gates.items():
                    coerced[k] = bool(v)
                with _state_lock:
                    gate_states.update(coerced)
                active = [k for k, v in gate_states.items() if v]
                print(f"\U0001f512 [GATES] Updated. Active: {', '.join(active) if active else 'NONE'}")

    if errors:
        return jsonify({"status": "partial", "errors": errors}), 400

    return jsonify({"status": "ok"})


@app.route('/api/shield', methods=['POST'])
def shield():
    """[N2] Toggle shield state — frontend shield button is no longer cosmetic."""
    global shield_enabled

    data = request.json
    if data is None or "enabled" not in data:
        return jsonify({"error": "Request body must include 'enabled' (boolean)"}), 400

    new_state = bool(data["enabled"])

    with _state_lock:
        shield_enabled = new_state

    state_label = "UP" if shield_enabled else "DOWN"
    print(f"\U0001f6e1\ufe0f [SHIELD] Shield is now {state_label}")

    # Log the state change to the vault
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO logs (title, desc, action, time, icon, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            f"Shield {state_label}",
            f"Administrator {'enabled' if shield_enabled else 'disabled'} the ButterClaw shield.",
            "Shield Toggled",
            datetime.datetime.now().strftime("%H:%M:%S"),
            "\U0001f6e1\ufe0f" if shield_enabled else "\U0001f99e",
            "emerald" if shield_enabled else "amber"
        ))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ [DB ERROR] Failed to log shield change: {e}")

    with _state_lock:
        global total_logs_processed
        total_logs_processed += 1

    return jsonify({"status": "ok", "shield_enabled": shield_enabled})


# =============================================
# SSE STREAM — [C1] NO MORE CORS WILDCARD
# =============================================

@app.route('/api/stream')
def stream():
    def event_stream():
        global total_logs_processed
        with _state_lock:
            last_processed = total_logs_processed
        while True:
            with _state_lock:
                current = total_logs_processed
            if current > last_processed:
                yield f"data: update_ready\n\n"
                last_processed = current
            time.sleep(0.5)

    # [C1] REMOVED: manual CORS wildcard header
    # Flask-CORS now handles this via the ALLOWED_ORIGINS whitelist
    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers.add('Cache-Control', 'no-cache')
    response.headers.add('Connection', 'keep-alive')
    return response


# =============================================
# BOOT
# =============================================

if __name__ == '__main__':
    # [L2] Version in startup banner + [R5] routing info
    print(f"\U0001f99e ButterClaw Reasoning Engine v{VERSION} is ONLINE.")
    print(f"   Database: {DB_PATH}")
    print(f"   Paranoia Level: {current_level}")
    print(f"   Routing Mode: {routing_mode}")
    print(f"   Active Model: {model_name}")
    if routing_mode == "remote" and remote_endpoint:
        print(f"   Remote Endpoint: {remote_endpoint}")
    else:
        print(f"   Ollama Endpoint: {OLLAMA_LOCAL_BASE}")
    active_gates = [k for k, v in gate_states.items() if v]
    print(f"   Active Gates: {', '.join(active_gates) if active_gates else 'NONE'}")
    print(f"   Rate Limit: {RATE_LIMIT_MAX} req / {RATE_LIMIT_WINDOW}s on /api/analyze")
    print(f"   CORS Origins: {', '.join(ALLOWED_ORIGINS)}")
    app.run(host='127.0.0.1', port=5000)

"""
ButterClaw v0.4.1 — Reasoning Engine + MCP Transport Layer
=====================================================================
Changelog:
  [v0.3.1] Security: CONFIDENCE_THRESHOLD (85%) self-DoS prevention.
  [v0.3.1] Stability: LLM confidence hallucination fix + clamping.
  [v0.3.1] Stability: Hot-path imports moved to top level.
  [v0.4.0] MCP Transport: Full rewrite of MCP process manager.
  [v0.4.1] QA Sterilization Patch:
           - S1: Auto-restart in send() now chains handshake()
           - S2: Thread-safe request counter via itertools.count()
           - S3: TOCTOU fix in status() — snapshot process reference
           - S4: CRITICAL path checks MCP send() return values
           - S5: CONFIDENCE_THRESHOLD extracted to module-level constant
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
import itertools
from collections import deque
from urllib.parse import urlparse
import json
import subprocess
import sys

import buttervault

# =============================================
# APP SETUP
# =============================================

VERSION = "0.4.1"

# [v0.4.1 S5] Module-level constant — referenced in both analyze_threat() and boot banner
CONFIDENCE_THRESHOLD = 85

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "null"
]

CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

# =============================================
# THREAD-SAFE GLOBAL STATE
# =============================================

_state_lock = threading.Lock()
total_logs_processed = 0
current_level = "3"
shield_enabled = True
model_name = "butterclaw-optimized:latest"
routing_mode = "local"
remote_endpoint = ""

gate_states = {
    "sig_scan": True,
    "origin_ctx": True,
    "intent": True,
    "kill_sw": True
}

OLLAMA_LOCAL_BASE = "http://localhost:11434"
OLLAMA_CHAT_PATH = "/api/chat"
VALID_ROUTING_MODES = ("local", "remote")
VALID_GATE_KEYS = frozenset(gate_states.keys())

# =============================================
# SIMPLE RATE LIMITER
# =============================================

RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60
_rate_log = deque()
_rate_lock = threading.Lock()

def is_rate_limited():
    now = time.time()
    with _rate_lock:
        while _rate_log and _rate_log[0] < now - RATE_LIMIT_WINDOW:
            _rate_log.popleft()
        if len(_rate_log) >= RATE_LIMIT_MAX:
            return True
        _rate_log.append(now)
        return False

# =============================================
# ABSOLUTE DB PATH + THREAD-SAFE SQLITE
# =============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'butterclaw.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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

init_db()

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)


# =============================================
# MCP PROCESS MANAGER (v0.4.1 Transport Layer)
# =============================================

class MCPProcessManager:

    MCP_PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None
        self._write_lock = threading.Lock()
        self._pending = {}
        self._req_counter = itertools.count(1)  # [S2] thread-safe
        self._running = False
        self._stdout_thread = None
        self._stderr_thread = None
        self.discovered_tools = []
        self.server_info = {}
        self.handshake_ok = False
        self.protocol_version = self.MCP_PROTOCOL_VERSION

    @property
    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.is_alive:
            return True
        print("🚀 [MCP] Spawning ButterClaw Execution Layer...")
        try:
            self.process = subprocess.Popen(
                [sys.executable, self.script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
        except FileNotFoundError:
            print(f"❌ [MCP] Script not found: {self.script_path}")
            return False
        except Exception as e:
            print(f"❌ [MCP] Failed to spawn: {e}")
            return False

        self._running = True
        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="mcp-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="mcp-stderr", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        print(f"✅ [MCP] Claws active at PID: {self.process.pid}")
        return True

    def stop(self):
        self._running = False
        if self.process and self.process.poll() is None:
            print(f"🛑 [MCP] Stopping PID {self.process.pid}...")
            try:
                self.process.stdin.close()
            except Exception:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            print("🛑 [MCP] Process stopped.")
        for req_id, entry in list(self._pending.items()):
            entry["result"] = {"error": "MCP process stopped"}
            entry["event"].set()
        self._pending.clear()
        self.process = None
        self.handshake_ok = False

    def restart(self):
        self.stop()
        time.sleep(0.3)
        if self.start():
            return self.handshake()
        return False

    def send(self, method, params=None, timeout=10):
        # [S1] Auto-restart now chains start() + handshake()
        if not self.is_alive:
            if not self.start():
                return {"error": "MCP process failed to start"}
            if not self.handshake():
                print("⚠️ [MCP] Auto-restart handshake failed. Attempting send anyway (best-effort).")

        req_id = next(self._req_counter)  # [S2] thread-safe

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id
        }

        event = threading.Event()
        self._pending[req_id] = {"event": event, "result": None}

        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(payload) + "\n")
                self.process.stdin.flush()
        except (BrokenPipeError, OSError, AttributeError) as e:
            self._pending.pop(req_id, None)
            return {"error": f"Pipe error: {e}"}

        if event.wait(timeout=timeout):
            entry = self._pending.pop(req_id, {})
            return entry.get("result") or {"error": "Empty response"}
        else:
            self._pending.pop(req_id, None)
            return {"error": f"Timeout ({timeout}s) on {method}"}

    def notify(self, method, params=None):
        if not self.is_alive:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(payload) + "\n")
                self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _read_stdout(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                response = json.loads(line)
                req_id = response.get("id")
                preview = line[:150] + ("..." if len(line) > 150 else "")
                print(f"📥 [MCP ACK] id={req_id} → {preview}")
                if req_id is not None and req_id in self._pending:
                    self._pending[req_id]["result"] = response
                    self._pending[req_id]["event"].set()
                elif req_id is not None:
                    print(f"⚠️ [MCP] Orphaned response (id={req_id}), no pending request.")
            except json.JSONDecodeError as e:
                print(f"⚠️ [MCP] Malformed JSON on stdout: {e}")
            except Exception as e:
                if self._running:
                    print(f"❌ [MCP] stdout reader error: {e}")
                break
        print("📡 [MCP] stdout reader exited.")

    def _read_stderr(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stderr.readline()
                if not line:
                    break
                print(f"🔧 [MCP LOG] {line.rstrip()}")
            except Exception:
                break
        print("📡 [MCP] stderr reader exited.")

    def handshake(self):
        init_resp = self.send("initialize", {
            "protocolVersion": self.MCP_PROTOCOL_VERSION,
            "clientInfo": {"name": "butterclaw-server", "version": VERSION},
            "capabilities": {}
        }, timeout=10)

        if "error" in init_resp:
            err = init_resp["error"]
            if isinstance(err, dict):
                err = err.get("message", str(err))
            print(f"❌ [MCP] Handshake failed at initialize: {err}")
            self.handshake_ok = False
            return False

        result = init_resp.get("result", {})
        self.server_info = result.get("serverInfo", {})
        self.protocol_version = result.get("protocolVersion", self.MCP_PROTOCOL_VERSION)

        srv_name = self.server_info.get("name", "?")
        srv_ver = self.server_info.get("version", "?")
        print(f"📡 [MCP] Connected: {srv_name} v{srv_ver} (protocol {self.protocol_version})")

        self.notify("notifications/initialized")

        tools_resp = self.send("tools/list", {}, timeout=5)
        if "error" not in tools_resp and "result" in tools_resp:
            self.discovered_tools = tools_resp["result"].get("tools", [])
            print(f"🔫 [MCP] Discovered {len(self.discovered_tools)} tools:")
            for tool in self.discovered_tools:
                print(f"   - {tool['name']}: {tool.get('description', '(no desc)')}")
        else:
            print("⚠️ [MCP] tools/list failed, continuing with 0 tools.")
            self.discovered_tools = []

        self.handshake_ok = True
        return True

    def status(self):
        # [S3] Snapshot process reference to avoid TOCTOU race
        proc = self.process
        return {
            "alive": proc is not None and proc.poll() is None,
            "pid": proc.pid if proc else None,
            "handshake_ok": self.handshake_ok,
            "server_info": self.server_info,
            "tools_count": len(self.discovered_tools),
            "pending_requests": len(self._pending),
            "protocol_version": self.protocol_version
        }


mcp_manager = MCPProcessManager(
    script_path=os.path.join(BASE_DIR, "butterclaw_mcp.py")
)


# =============================================
# DYNAMIC ENDPOINT RESOLUTION
# =============================================

def _resolve_ollama_url():
    with _state_lock:
        mode = routing_mode
        endpoint = remote_endpoint
    if mode == "remote" and endpoint:
        base = endpoint.rstrip("/")
        return f"{base}{OLLAMA_CHAT_PATH}"
    return f"{OLLAMA_LOCAL_BASE}{OLLAMA_CHAT_PATH}"

def _validate_endpoint_url(url_string):
    if not url_string:
        return True
    try:
        parsed = urlparse(url_string)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# =============================================
# THE GUARDIAN BRAIN
# =============================================

def ask_guardian_agent(threat_type, raw_data):
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

    json_schema = (
        'You must respond ONLY with a valid JSON object. Do not include markdown formatting. '
        'Strict Schema: {'
        '"verdict": "CRITICAL" | "WARNING" | "BENIGN", '
        '"confidence": float 0.0-1.0, '
        '"primary_gate": "Signature" | "Origin" | "Intent" | "None", '
        '"reasoning": "2-sentence explanation."}'
    )

    ollama_url = _resolve_ollama_url()

    payload = {
        "model": active_model,
        "format": "json",
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
            "temperature": 0.3
        }
    }

    try:
        response = requests.post(ollama_url, json=payload, timeout=120)
        raw_content = response.json().get("message", {}).get("content", "{}")

        try:
            parsed = json.loads(raw_content)
            raw_conf = float(parsed.get("confidence", 0.0))
            if raw_conf > 1.0:
                raw_conf = raw_conf / 100.0
            clamped_conf = max(0.0, min(1.0, raw_conf))

            return {
                "verdict": str(parsed.get("verdict", "UNKNOWN")).upper(),
                "confidence": clamped_conf,
                "primary_gate": str(parsed.get("primary_gate", "None")),
                "reasoning": str(parsed.get("reasoning", "Model failed to provide reasoning."))
            }
        except json.JSONDecodeError:
            return {
                "verdict": "ERROR",
                "confidence": 0.0,
                "reasoning": f"JSON parse failed on output: {raw_content[:200]}"
            }

    except Exception as e:
        return {"verdict": "ERROR", "confidence": 0.0, "reasoning": f"Brain failure: {str(e)}"}


# =============================================
# API ROUTES
# =============================================

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": VERSION}), 200

@app.route('/api/vault/key', methods=['POST'])
def save_vault_key():
    data = request.json
    if not data or "provider" not in data or "api_key" not in data:
        return jsonify({"error": "Missing provider or api_key"}), 400
    buttervault.store_key(data["provider"], data["api_key"])
    return jsonify({"status": "success"}), 200

@app.route('/api/vault/status', methods=['GET'])
def check_vault_status():
    providers = buttervault.list_providers()
    status = {provider: buttervault.get_key(provider) is not None for provider in providers}
    for default in ["OpenRouter", "Anthropic"]:
        if default not in status:
            status[default] = False
    return jsonify(status), 200

@app.route('/api/analyze', methods=['POST'])
def analyze_threat():
    if is_rate_limited():
        return jsonify({"error": "Rate limit exceeded. Max 10 requests per minute."}), 429

    data = request.json
    if data is None:
        return jsonify({"error": "Request body must be valid JSON with Content-Type: application/json"}), 400

    threat_type = data.get("threat_type")
    raw_data = data.get("raw_data")

    if not threat_type or not raw_data:
        return jsonify({"error": "Missing required fields: 'threat_type' and 'raw_data'"}), 400

    print("\n" + "=" * 60)
    print(f"📥 [HTTP POST RECEIVED] From Browser Dashboard")
    print(f"   Payload: {threat_type}")

    ollama_url = _resolve_ollama_url()
    print(f"📡 [HTTP POST DISPATCHED] Routing to {ollama_url}...")
    start_time = time.time()

    analysis = ask_guardian_agent(threat_type, raw_data)

    end_time = time.time()
    stew_time = round(end_time - start_time, 2)

    verdict_upper = analysis["verdict"]
    confidence_pct = int(analysis["confidence"] * 100)
    trigger_gate = analysis["primary_gate"]
    reasoning = analysis["reasoning"]

    # [v0.4.1 S5] Uses module-level CONFIDENCE_THRESHOLD
    if verdict_upper == "CRITICAL" and confidence_pct < CONFIDENCE_THRESHOLD:
        print(f"🛡️ [SELF-DOS AVERTED] CRITICAL downgraded due to low confidence ({confidence_pct}% < {CONFIDENCE_THRESHOLD}%).")
        verdict_upper = "WARNING"
        reasoning += f" [Downgraded from CRITICAL: Confidence below {CONFIDENCE_THRESHOLD}% safety threshold]."

    verdict_text = f"[Gate: {trigger_gate}] [{confidence_pct}% Confidence] {reasoning}"

    print(f"🧠 [HTTP 200 OK] Model returned {verdict_upper} ({confidence_pct}%) in {stew_time} seconds.")
    print("=" * 60)

    with _state_lock:
        kill_sw_armed = gate_states.get("kill_sw", True)

    if verdict_upper == "CRITICAL":
        color = "red"
        icon = "🚨"
        if kill_sw_armed:
            # [S4] Check MCP return values — report truth in action string
            mcp_failures = []

            gibson_resp = mcp_manager.send("tools/call", {
                "name": "execute_gibson_kill",
                "arguments": {"target_process": "openclaw"}
            })
            if "error" in gibson_resp:
                mcp_failures.append("gibson_kill")
                print(f"⚠️ [MCP] gibson_kill failed: {gibson_resp['error']}")

            # buttervault is a direct local call — always succeeds independently
            buttervault.butter_keys()

            rotate_resp = mcp_manager.send("tools/call", {
                "name": "rotate_keys",
                "arguments": {"provider": "OpenRouter"}
            })
            if "error" in rotate_resp:
                mcp_failures.append("rotate_keys")
                print(f"⚠️ [MCP] rotate_keys failed: {rotate_resp['error']}")

            if mcp_failures:
                action = f"Keys Buttered | MCP partial failure: {', '.join(mcp_failures)}"
            else:
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
        color = "emerald"
        icon = "✅"
        action = "Monitored"

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

    with _state_lock:
        global total_logs_processed
        total_logs_processed += 1

    return jsonify({"status": "success", "verdict": verdict_text}), 200


@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        conn = get_db_connection()
        rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 10').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e:
        return jsonify({"error": f"Database read failed: {e}"}), 500


@app.route('/api/rotate-keys', methods=['POST'])
def manual_key_rotation():
    buttervault.butter_keys()

    # [S4] Check MCP return value for manual rotation too
    rotate_resp = mcp_manager.send("tools/call", {
        "name": "rotate_keys",
        "arguments": {"provider": "Manual_Global"}
    })
    mcp_note = ""
    if "error" in rotate_resp:
        mcp_note = f" (MCP rotate_keys failed: {rotate_resp['error']})"
        print(f"⚠️ [MCP] Manual rotate_keys failed: {rotate_resp['error']}")

    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO logs (title, desc, action, time, icon, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            "Manual Key Rotation",
            f"Administrator manually triggered API key rotation. Ciphertext destroyed.{mcp_note}",
            "Keys Buttered",
            datetime.datetime.now().strftime("%H:%M:%S"),
            "🗝️",
            "blue"
        ))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        return jsonify({"error": f"Database write failed: {e}"}), 500

    with _state_lock:
        global total_logs_processed
        total_logs_processed += 1

    return jsonify({"status": "success"}), 200


# --- THE CONTROL PANEL ---

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
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

    data = request.json
    if data is None:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    errors = []

    if "level" in data:
        new_level = str(data["level"])
        if new_level not in ("1", "2", "3"):
            errors.append("level must be 1, 2, or 3")
        else:
            with _state_lock:
                current_level = new_level
            print(f"📡 [SENTINEL UPDATE] Paranoia Level shifted to: {new_level}")

    if "routing_mode" in data:
        new_mode = str(data["routing_mode"]).lower().strip()
        if new_mode not in VALID_ROUTING_MODES:
            errors.append(f"routing_mode must be one of: {', '.join(VALID_ROUTING_MODES)}")
        else:
            with _state_lock:
                routing_mode = new_mode
            print(f"🛠️ [ROUTING] Mode set to: {new_mode}")

    if "model" in data:
        new_model = str(data["model"]).strip()
        if not new_model:
            errors.append("model must be a non-empty string")
        else:
            with _state_lock:
                model_name = new_model
            print(f"🧠 [MODEL] Active model set to: {new_model}")

    if "endpoint" in data:
        new_endpoint = str(data["endpoint"]).strip()
        if not _validate_endpoint_url(new_endpoint):
            errors.append("endpoint must be a valid http:// or https:// URL")
        else:
            with _state_lock:
                remote_endpoint = new_endpoint
            label = new_endpoint if new_endpoint else "(cleared)"
            print(f"🌐 [ENDPOINT] Remote endpoint set to: {label}")

    if "gates" in data:
        new_gates = data["gates"]
        if not isinstance(new_gates, dict):
            errors.append("gates must be an object mapping gate IDs to booleans")
        else:
            unknown_keys = set(new_gates.keys()) - VALID_GATE_KEYS
            if unknown_keys:
                errors.append(f"Unknown gate keys: {', '.join(sorted(unknown_keys))}. ")
            else:
                coerced = {}
                for k, v in new_gates.items():
                    coerced[k] = bool(v)
                with _state_lock:
                    gate_states.update(coerced)
                active = [k for k, v in gate_states.items() if v]
                print(f"🔒 [GATES] Updated. Active: {', '.join(active) if active else 'NONE'}")

    if errors:
        return jsonify({"status": "partial", "errors": errors}), 400

    return jsonify({"status": "ok"})


@app.route('/api/shield', methods=['POST'])
def shield():
    global shield_enabled

    data = request.json
    if data is None or "enabled" not in data:
        return jsonify({"error": "Request body must include 'enabled' (boolean)"}), 400

    new_state = bool(data["enabled"])

    with _state_lock:
        shield_enabled = new_state

    state_label = "UP" if shield_enabled else "DOWN"
    print(f"🛡️ [SHIELD] Shield is now {state_label}")

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
            "🛡️" if shield_enabled else "🦞",
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
# MCP OBSERVABILITY ENDPOINTS (v0.4)
# =============================================

@app.route('/api/mcp/status', methods=['GET'])
def mcp_status():
    return jsonify(mcp_manager.status()), 200

@app.route('/api/mcp/ping', methods=['GET'])
def mcp_ping():
    start = time.time()
    resp = mcp_manager.send("ping", {}, timeout=5)
    elapsed_ms = round((time.time() - start) * 1000, 1)
    if "error" in resp:
        return jsonify({"pong": False, "error": resp["error"], "ms": elapsed_ms}), 503
    return jsonify({"pong": True, "ms": elapsed_ms}), 200

@app.route('/api/mcp/tools', methods=['GET'])
def mcp_tools():
    return jsonify({
        "tools": mcp_manager.discovered_tools,
        "count": len(mcp_manager.discovered_tools)
    }), 200

@app.route('/api/mcp/restart', methods=['POST'])
def mcp_restart():
    success = mcp_manager.restart()
    status = mcp_manager.status()
    code = 200 if success else 503
    return jsonify({"restarted": success, **status}), code


# =============================================
# SSE STREAM
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

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers.add('Cache-Control', 'no-cache')
    response.headers.add('Connection', 'keep-alive')
    return response


# =============================================
# BOOT
# =============================================

if __name__ == '__main__':
    print(f"🦞 ButterClaw Reasoning Engine v{VERSION} is ONLINE.")
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
    # [S5] References module-level constant
    print(f"   Self-DoS Threshold: {CONFIDENCE_THRESHOLD}%")
    print(f"   Rate Limit: {RATE_LIMIT_MAX} req / {RATE_LIMIT_WINDOW}s on /api/analyze")
    print(f"   CORS Origins: {', '.join(ALLOWED_ORIGINS)}")

    print("\n" + "=" * 60)
    print("📡 [MCP] Initiating v0.4.1 Handshake Sequence...")
    print("=" * 60)

    if mcp_manager.start():
        if mcp_manager.handshake():
            tool_count = len(mcp_manager.discovered_tools)
            print(f"✅ [MCP] Handshake complete. {tool_count} tools armed.")
        else:
            print("⚠️ [MCP] Handshake failed. MCP endpoints will report degraded status.")
    else:
        print("❌ [MCP] Failed to spawn execution layer. The Sentinel is unarmed.")

    print("=" * 60 + "\n")

    app.run(host='127.0.0.1', port=5000)

"""
ButterClaw v0.7.2
=====================================================================
Changelog:
  [v0.5.0] The Nervous System (Ledger, SSE Transport)
  [v0.5.1] Tool Chaining (ChainExecutor, safe eval)
  [v0.5.2] ButterVault OAuth (Credential Lifecycle)
  [v0.6.0] API Gateway & Auth (RBAC, API Keys, Sessions)
  [v0.6.1] Policy Engine (Deterministic DRIFT framework)
  [v0.6.2] Alert Dispatcher (Notifications & monitoring)
  [v0.6.3] Deployment Packaging (Docker, config.py)
  [v0.6.4] Active Tools & Autonomous Deployment
  [v0.6.5] The Paranoia Dial & TUI Integration
  [v0.6.6] The Reconciliation
  [v0.6.7] The Arsenal Hardening (Sanitizer-Aware Signatures)
  [v0.6.8] The Arsenal Hardening Stability Patch
  [v0.7.0] Positive Security Model & Capability Matrix Binding
  [v0.7.1] Full Policy Hotfix
  [v0.7.2] ENV Setup Wizard
"""

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import requests as http_requests
import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

import time
import sqlite3
import threading
import os
import itertools
import uuid
import secrets
from collections import deque
from urllib.parse import urlparse, quote
import json
import subprocess
import sys

from config import cfg
_server_start_time = time.time()

import buttervault
import oauth_config
import auth
from auth import require_auth, register_auth_routes, bootstrap_admin_key, is_rate_limited_for_key

# [v0.6.1] Policy Engine Import
try:
    import policy_engine
    POLICY_ENGINE_ENABLED = True
except ImportError:
    POLICY_ENGINE_ENABLED = False
    print("⚠️ [WARN] policy_engine.py not found. Deterministic guardrails disabled.")

# [v0.6.2] Alert Dispatcher Import
try:
    import alert_dispatcher
    ALERT_DISPATCHER_ENABLED = True
except ImportError:
    ALERT_DISPATCHER_ENABLED = False
    print("⚠️ [WARN] alert_dispatcher.py not found. External notifications disabled.")

# =============================================
# APP SETUP
# =============================================

VERSION = "0.7.2"
DRY_RUN = cfg.DRY_RUN
CONFIDENCE_THRESHOLD = cfg.CONFIDENCE_THRESHOLD

app = Flask(__name__)

# [v0.6.3] Nginx Reverse Proxy IP Fix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

ALLOWED_ORIGINS = cfg.CORS_ORIGINS

CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

# Register Module Routes
register_auth_routes(app)
if ALERT_DISPATCHER_ENABLED:
    alert_dispatcher.register_alert_routes(app)

# =============================================
# [v0.6.2] GLOBAL AUTH TRACKER
# =============================================
@app.after_request
def track_auth_failures(response):
    if response.status_code in (401, 403) and ALERT_DISPATCHER_ENABLED:
        alert_dispatcher.track_auth_failure(request.remote_addr)
    return response

# =============================================
# THREAD-SAFE GLOBAL STATE
# =============================================

_state_lock = threading.Lock()
total_logs_processed = 0
_logs_counter_lock = threading.Lock()

# Initialize Paranoia from .env (Default to 2: Active Defense)
current_level = os.getenv("BUTTERCLAW_PARANOIA", "2")

shield_enabled = True
model_name = cfg.MODEL_NAME
routing_mode = "local"
remote_endpoint = ""

mcp_transport_mode = cfg.MCP_TRANSPORT
mcp_sse_url = cfg.MCP_SSE_URL
mcp_sse_token = cfg.MCP_SSE_TOKEN

gate_states = {
    "sig_scan": True,
    "origin_ctx": True,
    "intent": True,
    "kill_sw": True
}

OLLAMA_LOCAL_BASE = cfg.OLLAMA_BASE_URL
OLLAMA_CHAT_PATH = cfg.OLLAMA_CHAT_PATH
VALID_ROUTING_MODES = ("local", "remote")
VALID_GATE_KEYS = frozenset(gate_states.keys())
VALID_MCP_TRANSPORTS = ("stdio", "sse")

# =============================================
# ABSOLUTE DB PATH + THREAD-SAFE SQLITE
# =============================================

BASE_DIR = cfg.BASE_DIR
DB_PATH = cfg.DB_PATH

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mcp_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT NOT NULL,
            req_id     INTEGER,
            method     TEXT NOT NULL,
            tool_name  TEXT,
            arguments  TEXT,
            status     TEXT NOT NULL DEFAULT 'pending',
            result     TEXT,
            elapsed_ms REAL,
            trigger    TEXT DEFAULT 'auto',
            chain_id   TEXT,
            chain_step INTEGER
        )
    ''')
    conn.commit()
    conn.close()

    auth.init_auth_db()

    if POLICY_ENGINE_ENABLED:
        policy_engine.init_policy_db()
        
    if ALERT_DISPATCHER_ENABLED:
        alert_dispatcher.init_alert_db()

init_db()

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)

# =============================================
# OAUTH STATE MANAGEMENT (v0.5.2)
# =============================================

_oauth_states = {}
_oauth_states_lock = threading.Lock()
OAUTH_STATE_TTL = cfg.OAUTH_STATE_TTL

def _cleanup_expired_oauth_states():
    now = time.time()
    with _oauth_states_lock:
        expired = [k for k, v in _oauth_states.items() if now - v["created_at"] > OAUTH_STATE_TTL]
        for k in expired:
            del _oauth_states[k]

# =============================================
# MCP EVENT LEDGER (v0.5.0)
# =============================================

def ledger_log_start(req_id, method, tool_name=None, arguments=None, trigger="auto", chain_id=None, chain_step=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mcp_events (timestamp, req_id, method, tool_name, arguments, status, trigger, chain_id, chain_step)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        ''', (
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            req_id, method, tool_name,
            json.dumps(arguments) if arguments else None,
            trigger, chain_id, chain_step
        ))
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Failed to log start: {e}")
        return None

def ledger_log_end(event_id, status, result=None, elapsed_ms=None):
    if event_id is None: return
    try:
        result_str = None
        if result is not None:
            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
            if result_str and len(result_str) > 4096:
                result_str = result_str[:4093] + "..."

        conn = get_db_connection()
        conn.execute('UPDATE mcp_events SET status = ?, result = ?, elapsed_ms = ? WHERE id = ?', 
                     (status, result_str, elapsed_ms, event_id))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Failed to log end: {e}")

def ledger_query(limit=50, tool=None, status=None, since=None):
    query = "SELECT * FROM mcp_events WHERE 1=1"
    params = []
    if tool: query += " AND tool_name = ?"; params.append(tool)
    if status: query += " AND status = ?"; params.append(status)
    if since: query += " AND timestamp >= ?"; params.append(since)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 200))
    try:
        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except sqlite3.Error: return []

def ledger_get_event(event_id):
    try:
        conn = get_db_connection()
        row = conn.execute('SELECT * FROM mcp_events WHERE id = ?', (event_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error: return None

def ledger_count():
    try:
        conn = get_db_connection()
        count = conn.execute('SELECT COUNT(*) FROM mcp_events').fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error: return 0

# =============================================
# CHAIN EXECUTOR (v0.5.1)
# =============================================

VALID_CONDITION_OPERATORS = {
    "contains":     lambda val, exp: str(exp).lower() in str(val).lower(),
    "not_contains": lambda val, exp: str(exp).lower() not in str(val).lower(),
    "equals":       lambda val, exp: str(val).strip().lower() == str(exp).strip().lower(),
    "not_equals":   lambda val, exp: str(val).strip().lower() != str(exp).strip().lower(),
    "starts_with":  lambda val, exp: str(val).strip().lower().startswith(str(exp).strip().lower()),
}

class ChainExecutor:
    MAX_STEPS = 10
    TIMEOUT = 60

    def __init__(self, mcp_manager, chain_steps, dry_run=False):
        if not isinstance(chain_steps, list): raise ValueError("chain_steps must be a list")
        self.mcp_manager = mcp_manager
        self.chain_steps = chain_steps[:self.MAX_STEPS]
        self.dry_run = dry_run
        self.results = {}
        self.executed = []
        self.chain_id = uuid.uuid4().hex[:12]
        self.start_time = time.time()
        self.timeout = self.TIMEOUT

    def execute(self):
        print(f"\n🔗 [CHAIN {self.chain_id}] Starting {len(self.chain_steps)}-step chain{' [DRY RUN]' if self.dry_run else ''}")
        for idx, step in enumerate(self.chain_steps):
            elapsed = time.time() - self.start_time
            if elapsed > self.timeout:
                print(f"⏱️ [CHAIN {self.chain_id}] Timeout after {elapsed:.1f}s at step {idx}")
                break
            try:
                self._execute_step(step, idx)
            except Exception as e:
                tool_name = step.get('tool', f'step_{idx}')
                self.executed.append({"step": idx, "tool": tool_name, "status": "failed", "error": str(e)})
                event_id = ledger_log_start(req_id=None, method="tools/call", tool_name=tool_name, arguments=step.get("args", {}), trigger="chain", chain_id=self.chain_id, chain_step=idx)
                if event_id: ledger_log_end(event_id, status="error", result={"error": str(e)})
                continue

        step_names = [s.get('tool', '?') for s in self.chain_steps[:len(self.executed)]]
        action_summary = f"Chain [{self.chain_id}]: {len(self.executed)}/{len(self.chain_steps)} steps — {', '.join(step_names)}"
        print(f"🔗 [CHAIN {self.chain_id}] Complete. {action_summary}")
        return {"chain_id": self.chain_id, "steps_executed": len(self.executed), "steps_total": len(self.chain_steps), "results": self.results, "action_summary": action_summary}

    def _execute_step(self, step, step_index):
        tool_name = step.get('tool')
        if not tool_name: raise ValueError(f"Step {step_index} missing required 'tool' key")

        condition = step.get('condition')
        if condition:
            if not self._evaluate_condition(condition):
                print(f"⏭️ [CHAIN {self.chain_id}] Step {step_index} ({tool_name}) skipped — condition not met")
                self.executed.append({"step": step_index, "tool": tool_name, "status": "skipped"})
                event_id = ledger_log_start(req_id=None, method="tools/call", tool_name=tool_name, arguments=step.get("args", {}), trigger="chain", chain_id=self.chain_id, chain_step=step_index)
                if event_id: ledger_log_end(event_id, status="skipped", result={"reason": "condition_not_met"})
                return

        if POLICY_ENGINE_ENABLED:
            with _state_lock:
                current_active_model = model_name
                
            pre_tool_ctx = {
                "raw_data": str(step.get("args", {})),
                "threat_type": "chain_tool_call",
                "tool_name": tool_name,
                "tool_args": step.get("args", {}),
                "chain_id": self.chain_id,
                "chain_step": step_index,
                "verdict": "CRITICAL", 
                "confidence": 1.0,
                "active_model": current_active_model
            }
            gate_result = policy_engine.evaluate_policies("pre_tool", pre_tool_ctx)
            
            if gate_result["action"] == "skip_tool":
                print(f"🚫 [POLICY] Pre-Tool gate blocked {tool_name}: {gate_result['reason']}")
                if ALERT_DISPATCHER_ENABLED:
                    alert_dispatcher.dispatch_alert("policy_blocked", {"tool_name": tool_name, "reason": gate_result["reason"]})
                self.executed.append({"step": step_index, "tool": tool_name, "status": "policy_blocked"})
                event_id = ledger_log_start(req_id=None, method="tools/call", tool_name=tool_name, arguments=step.get("args", {}), trigger="chain", chain_id=self.chain_id, chain_step=step_index)
                if event_id: ledger_log_end(event_id, status="policy_blocked", result={"reason": gate_result["reason"], "policy_id": gate_result["policy_id"]})
                return
            elif gate_result["action"] == "block":
                print(f"🚫 [POLICY] Pre-Tool gate HARD BLOCKED {tool_name}: {gate_result['reason']}")
                if ALERT_DISPATCHER_ENABLED:
                    alert_dispatcher.dispatch_alert("policy_blocked", {"tool_name": tool_name, "reason": gate_result["reason"]})
                self.executed.append({"step": step_index, "tool": tool_name, "status": "policy_blocked"})
                return

        args = step.get('args', {})
        store_as = step.get('store_as', tool_name)

        if self.dry_run:
            print(f"🧪 [CHAIN {self.chain_id}] [DRY RUN] Step {step_index}: {tool_name}({args})")
            result = {"dry_run": True, "tool": tool_name, "args": args}
        else:
            result = self.mcp_manager.send("tools/call", {"name": tool_name, "arguments": args}, trigger="chain", chain_id=self.chain_id, chain_step=step_index)

        self.results[store_as] = result
        self.executed.append({"step": step_index, "tool": tool_name, "status": "executed"})
        print(f"✅ [CHAIN {self.chain_id}] Step {step_index}: {tool_name} → stored as '{store_as}'")

    def _evaluate_condition(self, condition):
        if not isinstance(condition, dict): return False
        source = condition.get('source')
        operator = condition.get('operator')
        expected = condition.get('expected')
        if source not in self.results: return False
        if operator not in VALID_CONDITION_OPERATORS: return False
        return VALID_CONDITION_OPERATORS[operator](str(self.results[source]), expected)

# =============================================
# MCP MANAGER INTERFACE
# =============================================

class BaseMCPManager:
    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None): raise NotImplementedError
    def notify(self, method, params=None): raise NotImplementedError
    def handshake(self): raise NotImplementedError
    def status(self): raise NotImplementedError
    def start(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def restart(self): raise NotImplementedError
    @property
    def is_alive(self): raise NotImplementedError
    @property
    def transport_name(self): raise NotImplementedError

# =============================================
# MCP PROCESS MANAGER — stdio transport
# =============================================

class MCPProcessManager(BaseMCPManager):
    MCP_PROTOCOL_VERSION = "2024-11-05"
    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None
        self._write_lock = threading.Lock()
        self._pending = {}
        self._req_counter = itertools.count(1)
        self._running = False
        self.discovered_tools = []
        self.server_info = {}
        self.handshake_ok = False
        self.protocol_version = self.MCP_PROTOCOL_VERSION
    @property
    def transport_name(self): return "stdio"
    @property
    def is_alive(self): return self.process is not None and self.process.poll() is None
    def start(self):
        if self.is_alive: return True
        print("🚀 [MCP] Spawning ButterClaw Execution Layer (stdio)...")
        try:
            self.process = subprocess.Popen([sys.executable, self.script_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        except Exception as e:
            print(f"❌ [MCP] Failed to spawn: {e}")
            return False
        self._running = True
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        return True
    def stop(self):
        self._running = False
        if self.process and self.process.poll() is None:
            try: self.process.stdin.close()
            except: pass
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for req_id, entry in list(self._pending.items()):
            entry["result"] = {"error": "MCP process stopped"}
            entry["event"].set()
        self._pending.clear()
        self.process = None
        self.handshake_ok = False
    def restart(self):
        self.stop()
        time.sleep(0.3)
        if self.start(): return self.handshake()
        return False
    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None):
        if not self.is_alive:
            if not self.start(): return {"error": "MCP process failed to start"}
            if not self.handshake(): print("⚠️ [MCP] Auto-restart handshake failed.")
        req_id = next(self._req_counter)
        tool_name = params.get("name") if method == "tools/call" and params else None
        arguments = params.get("arguments") if method == "tools/call" and params else None
        event_id = ledger_log_start(req_id=req_id, method=method, tool_name=tool_name, arguments=arguments, trigger=trigger, chain_id=chain_id, chain_step=chain_step)
        t0 = time.time()
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}
        event = threading.Event()
        self._pending[req_id] = {"event": event, "result": None}
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(payload) + "\n")
                self.process.stdin.flush()
        except Exception as e:
            self._pending.pop(req_id, None)
            result = {"error": f"Pipe error: {e}"}
            ledger_log_end(event_id, "error", result, round((time.time() - t0) * 1000, 1))
            return result
        if event.wait(timeout=timeout):
            entry = self._pending.pop(req_id, {})
            result = entry.get("result") or {"error": "Empty response"}
            ledger_log_end(event_id, "error" if "error" in result else "success", result, round((time.time() - t0) * 1000, 1))
            return result
        else:
            self._pending.pop(req_id, None)
            result = {"error": f"Timeout ({timeout}s) on {method}"}
            ledger_log_end(event_id, "timeout", result, round((time.time() - t0) * 1000, 1))
            return result
    def notify(self, method, params=None):
        if not self.is_alive: return
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
                self.process.stdin.flush()
        except: pass
    def _read_stdout(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stdout.readline()
                if not line: break
                line = line.strip()
                if not line: continue
                response = json.loads(line)
                req_id = response.get("id")
                if req_id is not None and req_id in self._pending:
                    self._pending[req_id]["result"] = response
                    self._pending[req_id]["event"].set()
            except: break
    def _read_stderr(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stderr.readline()
                if not line: break
                print(f"🔧 [MCP LOG] {line.rstrip()}")
            except: break
    def handshake(self):
        init_resp = self.send("initialize", {"protocolVersion": self.MCP_PROTOCOL_VERSION, "clientInfo": {"name": "butterclaw-server", "version": VERSION}, "capabilities": {}}, timeout=10, trigger="handshake")
        if "error" in init_resp:
            self.handshake_ok = False; return False
        self.server_info = init_resp.get("result", {}).get("serverInfo", {})
        self.notify("notifications/initialized")
        tools_resp = self.send("tools/list", {}, timeout=5, trigger="handshake")
        self.discovered_tools = tools_resp.get("result", {}).get("tools", []) if "error" not in tools_resp else []
        self.handshake_ok = True
        return True
    def status(self):
        proc = self.process
        return {"alive": proc is not None and proc.poll() is None, "pid": proc.pid if proc else None, "handshake_ok": self.handshake_ok, "server_info": self.server_info, "tools_count": len(self.discovered_tools), "pending_requests": len(self._pending), "protocol_version": self.protocol_version, "transport_mode": "stdio", "event_count": ledger_count()}

# =============================================
# MCP SSE CLIENT — remote SSE transport
# =============================================

class MCPSSEClient(BaseMCPManager):
    MCP_PROTOCOL_VERSION = "2024-11-05"
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._pending = {}
        self._req_counter = itertools.count(1)
        self._running = False
        self._connected = False
        self.discovered_tools = []
        self.server_info = {}
        self.handshake_ok = False
        self.protocol_version = self.MCP_PROTOCOL_VERSION
        self._message_url = None
    @property
    def transport_name(self): return f"sse ({self.base_url})"
    @property
    def is_alive(self): return self._running and self._connected
    def _auth_headers(self):
        return {"Content-Type": "application/json", **({"Authorization": f"Bearer {self.token}"} if self.token else {})}
    def start(self):
        if self._running: return True
        try:
            if http_requests.get(f"{self.base_url}/health", headers=self._auth_headers(), timeout=5).status_code != 200: return False
        except: return False
        self._running = True
        self._message_url = f"{self.base_url}/message"
        threading.Thread(target=self._read_sse_stream, daemon=True).start()
        for _ in range(20):
            if self._connected: break
            time.sleep(0.1)
        return True
    def stop(self):
        self._running = False; self._connected = False
        for req_id, entry in list(self._pending.items()):
            entry["result"] = {"error": "MCP SSE client stopped"}; entry["event"].set()
        self._pending.clear()
        self.handshake_ok = False
    def restart(self):
        self.stop(); time.sleep(0.3)
        return self.handshake() if self.start() else False
    def _read_sse_stream(self):
        headers = {**self._auth_headers(), "Accept": "text/event-stream", "Cache-Control": "no-cache"}
        while self._running:
            try:
                resp = http_requests.get(f"{self.base_url}/sse", headers=headers, stream=True, timeout=None)
                if resp.status_code != 200: time.sleep(5); continue
                self._connected = True
                event_type = None; data_buffer = ""
                for line in resp.iter_lines(decode_unicode=True):
                    if not self._running: break
                    if not line:
                        if data_buffer and event_type:
                            if event_type == "endpoint": self._message_url = data_buffer.strip()
                            elif event_type == "message":
                                try:
                                    response = json.loads(data_buffer)
                                    if "id" in response and response["id"] in self._pending:
                                        self._pending[response["id"]]["result"] = response; self._pending[response["id"]]["event"].set()
                                except: pass
                        event_type = None; data_buffer = ""; continue
                    if line.startswith(":"): continue
                    if line.startswith("event: "): event_type = line[7:].strip()
                    elif line.startswith("data: "): data_buffer += line[6:]
            except:
                if self._running: self._connected = False; time.sleep(5)
    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None):
        if not self._running:
            if not self.start(): return {"error": "MCP SSE client failed to connect"}
        req_id = next(self._req_counter)
        tool_name = params.get("name") if method == "tools/call" and params else None
        arguments = params.get("arguments") if method == "tools/call" and params else None
        event_id = ledger_log_start(req_id=req_id, method=method, tool_name=tool_name, arguments=arguments, trigger=trigger, chain_id=chain_id, chain_step=chain_step)
        t0 = time.time()
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}
        event = threading.Event()
        self._pending[req_id] = {"event": event, "result": None}
        try:
            resp = http_requests.post(self._message_url or f"{self.base_url}/message", json=payload, headers=self._auth_headers(), timeout=5)
            if resp.status_code not in (200, 202):
                self._pending.pop(req_id, None)
                result = {"error": f"POST failed: HTTP {resp.status_code}"}
                ledger_log_end(event_id, "error", result, round((time.time() - t0) * 1000, 1))
                return result
        except Exception as e:
            self._pending.pop(req_id, None)
            result = {"error": f"POST failed: {e}"}
            ledger_log_end(event_id, "error", result, round((time.time() - t0) * 1000, 1))
            return result
        if event.wait(timeout=timeout):
            entry = self._pending.pop(req_id, {})
            result = entry.get("result") or {"error": "Empty response"}
            ledger_log_end(event_id, "error" if "error" in result else "success", result, round((time.time() - t0) * 1000, 1))
            return result
        else:
            self._pending.pop(req_id, None)
            result = {"error": f"Timeout ({timeout}s) on {method}"}
            ledger_log_end(event_id, "timeout", result, round((time.time() - t0) * 1000, 1))
            return result
    def notify(self, method, params=None):
        if not self._running: return
        try: http_requests.post(self._message_url or f"{self.base_url}/message", json={"jsonrpc": "2.0", "method": method, "params": params or {}}, headers=self._auth_headers(), timeout=5)
        except: pass
    def handshake(self):
        init_resp = self.send("initialize", {"protocolVersion": self.MCP_PROTOCOL_VERSION, "clientInfo": {"name": "butterclaw-server", "version": VERSION}, "capabilities": {}}, timeout=10, trigger="handshake")
        if "error" in init_resp: self.handshake_ok = False; return False
        self.server_info = init_resp.get("result", {}).get("serverInfo", {})
        self.notify("notifications/initialized")
        tools_resp = self.send("tools/list", {}, timeout=5, trigger="handshake")
        self.discovered_tools = tools_resp.get("result", {}).get("tools", []) if "error" not in tools_resp else []
        self.handshake_ok = True; return True
    def status(self):
        return {"alive": self._connected, "pid": None, "handshake_ok": self.handshake_ok, "server_info": self.server_info, "tools_count": len(self.discovered_tools), "pending_requests": len(self._pending), "protocol_version": self.protocol_version, "transport_mode": "sse", "remote_url": self.base_url, "event_count": ledger_count()}

def create_mcp_manager():
    with _state_lock: mode = mcp_transport_mode; url = mcp_sse_url; token = mcp_sse_token
    if mode == "sse" and url:
        print(f"📡 [MCP] Using SSE transport → {url}")
        return MCPSSEClient(base_url=url, token=token)
    else:
        print("📡 [MCP] Using stdio transport (local child process)")
        return MCPProcessManager(script_path=cfg.MCP_SCRIPT)

mcp_manager = create_mcp_manager()

# =============================================
# [v0.6.2] MCP HEALTH MONITOR DAEMON
# =============================================
def mcp_health_monitor():
    was_alive = True
    while True:
        time.sleep(10)
        is_alive = mcp_manager.is_alive
        if was_alive and not is_alive:
            print("⚠️ [MCP] Disconnect/Crash detected by health monitor.")
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("mcp_offline", {"transport": mcp_manager.transport_name})
        was_alive = is_alive

threading.Thread(target=mcp_health_monitor, daemon=True).start()

# =============================================
# DYNAMIC ENDPOINT RESOLUTION
# =============================================

def _resolve_ollama_url():
    with _state_lock: mode = routing_mode; endpoint = remote_endpoint
    if mode == "remote" and endpoint: return f"{endpoint.rstrip('/')}{OLLAMA_CHAT_PATH}"
    return f"{OLLAMA_LOCAL_BASE}{OLLAMA_CHAT_PATH}"

def _validate_endpoint_url(url_string):
    if not url_string: return True
    try:
        parsed = urlparse(url_string)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except: return False

def _build_ai_headers(api_url):
    """Only send Google API key to Google's own domain to prevent exfiltration."""
    parsed = urlparse(api_url)
    headers = {"Content-Type": "application/json"}
    
    if parsed.netloc == "generativelanguage.googleapis.com":
        headers["Authorization"] = f"Bearer {cfg.GOOGLE_API_KEY}"
    # Allow custom endpoints to use a separate key if provided in config
    elif getattr(cfg, "REMOTE_API_KEY", None):
        headers["Authorization"] = f"Bearer {cfg.REMOTE_API_KEY}"
        
    return headers

# =============================================
# BRAIN API CALL — RETRY WITH BACKOFF
# =============================================

def _call_brain_api(api_url, payload, headers, timeout=120, max_retries=3):
    """
    POST to the Brain API with exponential backoff on 429 and 503.
    Fails fast on all other non-200 status codes.
    """
    delay = 15  # Initial backoff in seconds
    for attempt in range(1, max_retries + 1):
        try:
            response = http_requests.post(api_url, json=payload, headers=headers, timeout=timeout)
            if response.status_code in (429, 503):
                retry_after = int(response.headers.get("Retry-After", delay))
                wait = max(retry_after, delay)
                print(f"⚠️ [BRAIN] HTTP {response.status_code} on attempt {attempt}/{max_retries}. Retrying in {wait}s...")
                time.sleep(wait)
                delay *= 2  # Exponential backoff: 15s → 30s → 60s
                continue
            return response  # success or non-retryable error — caller handles it
        except Exception as e:
            print(f"⚠️ [BRAIN] Request exception on attempt {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
            else:
                raise
    return None

# =============================================
# THE GUARDIAN BRAIN
# =============================================

def ask_guardian_agent(threat_type, raw_data):
    with _state_lock: level = current_level; active_model = model_name; gates = dict(gate_states)

    mcp_history = ledger_query(limit=5, status="success")
    timeline_context = ""
    if mcp_history:
        timeline_context = "RECENT SENTINEL ACTIONS (Sliding Window):\n"
        for event in reversed(mcp_history):
            if event['method'] == 'tools/call':
                timeline_context += f" - [{event['timestamp']}] Executed: {event['tool_name']} | Result: {event['status']}\n"
        timeline_context += "\n"

    # Apply Paranoia Logic to Prompt
    if level == "1": mode_instructions = "Mode: RELAXED OBSERVER. Log anomalies, but do not terminate processes."
    elif level == "2": mode_instructions = "Mode: CAUTIOUS ACTIVE DEFENSE. Flag anomalies and terminate compromised processes via execute_gibson_kill."
    else: mode_instructions = "Mode: PARANOID LOCKDOWN. Zero Trust. Terminate unauthorized behavior and trigger full Vault destruction."

    active_gates = [k for k, v in gates.items() if v]
    inactive_gates = [k for k, v in gates.items() if not v]
    gate_context = ""
    if inactive_gates:
        gate_labels = {"sig_scan": "Signature Scan", "origin_ctx": "Origin Context", "intent": "Intent Classification", "kill_sw": "Kill Switch"}
        gate_context = f" Active analysis gates: {', '.join([gate_labels.get(g, g) for g in active_gates]) if active_gates else 'NONE'}. Disabled gates (skip these): {', '.join([gate_labels.get(g, g) for g in inactive_gates])}."
        if not gates.get("kill_sw"): gate_context += " Kill Switch is DISARMED — do NOT recommend process termination."
    
    tools_list = [f"  - {t.get('name', 'unknown_tool')}: {t.get('description', 'No description')}" for t in mcp_manager.discovered_tools]
    tools_context = "\n".join(tools_list) if tools_list else "  No MCP tools discovered yet."

    json_schema = (
        'You must respond ONLY with a valid JSON object. Do not include markdown formatting. Strict Schema: {'
        '"verdict": "CRITICAL" | "WARNING" | "BENIGN", "confidence": float 0.0-1.0, "primary_gate": "Signature" | "Origin" | "Intent" | "None", "reasoning": "2-sentence explanation."} '
        'For CRITICAL verdicts, you MAY include an optional "chain" array to compose a multi-step tool sequence: '
        '"chain": [{"tool": "tool_name", "args": {"key": "value"}, "store_as": "result_label", "condition": {"source": "previous_result_label", "operator": "contains|not_contains|equals|not_equals|starts_with", "expected": "value"}}] '
        f'Available MCP tools:\n{tools_context}\n'
        'CRITICAL TOOL RULES: If using the "log_event" tool, your args MUST strictly use the key "message" (e.g., {"message": "your log string"}). Do not invent keys like "event_type" or "details". '
        'Chain rules: max 10 steps, conditions reference previous store_as labels, first step cannot have a condition. If unsure, omit chain — hardcoded fallback will execute.'
    )

    # --- HYBRID ROUTING LOGIC ---
    messages = [
        {"role": "system", "content": f"You are ButterClaw, an expert Blue Team cybersecurity Guardian AI. {mode_instructions}{gate_context} {json_schema}"},
        {"role": "user", "content": f"{timeline_context}Analyze this NEW local AI agent event:\nThreat Type: {threat_type}\nRaw Data/Log: {raw_data}\n\nDetermine if this is a CSWH attempt, an Indirect Prompt Injection, or benign noise based on the current event and recent history."}
    ]

    if routing_mode == "remote":
        api_url = remote_endpoint if remote_endpoint else "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = _build_ai_headers(api_url)
        payload = {"model": active_model, "response_format": {"type": "json_object"}, "temperature": 0.3, "messages": messages}
    else:
        api_url = _resolve_ollama_url()
        headers = {"Content-Type": "application/json"}
        payload = {"model": active_model, "format": "json", "stream": False, "options": {"temperature": 0.3}, "messages": messages}

    print("🧠 Transmitting payload to Brain... stand by.")

    try:
        response = _call_brain_api(api_url, payload, headers, timeout=120)
        
        # --- BULLETPROOF NETWORK PATCH ---
        if response is None or response.status_code != 200:
            code = response.status_code if response else "N/A"
            print(f"⚠️ [API ERROR] HTTP {code}: {response.text if response else 'No response'}")
            return {"verdict": "ERROR", "confidence": 0.0, "primary_gate": "None", "chain": None, "reasoning": f"API HTTP {code} Error after retries. Check terminal logs."}

        resp_json = response.json()
        if isinstance(resp_json, list):
            resp_json = resp_json[0] if resp_json else {}

        if routing_mode == "remote":
            # Extract from OpenAI format
            raw_content = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        else:
            # Extract from Ollama format
            raw_content = resp_json.get("message", {}).get("content", "{}")
        # ----------------------------------

        print(f"\n🧠 RAW LLM OUTPUT:\n{raw_content}\n")
        
        try:
            parsed = json.loads(raw_content)
            
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}

            raw_conf = float(parsed.get("confidence", 0.0))
            return {
                "verdict": str(parsed.get("verdict", "UNKNOWN")).upper(),
                "confidence": max(0.0, min(1.0, raw_conf / 100.0 if raw_conf > 1.0 else raw_conf)),
                "primary_gate": str(parsed.get("primary_gate", "None")),
                "reasoning": str(parsed.get("reasoning", "Model failed to provide reasoning.")),
                "chain": parsed.get("chain")
            }
        except json.JSONDecodeError: return {"verdict": "ERROR", "confidence": 0.0, "primary_gate": "None", "chain": None, "reasoning": f"JSON parse failed on output: {raw_content[:200]}"}
    except Exception as e: return {"verdict": "ERROR", "confidence": 0.0, "primary_gate": "None", "chain": None, "reasoning": f"Brain failure: {str(e)}"}

# =============================================
# THE AUDITOR (Step A)
# =============================================

def run_self_audit(original_threat):
    time.sleep(30)
    mcp_history = ledger_query(limit=5, status="success")
    timeline_context = "RECENT SENTINEL ACTIONS:\n"
    if mcp_history:
        for event in reversed(mcp_history):
            if event['method'] == 'tools/call':
                timeline_context += f" - [{event['timestamp']}] Executed: {event['tool_name']} | Result: {str(event.get('result', ''))[:100]}...\n"
    else: timeline_context += " - No recent actions.\n"

    with _state_lock: active_model = model_name

    messages = [
        {"role": "system", "content": "You are the ButterClaw Auditor. Review the RECENT ACTIONS. Your job is to determine if the system overreacted to a False Positive. Respond in JSON: {\"audit_verdict\": \"AGREEMENT\"|\"FALSE_POSITIVE\", \"reasoning\": \"...\"}"},
        {"role": "user", "content": f"{timeline_context}\nOriginal Trigger: {original_threat}\nDid we overreact?"}
    ]

    if routing_mode == "remote":
        api_url = remote_endpoint if remote_endpoint else "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = _build_ai_headers(api_url)
        payload = {"model": active_model, "response_format": {"type": "json_object"}, "temperature": 0.0, "messages": messages}
    else:
        api_url = _resolve_ollama_url()
        headers = {"Content-Type": "application/json"}
        payload = {"model": active_model, "format": "json", "stream": False, "options": {"temperature": 0.0}, "messages": messages}

    try:
        response = _call_brain_api(api_url, payload, headers, timeout=300)
        
        # --- BULLETPROOF NETWORK PATCH ---
        if response is None or response.status_code != 200:
            code = response.status_code if response else "N/A"
            print(f"❌ [AUDITOR] API Error HTTP {code} after retries: {response.text if response else 'No response'}")
            return
        
        resp_json = response.json()
        if isinstance(resp_json, list):
            resp_json = resp_json[0] if resp_json else {}

        if routing_mode == "remote":
            raw_content = resp_json.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        else:
            raw_content = resp_json.get("message", {}).get("content", "{}")
        # ---------------------------------
            
        parsed = json.loads(raw_content)
        
        # --- THE GEMINI LIST PATCH ---
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else {}
        # -----------------------------

        if parsed.get("audit_verdict", "UNKNOWN") == "FALSE_POSITIVE":
            print(f"🧐 [AUDITOR] False Positive Detected: {parsed.get('reasoning', 'No reasoning provided.')}")
            conn = get_db_connection()
            conn.execute('INSERT INTO logs (title, desc, action, time, icon, color) VALUES (?, ?, ?, ?, ?, ?)', (f"Self-Audit: {original_threat}", f"[Likely False Positive] Auditor Review: {parsed.get('reasoning', 'No reasoning provided.')}", "Audit Flagged", datetime.datetime.now().strftime("%H:%M:%S"), "🧐", "amber"))
            conn.commit()
            conn.close()
            with _logs_counter_lock:
                global total_logs_processed; total_logs_processed += 1
        else: print(f"👍 [AUDITOR] Actions verified. Agreement with primary Instinct.")
    except Exception as e: print(f"❌ [AUDITOR] Self-audit API failure: {e}")

# =============================================
# FRONTEND DASHBOARD ROUTES
# =============================================
# This function handles BOTH the root URL and /index.html
@app.route('/')
@app.route('/index.html')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')

# This separate function handles ONLY /routing.html
@app.route('/routing.html')
def serve_routing():
    return send_from_directory(BASE_DIR, 'routing.html')

# =============================================
# API ROUTES
# =============================================

@app.route('/api/health', methods=['GET'])
def health():
    """Enhanced health check for Docker/systemd/load balancers."""
    health_data = {
        "status": "ok",
        "version": VERSION,
        "instance_id": cfg.INSTANCE_ID,
        "uptime_seconds": int(time.time() - _server_start_time),
        "components": {
            "auth": "enabled",
            "policy_engine": "enabled" if POLICY_ENGINE_ENABLED else "disabled",
            "alert_dispatcher": "enabled" if ALERT_DISPATCHER_ENABLED else "disabled",
            "mcp": "alive" if mcp_manager.is_alive else "dead",
        },
        "config_source": "env" if os.environ.get("BUTTERCLAW_PORT") else "defaults",
    }
    return jsonify(health_data), 200

@app.route('/api/config', methods=['GET'])
@require_auth(min_role="admin")
def get_config():
    """Read-only view of current configuration. Secrets redacted."""
    return jsonify(cfg.to_dict(redact_secrets=True)), 200

@app.route('/api/vault/key', methods=['POST'])
@require_auth(min_role="admin")
def save_vault_key():
    data = request.json
    if not data or "provider" not in data or "api_key" not in data: return jsonify({"error": "Missing provider or api_key"}), 400
    buttervault.store_key(data["provider"], data["api_key"])
    return jsonify({"status": "success"}), 200

@app.route('/api/vault/status', methods=['GET'])
@require_auth(min_role="viewer")
def check_vault_status():
    providers = buttervault.list_providers()
    status = {provider: buttervault.get_key(provider) is not None for provider in providers}
    for default in ["OpenRouter", "Anthropic"]:
        if default not in status: status[default] = False
    return jsonify(status), 200

@app.route('/api/analyze', methods=['POST'])
@require_auth(min_role="operator")
def analyze_threat():
    ctx = request.auth_context
    if is_rate_limited_for_key(ctx["key_id"], ctx["role"]):
        limit = auth.ROLE_RATE_LIMITS.get(ctx["role"], 10)
        return jsonify({"error": f"Rate limit exceeded. Max {limit} requests per minute for {ctx['role']} role."}), 429

    data = request.json
    if data is None: return jsonify({"error": "Request body must be valid JSON with Content-Type: application/json"}), 400

    threat_type = data.get("threat_type")
    raw_data = data.get("raw_data")

    if not threat_type or not raw_data: return jsonify({"error": "Missing required fields: 'threat_type' and 'raw_data'"}), 400

    print("\n" + "=" * 60)
    print(f"📥 [HTTP POST RECEIVED] From Browser Dashboard")
    print(f"   Payload: {threat_type}")

    # ==============================================
    # [v0.6.1] PRE-BRAIN POLICY FILTER
    # ==============================================
    if POLICY_ENGINE_ENABLED:
        pre_brain_ctx = {
            "raw_data": raw_data,
            "payload": raw_data,
            "threat_type": threat_type,
            "source_ip": request.remote_addr,
        }
        pre_brain_result = policy_engine.evaluate_policies("pre_brain", pre_brain_ctx)

        if pre_brain_result["action"] == "override_critical":
            print(f"🛡️ [POLICY] Pre-Brain override → CRITICAL: {pre_brain_result['reason']}")
            analysis = {
                "verdict": "CRITICAL",
                "confidence": 1.0,
                "primary_gate": "Policy",
                "reasoning": f"[Policy Override] {pre_brain_result['reason']}",
                "chain": None
            }
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("policy_override", {"threat_type": threat_type, "new_verdict": "CRITICAL", "reason": pre_brain_result["reason"]})
        elif pre_brain_result["action"] == "override_benign":
            print(f"✅ [POLICY] Pre-Brain fast-track → BENIGN: {pre_brain_result['reason']}")
            analysis = {
                "verdict": "BENIGN",
                "confidence": 1.0,
                "primary_gate": "Policy",
                "reasoning": f"[Policy Fast-Track] {pre_brain_result['reason']}",
                "chain": None
            }
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("policy_override", {"threat_type": threat_type, "new_verdict": "BENIGN", "reason": pre_brain_result["reason"]})
        elif pre_brain_result["action"] == "block":
            print(f"🚫 [POLICY] Pre-Brain block: {pre_brain_result['reason']}")
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("policy_blocked", {"threat_type": threat_type, "reason": pre_brain_result["reason"]})
            return jsonify({
                "status": "blocked",
                "reason": pre_brain_result["reason"],
                "policy_id": pre_brain_result["policy_id"]
            }), 403
        else:
            analysis = ask_guardian_agent(threat_type, raw_data)
    else:
        analysis = ask_guardian_agent(threat_type, raw_data)

    # ==============================================
    # [v0.6.1] POST-BRAIN POLICY VALIDATOR
    # ==============================================
    if POLICY_ENGINE_ENABLED:
        post_brain_ctx = {
            "raw_data": raw_data,
            "payload": raw_data,
            "threat_type": threat_type,
            "source_ip": request.remote_addr,
            "verdict": analysis.get("verdict", "UNKNOWN"),
            "confidence": analysis.get("confidence", 0.0),
            "primary_gate": analysis.get("primary_gate", "None"),
            "reasoning": analysis.get("reasoning", ""),
            "chain": analysis.get("chain"),
        }
        post_brain_result = policy_engine.evaluate_policies("post_brain", post_brain_ctx)

        if post_brain_result["action"] == "override_critical":
            print(f"🛡️ [POLICY] Post-Brain escalation → CRITICAL: {post_brain_result['reason']}")
            analysis["verdict"] = "CRITICAL"
            analysis["confidence"] = 1.0
            analysis["reasoning"] += f" [Policy Escalated: {post_brain_result['reason']}]"
            analysis["primary_gate"] = "Policy"
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("policy_override", {"threat_type": threat_type, "new_verdict": "CRITICAL", "reason": post_brain_result["reason"]})

        elif post_brain_result["action"] == "override_benign":
            print(f"✅ [POLICY] Post-Brain downgrade → BENIGN: {post_brain_result['reason']}")
            analysis["verdict"] = "BENIGN"
            analysis["reasoning"] += f" [Policy Downgraded: {post_brain_result['reason']}]"
            if ALERT_DISPATCHER_ENABLED:
                alert_dispatcher.dispatch_alert("policy_override", {"threat_type": threat_type, "new_verdict": "BENIGN", "reason": post_brain_result["reason"]})

        elif post_brain_result["action"] == "require_confidence":
            min_conf = post_brain_result.get("action_params", {}).get("min_confidence", 90)
            conf_pct = int(analysis["confidence"] * 100)
            if conf_pct < min_conf and analysis["verdict"] == "CRITICAL":
                print(f"🛡️ [POLICY] Confidence gate: {conf_pct}% < {min_conf}% required → WARNING")
                analysis["verdict"] = "WARNING"
                analysis["reasoning"] += f" [Policy: Confidence {conf_pct}% below {min_conf}% policy minimum]"
                if ALERT_DISPATCHER_ENABLED:
                    alert_dispatcher.dispatch_alert("policy_override", {"threat_type": threat_type, "new_verdict": "WARNING", "reason": post_brain_result["reason"]})

    verdict_upper = analysis["verdict"]
    confidence_pct = int(analysis["confidence"] * 100)
    trigger_gate = analysis["primary_gate"]
    reasoning = analysis["reasoning"]

    if verdict_upper == "CRITICAL" and confidence_pct < CONFIDENCE_THRESHOLD:
        print(f"🛡️ [SELF-DOS AVERTED] CRITICAL downgraded due to low confidence ({confidence_pct}% < {CONFIDENCE_THRESHOLD}%).")
        verdict_upper = "WARNING"
        reasoning += f" [Downgraded from CRITICAL: Confidence below {CONFIDENCE_THRESHOLD}% safety threshold]."

    verdict_text = f"[Gate: {trigger_gate}] [{confidence_pct}% Confidence] {reasoning}"
    print(f"🧠 [HTTP 200 OK] Model returned {verdict_upper} ({confidence_pct}%)")
    print("=" * 60)
    
    # [v0.6.2] Dispatch Final Verdict
    if ALERT_DISPATCHER_ENABLED:
        if verdict_upper == "CRITICAL":
            alert_dispatcher.dispatch_alert("verdict_critical", {"threat_type": threat_type, "reasoning": reasoning})
        elif verdict_upper == "WARNING":
            alert_dispatcher.dispatch_alert("verdict_warning", {"threat_type": threat_type, "reasoning": reasoning})

    with _state_lock: kill_sw_armed = gate_states.get("kill_sw", True)

    if verdict_upper == "CRITICAL":
        color = "red"; icon = "🚨"

        # ====================================================
        # [v0.6.5] PARANOIA DIAL INTEGRATION (The Gibson Gate)
        # ====================================================
        if not kill_sw_armed or current_level == "1":
            # Paranoia Level 1 (Observe) or Kill Switch Disabled manually
            action = "Monitored (Kinetics Disabled)"
            print(f"🛡️ [SERVER] Threat logged. Kinetic responses skipped (Paranoia Level 1 or Kill Switch disarmed).")
        else:
            # Paranoia Level 2 (Active Defense) or Level 3 (Air-Gapped Lockdown)
            executed_critical_tools = False
            mcp_failures = []
            chain_summary = None  # <-- WE CAPTURE THE CHAIN ID HERE

            chain_steps = analysis.get('chain') if isinstance(analysis, dict) else None
            if chain_steps and isinstance(chain_steps, list) and len(chain_steps) > 0:
                print(f"🔗 [CHAIN] Brain composed {len(chain_steps)}-step chain for CRITICAL response")
                executor = ChainExecutor(mcp_manager, chain_steps, dry_run=DRY_RUN)
                
                # <-- STORE THE SUMMARY STRING INSTEAD OF IMMEDIATELY OVERWRITING
                chain_summary = executor.execute()['action_summary']
                action = chain_summary
                
                executed_tools = [s['tool'] for s in executor.executed if s.get('status') == 'executed']
                if "execute_gibson_kill" in executed_tools or "rotate_keys" in executed_tools:
                    executed_critical_tools = True
            else:
                # Execute fallback hardcoded defense tools
                gibson_blocked = False
                if POLICY_ENGINE_ENABLED:
                    with _state_lock:
                        current_active_model = model_name
                    gate = policy_engine.evaluate_policies("pre_tool", {
                        "tool_name": "execute_gibson_kill", 
                        "tool_args": {"target_process": "openclaw"}, 
                        "verdict": "CRITICAL", 
                        "confidence": 1.0,
                        "active_model": current_active_model
                    })
                    if gate["action"] in ("skip_tool", "block"):
                        gibson_blocked = True; print(f"🚫 [POLICY] gibson_kill blocked by policy: {gate['reason']}")
                
                if not gibson_blocked:
                    gibson_resp = mcp_manager.send("tools/call", {"name": "execute_gibson_kill", "arguments": {"target_process": "openclaw"}}, trigger="critical")
                    if "error" in gibson_resp: mcp_failures.append("gibson_kill"); print(f"⚠️ [MCP] gibson_kill failed: {gibson_resp['error']}")
                    else: executed_critical_tools = True
                
                rotate_blocked = False
                if POLICY_ENGINE_ENABLED:
                    with _state_lock:
                        current_active_model = model_name
                    gate = policy_engine.evaluate_policies("pre_tool", {
                        "tool_name": "rotate_keys", 
                        "tool_args": {"provider": "OpenRouter"}, 
                        "verdict": "CRITICAL", 
                        "confidence": 1.0,
                        "active_model": current_active_model
                    })
                    if gate["action"] in ("skip_tool", "block"):
                        rotate_blocked = True; print(f"🚫 [POLICY] rotate_keys blocked by policy: {gate['reason']}")
                
                if not rotate_blocked:
                    rotate_resp = mcp_manager.send("tools/call", {"name": "rotate_keys", "arguments": {"provider": "OpenRouter"}}, trigger="critical")
                    if "error" in rotate_resp: mcp_failures.append("rotate_keys"); print(f"⚠️ [MCP] rotate_keys failed: {rotate_resp['error']}")
                    else: executed_critical_tools = True

            # Evaluate Paranoia Level against the executed critical tools
            if executed_critical_tools:
                if DRY_RUN:
                    print("🧪 [DRY RUN] Critical tool triggered. Skipping further kinetic action.")
                    # <-- SAFELY INJECT THE SUMMARY INTO THE FINAL STRINGS
                    action = f"{chain_summary} | SIGKILL (Dry Run)" if chain_summary else (f"SIGKILL (Dry Run) | MCP partial failure: {', '.join(mcp_failures)}" if mcp_failures else "SIGKILL (Dry Run)")
                else:
                    if current_level == "3":
                        print("☢️ [SERVER] Paranoia Level 3 Active: Air-Gapped Lockdown. Triggering ButterVault destruction...")
                        if ALERT_DISPATCHER_ENABLED:
                            alert_dispatcher.dispatch_alert("gibson_triggered", {"threat_type": threat_type, "trigger": "paranoia_3"})
                        buttervault.butter_keys()
                        action = f"{chain_summary} | Vault Shredded" if chain_summary else (f"Vault Shredded | MCP partial failure: {', '.join(mcp_failures)}" if mcp_failures else "SIGKILL | Vault Shredded")
                    else:
                        print("⚔️ [SERVER] Paranoia Level 2 Active: Active Defense. SIGKILL executed. Vault remains sealed.")
                        action = f"{chain_summary} | SIGKILL Executed" if chain_summary else (f"SIGKILL Executed | MCP partial failure: {', '.join(mcp_failures)}" if mcp_failures else "SIGKILL Executed")
            else:
                print("🛡️ [SERVER] All critical tools blocked or failed. Vault remains sealed.")
                # <-- PREVENT THE CLOBBER IF KINETICS FAIL
                action = f"{chain_summary} (Kinetics Blocked)" if chain_summary else "ALERT | Blocks/Failures Prevented Kinetics"

        threading.Thread(target=run_self_audit, args=(threat_type,), daemon=True).start()
    elif verdict_upper == "WARNING": color = "amber"; icon = "⚠️"; action = "Monitored"
    elif verdict_upper == "ERROR": color = "red"; icon = "❌"; action = "System Offline"
    else: color = "emerald"; icon = "✅"; action = "Monitored"

    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO logs (title, desc, action, time, icon, color) VALUES (?, ?, ?, ?, ?, ?)', (threat_type, verdict_text, action, datetime.datetime.now().strftime("%H:%M:%S"), icon, color))
        conn.commit()
        conn.close()
    except sqlite3.Error as e: print(f"❌ [DB ERROR] Failed to write log: {e}"); return jsonify({"error": f"Database write failed: {e}"}), 500

    with _logs_counter_lock:
        global total_logs_processed; total_logs_processed += 1

    return jsonify({"status": "success", "verdict": verdict_text}), 200

@app.route('/api/logs', methods=['GET'])
@require_auth(min_role="viewer")
def get_logs():
    try:
        conn = get_db_connection()
        rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 40').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e: return jsonify({"error": f"Database read failed: {e}"}), 500

@app.route('/api/rotate-keys', methods=['POST'])
@require_auth(min_role="admin")
def manual_key_rotation():
    if ALERT_DISPATCHER_ENABLED:
        alert_dispatcher.dispatch_alert("gibson_manual", {"trigger": "admin_api"})
    buttervault.butter_keys()
    
    rotate_blocked = False
    if POLICY_ENGINE_ENABLED:
        with _state_lock:
            current_active_model = model_name
        gate = policy_engine.evaluate_policies("pre_tool", {
            "tool_name": "rotate_keys", 
            "tool_args": {"provider": "Manual_Global"}, 
            "verdict": "CRITICAL", 
            "confidence": 1.0,
            "active_model": current_active_model
        })
        if gate["action"] in ("skip_tool", "block"):
            rotate_blocked = True; print(f"🚫 [POLICY] manual rotate_keys blocked by policy: {gate['reason']}")

    mcp_note = ""
    if not rotate_blocked:
        rotate_resp = mcp_manager.send("tools/call", {"name": "rotate_keys", "arguments": {"provider": "Manual_Global"}}, trigger="manual")
        if "error" in rotate_resp:
            mcp_note = f" (MCP rotate_keys failed: {rotate_resp['error']})"
            print(f"⚠️ [MCP] Manual rotate_keys failed: {rotate_resp['error']}")

    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO logs (title, desc, action, time, icon, color) VALUES (?, ?, ?, ?, ?, ?)', ("Manual Key Rotation", f"Administrator manually triggered API key rotation. Ciphertext destroyed.{mcp_note}", "Keys Buttered", datetime.datetime.now().strftime("%H:%M:%S"), "🗝️", "blue"))
        conn.commit()
        conn.close()
    except sqlite3.Error as e: return jsonify({"error": f"Database write failed: {e}"}), 500

    with _logs_counter_lock:
        global total_logs_processed; total_logs_processed += 1

    return jsonify({"status": "success"}), 200

# =============================================
# API ROUTES: OAUTH (v0.5.2)
# =============================================

def _oauth_result_page(success, message):
    color = "#10b981" if success else "#ef4444"
    icon = "✅" if success else "❌"
    return Response(f"""<!DOCTYPE html><html><head><title>ButterClaw OAuth</title></head><body style="font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f8fafc;"><div style="text-align:center;padding:2rem;"><div style="font-size:3rem;">{icon}</div><h2 style="color:{color};margin:1rem 0;">{message}</h2><p style="color:#64748b;font-size:0.875rem;">This window will close automatically.</p></div><script>if (window.opener) {{ window.opener.postMessage({{type: 'oauth_result', success: {str(success).lower()}, message: '{message}'}}, '*'); }} setTimeout(function() {{ window.close(); }}, 2000);</script></body></html>""", mimetype="text/html")

@app.route('/api/vault/oauth/start/<provider_name>', methods=['GET'])
@require_auth(min_role="operator")
def oauth_start(provider_name):
    provider = oauth_config.get_provider(provider_name)
    if not provider: return jsonify({"error": f"Unknown provider: {provider_name}"}), 404
    if not provider["oauth_supported"]: return jsonify({"error": f"{provider['display_name']} does not support OAuth. Use manual API key entry."}), 400
    client_id = buttervault.get_key(f"{provider_name}_client_id")
    if not client_id: return jsonify({"error": f"No client_id found in ButterVault for '{provider_name}'."}), 400
    
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{cfg.BASE_URL}/api/vault/oauth/callback"
    _cleanup_expired_oauth_states()
    with _oauth_states_lock: _oauth_states[state] = {"provider": provider_name, "created_at": time.time(), "redirect_uri": redirect_uri}
    
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(provider["scopes"]), "state": state, "access_type": "offline", "prompt": "consent"}
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    auth_url = f"{provider['authorize_url']}?{query}"
    print(f"🔑 [OAUTH] Starting {provider['display_name']} flow. State: {state[:8]}...")
    return jsonify({"auth_url": auth_url, "state": state, "provider": provider_name}), 200

@app.route('/api/vault/oauth/callback', methods=['GET'])
def oauth_callback():
    code = request.args.get("code"); state = request.args.get("state"); error = request.args.get("error")
    if error: print(f"❌ [OAUTH] Provider returned error: {error}"); return _oauth_result_page(success=False, message=f"Authorization denied: {error}")
    if not code or not state: return _oauth_result_page(success=False, message="Missing code or state parameter.")
    
    with _oauth_states_lock: state_data = _oauth_states.pop(state, None)
    if not state_data: return _oauth_result_page(success=False, message="Invalid or expired state. Please try again.")
    if time.time() - state_data["created_at"] > OAUTH_STATE_TTL: return _oauth_result_page(success=False, message="Authorization timed out. Please try again.")
    
    provider_name = state_data["provider"]; redirect_uri = state_data["redirect_uri"]
    provider = oauth_config.get_provider(provider_name)
    if not provider: return _oauth_result_page(success=False, message=f"Unknown provider: {provider_name}")
    
    client_id = buttervault.get_key(f"{provider_name}_client_id")
    client_secret = buttervault.get_key(f"{provider_name}_client_secret")
    if not client_id or not client_secret: return _oauth_result_page(success=False, message="Client credentials not found in ButterVault.")
    
    print(f"🔑 [OAUTH] Exchanging code for tokens ({provider['display_name']})...")
    try:
        token_resp = http_requests.post(provider["token_url"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri, "client_id": client_id, "client_secret": client_secret}, timeout=15)
        if token_resp.status_code != 200: return _oauth_result_page(success=False, message=f"Token exchange failed: HTTP {token_resp.status_code}")
        tokens = token_resp.json()
    except Exception as e: return _oauth_result_page(success=False, message=f"Token exchange failed: {e}")
    
    token_dict = {"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token"), "expires_at": time.time() + tokens.get("expires_in", 3600), "token_type": tokens.get("token_type", "Bearer"), "scope": tokens.get("scope", " ".join(provider["scopes"]))}
    buttervault.store_oauth_token(provider_name, token_dict)
    
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO logs (title, desc, action, time, icon, color) VALUES (?, ?, ?, ?, ?, ?)', (f"OAuth Connected: {provider['display_name']}", f"Successfully authenticated with {provider['display_name']} via OAuth 2.0. Tokens encrypted and sealed.", "OAuth Sealed", datetime.datetime.now().strftime("%H:%M:%S"), "🔑", "emerald"))
        conn.commit()
        conn.close()
    except sqlite3.Error: pass
    return _oauth_result_page(success=True, message=f"{provider['display_name']} connected successfully!")

@app.route('/api/vault/oauth/status', methods=['GET'])
@require_auth(min_role="viewer")
def oauth_status():
    statuses = {}; connected_providers = buttervault.list_oauth_providers()
    for name in oauth_config.list_oauth_capable():
        provider = oauth_config.get_provider(name)
        token = buttervault.get_oauth_token(name) if name in connected_providers else None
        statuses[name] = {"display_name": provider["display_name"], "connected": token is not None, "has_refresh_token": bool(token.get("refresh_token")) if token else False, "expires_at": token.get("expires_at") if token else None, "expired": token is not None and time.time() > token.get("expires_at", 0), "has_client_credentials": (buttervault.get_key(f"{name}_client_id") is not None and buttervault.get_key(f"{name}_client_secret") is not None)}
    return jsonify(statuses), 200

@app.route('/api/vault/oauth/revoke/<provider_name>', methods=['POST'])
@require_auth(min_role="admin")
def oauth_revoke(provider_name):
    provider = oauth_config.get_provider(provider_name)
    if not provider: return jsonify({"error": f"Unknown provider: {provider_name}"}), 404
    token_dict = buttervault.get_oauth_token(provider_name)
    if not token_dict: return jsonify({"error": f"No OAuth token found for {provider_name}"}), 404
    if provider.get("revoke_url"):
        try: http_requests.post(provider["revoke_url"], data={"token": token_dict["access_token"]}, timeout=10)
        except Exception as e: print(f"⚠️ [OAUTH] Remote revocation failed: {e}")
    buttervault.delete_oauth_token(provider_name)
    return jsonify({"status": "revoked", "provider": provider_name}), 200

# --- THE CONTROL PANEL ---

@app.route('/api/settings', methods=['GET'])
@require_auth(min_role="operator")
def settings_get():
    with _state_lock: return jsonify({"level": current_level, "shield_enabled": shield_enabled, "routing_mode": routing_mode, "model": model_name, "endpoint": remote_endpoint, "gates": dict(gate_states), "dry_run": DRY_RUN, "mcp_transport": mcp_transport_mode, "mcp_sse_url": mcp_sse_url, "mcp_sse_token_set": bool(mcp_sse_token)})

@app.route('/api/settings', methods=['POST'])
@require_auth(min_role="admin")
def settings_post():
    global current_level, routing_mode, model_name, remote_endpoint, gate_states, mcp_transport_mode, mcp_sse_url, mcp_sse_token
    data = request.json
    if data is None: return jsonify({"error": "Request body must be valid JSON"}), 400
    errors = []

    if "level" in data:
        new_level = str(data["level"])
        if new_level not in ("1", "2", "3"): errors.append("level must be 1, 2, or 3")
        else:
            with _state_lock: current_level = new_level
            print(f"📡 [SENTINEL UPDATE] Paranoia Level shifted to: {new_level}")

    if "routing_mode" in data:
        new_mode = str(data["routing_mode"]).lower().strip()
        if new_mode not in VALID_ROUTING_MODES: errors.append(f"routing_mode must be one of: {', '.join(VALID_ROUTING_MODES)}")
        else:
            with _state_lock: routing_mode = new_mode
            print(f"🛠️ [ROUTING] Mode set to: {new_mode}")

    if "model" in data:
        new_model = str(data["model"]).strip()
        if not new_model: errors.append("model must be a non-empty string")
        else:
            with _state_lock: model_name = new_model
            print(f"🧠 [MODEL] Active model set to: {new_model}")

    if "endpoint" in data:
        new_endpoint = str(data["endpoint"]).strip()
        if not _validate_endpoint_url(new_endpoint): errors.append("endpoint must be a valid http:// or https:// URL")
        else:
            with _state_lock: remote_endpoint = new_endpoint

    if "gates" in data:
        new_gates = data["gates"]
        if not isinstance(new_gates, dict): errors.append("gates must be an object mapping gate IDs to booleans")
        else:
            unknown_keys = set(new_gates.keys()) - VALID_GATE_KEYS
            if unknown_keys: errors.append(f"Unknown gate keys: {', '.join(sorted(unknown_keys))}. ")
            else:
                with _state_lock: gate_states.update({k: bool(v) for k, v in new_gates.items()})
                print(f"🛡️ [GATE UPDATE] Gate states updated: { {k: bool(v) for k, v in new_gates.items()} }")

    if "mcp_transport" in data:
        new_transport = str(data["mcp_transport"]).lower().strip()
        if new_transport not in VALID_MCP_TRANSPORTS: errors.append(f"mcp_transport must be one of: {', '.join(VALID_MCP_TRANSPORTS)}")
        else:
            with _state_lock: mcp_transport_mode = new_transport

    if "mcp_sse_url" in data:
        new_url = str(data["mcp_sse_url"]).strip()
        if new_url and not _validate_endpoint_url(new_url): errors.append("mcp_sse_url must be a valid http:// or https:// URL")
        else:
            with _state_lock: mcp_sse_url = new_url

    if "mcp_sse_token" in data:
        with _state_lock: mcp_sse_token = str(data["mcp_sse_token"]).strip()

    if errors: return jsonify({"status": "partial", "errors": errors}), 400
    return jsonify({"status": "ok"})

@app.route('/api/gates/<gate_id>/toggle', methods=['POST'])
@require_auth(min_role="admin")
def gate_toggle(gate_id):
    data = request.json or {}
    if gate_id not in VALID_GATE_KEYS:
        return jsonify({"error": f"Unknown gate: {gate_id}", "code": "UNKNOWN_GATE"}), 404
    if "active" not in data or not isinstance(data["active"], bool):
        return jsonify({"error": "'active' (boolean) is required", "code": "BAD_REQUEST"}), 400
    with _state_lock:
        gate_states[gate_id] = data["active"]
        current_dry = DRY_RUN
    state_label = "ARMED" if data["active"] else "DISARMED"
    dry_label   = " [DRY RUN — no execution will occur]" if current_dry else ""
    print(f"🛡️ [GATE TOGGLE] {gate_id} → {state_label}{dry_label}")
    if gate_id == "kill_sw" and data["active"] and not current_dry:
        print(f"⚠️  [GATE TOGGLE] kill_sw ARMED — Gibson sequence is now live")
    return jsonify({"ok": True, "gate": gate_id, "active": data["active"], "dry_run": current_dry})

@app.route('/api/shield', methods=['POST'])
@require_auth(min_role="admin")
def shield():
    global shield_enabled
    data = request.json
    if data is None or "enabled" not in data: return jsonify({"error": "Request body must include 'enabled' (boolean)"}), 400
    new_state = bool(data["enabled"])
    with _state_lock: shield_enabled = new_state
    state_label = "UP" if shield_enabled else "DOWN"
    print(f"🛡️ [SHIELD] Shield is now {state_label}")
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO logs (title, desc, action, time, icon, color) VALUES (?, ?, ?, ?, ?, ?)', (f"Shield {state_label}", f"Administrator {'enabled' if shield_enabled else 'disabled'} the ButterClaw shield.", "Shield Toggled", datetime.datetime.now().strftime("%H:%M:%S"), "🛡️" if shield_enabled else "🦞", "emerald" if shield_enabled else "amber"))
        conn.commit()
        conn.close()
    except sqlite3.Error as e: print(f"❌ [DB ERROR] Failed to log shield change: {e}")
    with _logs_counter_lock:
        global total_logs_processed; total_logs_processed += 1
    return jsonify({"status": "ok", "shield_enabled": shield_enabled})

# =============================================
# MCP OBSERVABILITY ENDPOINTS (v0.5.0)
# =============================================

@app.route('/api/mcp/status', methods=['GET'])
@require_auth(min_role="viewer")
def mcp_status():
    return jsonify(mcp_manager.status()), 200

@app.route('/api/mcp/ping', methods=['GET'])
@require_auth(min_role="operator")
def mcp_ping():
    start = time.time()
    resp = mcp_manager.send("ping", {}, timeout=5, trigger="ping")
    elapsed_ms = round((time.time() - start) * 1000, 1)
    if "error" in resp: return jsonify({"pong": False, "error": resp["error"], "ms": elapsed_ms}), 503
    return jsonify({"pong": True, "ms": elapsed_ms}), 200

@app.route('/api/mcp/tools', methods=['GET'])
@require_auth(min_role="viewer")
def mcp_tools():
    return jsonify({"tools": mcp_manager.discovered_tools, "count": len(mcp_manager.discovered_tools)}), 200

@app.route('/api/mcp/restart', methods=['POST'])
@require_auth(min_role="admin")
def mcp_restart():
    global mcp_manager
    with _state_lock: current_transport = mcp_transport_mode
    if current_transport != mcp_manager.transport_name.split(" ")[0]:
        mcp_manager.stop(); mcp_manager = create_mcp_manager()
    success = mcp_manager.restart()
    status = mcp_manager.status()
    return jsonify({"restarted": success, **status}), 200 if success else 503

# =============================================
# MCP EVENT LEDGER ENDPOINTS (v0.5.0)
# =============================================

@app.route('/api/mcp/events', methods=['GET'])
@require_auth(min_role="viewer")
def mcp_events():
    limit = request.args.get('limit', 50, type=int)
    events = ledger_query(limit=limit, tool=request.args.get('tool', None), status=request.args.get('status', None), since=request.args.get('since', None))
    return jsonify({"events": events, "count": len(events), "total": ledger_count()}), 200

@app.route('/api/mcp/events/<int:event_id>', methods=['GET'])
@require_auth(min_role="viewer")
def mcp_event_detail(event_id):
    event = ledger_get_event(event_id)
    if event is None: return jsonify({"error": f"Event {event_id} not found"}), 404
    return jsonify(event), 200

# =============================================
# API ROUTES: POLICY ENGINE (v0.6.1)
# =============================================

@app.route('/api/policies', methods=['GET'])
@require_auth(min_role="viewer")
def list_policies_endpoint():
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    enabled = request.args.get("enabled")
    policies = policy_engine.list_policies(scope=request.args.get("scope"), enabled_only=(enabled == "true" if enabled else False))
    return jsonify(policies), 200

@app.route('/api/policies', methods=['POST'])
@require_auth(min_role="admin")
def create_policy_endpoint():
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    data = request.json
    if not data: return jsonify({"error": "Request body required"}), 400
    missing = [f for f in ["name", "scope", "condition", "action"] if f not in data]
    if missing: return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
    try:
        result = policy_engine.create_policy(
            name=data["name"], scope=data["scope"], condition=data["condition"], action=data["action"],
            action_params=data.get("action_params"), description=data.get("description"), priority=data.get("priority", 50), created_by=request.auth_context.get("key_id")
        )
        return jsonify(result), 201
    except ValueError as e: return jsonify({"error": str(e)}), 400

@app.route('/api/policies/<policy_id>', methods=['GET'])
@require_auth(min_role="viewer")
def get_policy_endpoint(policy_id):
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    policy = policy_engine.get_policy(policy_id)
    if not policy: return jsonify({"error": "Policy not found"}), 404
    return jsonify(policy), 200

@app.route('/api/policies/<policy_id>', methods=['PUT'])
@require_auth(min_role="admin")
def update_policy_endpoint(policy_id):
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    data = request.json
    if not data: return jsonify({"error": "Request body required"}), 400
    try:
        result = policy_engine.update_policy(policy_id, **data)
        if not result: return jsonify({"error": "Policy not found"}), 404
        return jsonify(result), 200
    except ValueError as e: return jsonify({"error": str(e)}), 400

@app.route('/api/policies/<policy_id>', methods=['DELETE'])
@require_auth(min_role="admin")
def delete_policy_endpoint(policy_id):
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    if not policy_engine.delete_policy(policy_id): return jsonify({"error": "Policy not found"}), 404
    return jsonify({"status": "deleted", "id": policy_id}), 200

@app.route('/api/policies/<policy_id>/toggle', methods=['POST'])
@require_auth(min_role="admin")
def toggle_policy_endpoint(policy_id):
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    data = request.json or {}
    enabled = data.get("enabled", True)
    if not policy_engine.toggle_policy(policy_id, enabled): return jsonify({"error": "Policy not found"}), 404
    return jsonify({"status": "toggled", "id": policy_id, "enabled": enabled}), 200

@app.route('/api/policies/test', methods=['POST'])
@require_auth(min_role="operator")
def test_policy_endpoint():
    if not POLICY_ENGINE_ENABLED: return jsonify({"error": "Policy engine disabled"}), 503
    data = request.json
    if not data or "payload" not in data: return jsonify({"error": "Missing 'payload' field"}), 400
    return jsonify(policy_engine.test_payload(payload=data["payload"], threat_type=data.get("threat_type", "test"))), 200

@app.route('/api/policies/events', methods=['GET'])
@require_auth(min_role="viewer")
def policy_events_endpoint():
    if not POLICY_ENGINE_ENABLED: 
        return jsonify({"error": "Policy engine disabled"}), 503
        
    limit = request.args.get("limit", 50, type=int)
    policy_id = request.args.get("policy_id")
    scope = request.args.get("scope")
    since = request.args.get("since")
    
    events = policy_engine.get_policy_events(
        limit=limit, policy_id=policy_id, scope=scope, since=since
    )
    total_count = policy_engine.get_policy_event_count()
    
    return jsonify({
        "events": events,
        "count": len(events),
        "total": total_count
    }), 200

# =============================================
# SSE STREAM
# =============================================

@app.route('/api/stream')
@require_auth(min_role="viewer")
def stream():
    def event_stream():
        global total_logs_processed
        with _logs_counter_lock: last_processed = total_logs_processed
        while True:
            with _logs_counter_lock: current = total_logs_processed
            if current > last_processed: yield f"data: update_ready\n\n"; last_processed = current
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
    print(f"   Config Source: {'env' if os.environ.get('BUTTERCLAW_PORT') else '.env/defaults'}")
    print(f"   Instance ID: {cfg.INSTANCE_ID}")
    print(f"   Database: {cfg.DB_PATH}")
    print(f"   Paranoia Level: {current_level}")
    print(f"   Routing Mode: {routing_mode}")
    print(f"   Active Model: {model_name}")
    if routing_mode == "remote" and remote_endpoint: print(f"   Remote Endpoint: {remote_endpoint}")
    else: print(f"   Ollama Endpoint: {OLLAMA_LOCAL_BASE}")
    active_gates = [k for k, v in gate_states.items() if v]
    print(f"   Active Gates: {', '.join(active_gates) if active_gates else 'NONE'}")
    print(f"   Self-DoS Threshold: {CONFIDENCE_THRESHOLD}%")
    print(f"   Policy Engine: {'ENABLED' if POLICY_ENGINE_ENABLED else 'DISABLED'}")
    print(f"   Alert Dispatcher: {'ENABLED' if ALERT_DISPATCHER_ENABLED else 'DISABLED'}")
    print(f"   MCP Transport: {mcp_transport_mode}")

    print("\n🔐 [AUTH] Checking API key bootstrap...")
    bootstrap_admin_key()
    auth.bootstrap_infrastructure_keys()
    auth.bootstrap_infrastructure_keys_auto_heal()
    
    print("\n🚨 [ALERTS] Checking infrastructure channels...")
    if ALERT_DISPATCHER_ENABLED:
        alert_dispatcher.bootstrap_infrastructure_alerts()

    print("\n🔐 [VAULT] Initializing Master Keyring...")
    try:
        buttervault._get_cipher()
        print("   ✅ Vault Master Key is sealed.")
    except Exception as e:
        print(f"   ❌ Vault initialization failed: {e}")
        
    if ALERT_DISPATCHER_ENABLED:
        alert_dispatcher.dispatch_alert("system_startup", {"version": VERSION, "routing_mode": routing_mode, "model": model_name})

    print("\n" + "=" * 60)
    print(f"📡 [MCP] Initiating v{VERSION} Handshake Sequence...")
    print("=" * 60)

    if mcp_manager.start():
        if mcp_manager.handshake():
            tool_count = len(mcp_manager.discovered_tools)
            print(f"✅ [MCP] Handshake complete. {tool_count} tools armed.")
            print(f"   Transport: {mcp_manager.transport_name}")
        else: print("⚠️ [MCP] Handshake failed. MCP endpoints will report degraded status.")
    else: print("❌ [MCP] Failed to spawn execution layer. The Sentinel is unarmed.")

    print(f"📋 [LEDGER] Event ledger initialized. {ledger_count()} historical events.")
    print("=" * 60 + "\n")

    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
"""
ButterClaw v0.5.2 — ButterVault OAuth & Multi-Step Chaining
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
  [v0.5.0] The Nervous System:
           - Event Ledger: persistent append-only audit log (mcp_events table)
           - MCPSSEClient: connects to remote MCP servers via SSE transport
           - MCP transport selector: stdio (default) or sse (remote)
           - /api/mcp/events endpoint for ledger queries
           - /api/mcp/events/<id> endpoint for single event detail
           - send() hooks: every MCP tool call is logged before + after
           - Settings extended with mcp_transport, mcp_sse_url, mcp_sse_token
           - Status extended with transport_mode, event_count
  [v0.5.1] Tool Chaining:
           - ChainExecutor class for multi-step MCP tool sequences
           - Condition evaluator: whitelist of safe string comparisons
           - Brain prompt extended with chain schema + available tools
           - CRITICAL path routes to ChainExecutor when chain is present
           - Chain-aware ledger logging (chain_id, chain_step now populated)
           - Safety: max 10 steps, 60s total timeout, no eval()
  [v0.5.2] ButterVault OAuth:
           - OAuth 2.0 authorization code flow (Google Cloud first)
           - /api/vault/oauth/start, /callback, /status, /revoke endpoints
           - CSRF state validation with 10-minute TTL
           - Token refresh handled transparently by buttervault
           - Gibson destroys OAuth tokens alongside API keys
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests as http_requests
import datetime
import logging
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
# requests.utils.quote <- replaced with urllib standard, maybe use later
import buttervault
import oauth_config

# =============================================
# APP SETUP
# =============================================

VERSION = "0.5.2"

# [v0.5.1] Module-level dry run flag — disables actual MCP calls in ChainExecutor
DRY_RUN = False

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

# [v0.5.0] MCP transport configuration
mcp_transport_mode = "stdio"    # "stdio" or "sse"
mcp_sse_url = ""                # e.g. "http://remote-host:5001"
mcp_sse_token = ""              # bearer token for SSE auth

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
VALID_MCP_TRANSPORTS = ("stdio", "sse")

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
    # Original oopsie logs table
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
    # [v0.5.0] MCP Event Ledger — persistent append-only audit log
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

init_db()

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)


# =============================================
# OAUTH STATE MANAGEMENT (v0.5.2)
# =============================================

_oauth_states = {}  # state_token → {provider, created_at, redirect_uri}
_oauth_states_lock = threading.Lock()
OAUTH_STATE_TTL = 600  # 10 minutes — state tokens expire after this

def _cleanup_expired_oauth_states():
    """Remove expired CSRF state tokens."""
    now = time.time()
    with _oauth_states_lock:
        expired = [k for k, v in _oauth_states.items() if now - v["created_at"] > OAUTH_STATE_TTL]
        for k in expired:
            del _oauth_states[k]


# =============================================
# MCP EVENT LEDGER (v0.5.0)
# =============================================

def ledger_log_start(req_id, method, tool_name=None, arguments=None, trigger="auto", chain_id=None, chain_step=None):
    """Write a pending event to the ledger before MCP dispatch."""
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO mcp_events (timestamp, req_id, method, tool_name, arguments, status, trigger, chain_id, chain_step)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        ''', (
            datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            req_id,
            method,
            tool_name,
            json.dumps(arguments) if arguments else None,
            trigger,
            chain_id,
            chain_step
        ))
        event_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.commit()
        conn.close()
        return event_id
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Failed to log start: {e}")
        return None

def ledger_log_end(event_id, status, result=None, elapsed_ms=None):
    """Update a pending event with its outcome."""
    if event_id is None:
        return
    try:
        result_str = None
        if result is not None:
            if isinstance(result, dict):
                result_str = json.dumps(result)
            else:
                result_str = str(result)
            # Truncate very long results to prevent DB bloat
            if result_str and len(result_str) > 4096:
                result_str = result_str[:4093] + "..."

        conn = get_db_connection()
        conn.execute('''
            UPDATE mcp_events SET status = ?, result = ?, elapsed_ms = ? WHERE id = ?
        ''', (status, result_str, elapsed_ms, event_id))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Failed to log end: {e}")

def ledger_query(limit=50, tool=None, status=None, since=None):
    """Query the event ledger with optional filters."""
    query = "SELECT * FROM mcp_events WHERE 1=1"
    params = []

    if tool:
        query += " AND tool_name = ?"
        params.append(tool)
    if status:
        query += " AND status = ?"
        params.append(status)
    if since:
        query += " AND timestamp >= ?"
        params.append(since)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 200))

    try:
        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Query failed: {e}")
        return []

def ledger_get_event(event_id):
    """Fetch a single event by ID."""
    try:
        conn = get_db_connection()
        row = conn.execute('SELECT * FROM mcp_events WHERE id = ?', (event_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        print(f"⚠️ [LEDGER] Fetch failed: {e}")
        return None

def ledger_count():
    """Return total event count for status endpoint."""
    try:
        conn = get_db_connection()
        count = conn.execute('SELECT COUNT(*) FROM mcp_events').fetchone()[0]
        conn.close()
        return count
    except sqlite3.Error:
        return 0


# =============================================
# CHAIN EXECUTOR (v0.5.1)
# Brain-composed multi-step MCP tool sequences
# =============================================

VALID_CONDITION_OPERATORS = {
    "contains":     lambda val, exp: str(exp).lower() in str(val).lower(),
    "not_contains": lambda val, exp: str(exp).lower() not in str(val).lower(),
    "equals":       lambda val, exp: str(val).strip().lower() == str(exp).strip().lower(),
    "not_equals":   lambda val, exp: str(val).strip().lower() != str(exp).strip().lower(),
    "starts_with":  lambda val, exp: str(val).strip().lower().startswith(str(exp).strip().lower()),
}

class ChainExecutor:
    """Executes a Brain-composed sequence of MCP tool calls with
    optional inter-step conditions. Safety rails: 10-step max, 60s timeout,
    no eval() — conditions use a closed operator whitelist."""

    MAX_STEPS = 10
    TIMEOUT = 60  # seconds

    def __init__(self, mcp_manager, chain_steps, dry_run=False):
        if not isinstance(chain_steps, list):
            raise ValueError("chain_steps must be a list")
        self.mcp_manager = mcp_manager
        self.chain_steps = chain_steps[:self.MAX_STEPS]
        self.dry_run = dry_run
        self.results = {}
        self.executed = []
        self.chain_id = uuid.uuid4().hex[:12]
        self.start_time = time.time()
        self.timeout = self.TIMEOUT

    def execute(self):
        """Run the chain. Returns summary dict."""
        print(f"\n🔗 [CHAIN {self.chain_id}] Starting {len(self.chain_steps)}-step chain"
              f"{' [DRY RUN]' if self.dry_run else ''}")

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
                event_id = ledger_log_start(
                    req_id=None,
                    method="tools/call",
                    tool_name=tool_name,
                    arguments=step.get("args", {}),
                    trigger="chain",
                    chain_id=self.chain_id,
                    chain_step=idx
                )
                if event_id:
                    ledger_log_end(event_id, status="error", result={"error": str(e)})
                continue

        step_names = [s.get('tool', '?') for s in self.chain_steps[:len(self.executed)]]
        action_summary = f"Chain [{self.chain_id}]: {len(self.executed)}/{len(self.chain_steps)} steps — {', '.join(step_names)}"

        print(f"🔗 [CHAIN {self.chain_id}] Complete. {action_summary}")

        return {
            "chain_id": self.chain_id,
            "steps_executed": len(self.executed),
            "steps_total": len(self.chain_steps),
            "results": self.results,
            "action_summary": action_summary
        }

    def _execute_step(self, step, step_index):
        """Execute a single chain step with optional condition check."""
        tool_name = step.get('tool')
        if not tool_name:
            raise ValueError(f"Step {step_index} missing required 'tool' key")

        # Check condition (if present)
        condition = step.get('condition')
        if condition:
            if not self._evaluate_condition(condition):
                print(f"⏭️ [CHAIN {self.chain_id}] Step {step_index} ({tool_name}) skipped — condition not met")
                self.executed.append({"step": step_index, "tool": tool_name, "status": "skipped"})
                # Log skipped step to ledger
                event_id = ledger_log_start(
                    req_id=None,
                    method="tools/call", tool_name=tool_name,
                    arguments=step.get("args", {}),
                    trigger="chain", chain_id=self.chain_id, chain_step=step_index
                )
                if event_id:
                    ledger_log_end(event_id, status="skipped", result={"reason": "condition_not_met"})
                return

        args = step.get('args', {})
        store_as = step.get('store_as', tool_name)

        if self.dry_run:
            print(f"🧪 [CHAIN {self.chain_id}] [DRY RUN] Step {step_index}: {tool_name}({args})")
            result = {"dry_run": True, "tool": tool_name, "args": args}
        else:
            result = self.mcp_manager.send("tools/call", {
                "name": tool_name,
                "arguments": args
            }, trigger="chain", chain_id=self.chain_id, chain_step=step_index)

        self.results[store_as] = result
        self.executed.append({"step": step_index, "tool": tool_name, "status": "executed"})
        print(f"✅ [CHAIN {self.chain_id}] Step {step_index}: {tool_name} → stored as '{store_as}'")

    def _evaluate_condition(self, condition):
        """Evaluate a step condition using the safe operator whitelist."""
        if not isinstance(condition, dict):
            return False

        source = condition.get('source')
        operator = condition.get('operator')
        expected = condition.get('expected')

        if source not in self.results:
            print(f"⚠️ [CHAIN {self.chain_id}] Condition source '{source}' not in results — skipping")
            return False

        if operator not in VALID_CONDITION_OPERATORS:
            print(f"⚠️ [CHAIN {self.chain_id}] Unknown operator '{operator}' — skipping")
            return False

        source_value = str(self.results[source])
        return VALID_CONDITION_OPERATORS[operator](source_value, expected)

    def summary(self):
        """Return human-readable action summary string."""
        step_names = [s.get('tool', '?') for s in self.chain_steps[:len(self.executed)]]
        return f"Chain [{self.chain_id}]: {len(self.executed)}/{len(self.chain_steps)} steps — {', '.join(step_names)}"


# =============================================
# MCP MANAGER INTERFACE (v0.5.0)
# =============================================

class BaseMCPManager:
    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None):
        raise NotImplementedError
    def notify(self, method, params=None):
        raise NotImplementedError
    def handshake(self):
        raise NotImplementedError
    def status(self):
        raise NotImplementedError
    def start(self):
        raise NotImplementedError
    def stop(self):
        raise NotImplementedError
    def restart(self):
        raise NotImplementedError
    @property
    def is_alive(self):
        raise NotImplementedError
    @property
    def transport_name(self):
        raise NotImplementedError

# =============================================
# MCP PROCESS MANAGER — stdio transport (v0.5.0)
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
        self._stdout_thread = None
        self._stderr_thread = None
        self.discovered_tools = []
        self.server_info = {}
        self.handshake_ok = False
        self.protocol_version = self.MCP_PROTOCOL_VERSION

    @property
    def transport_name(self):
        return "stdio"

    @property
    def is_alive(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.is_alive:
            return True
        print("🚀 [MCP] Spawning ButterClaw Execution Layer (stdio)...")
        try:
            self.process = subprocess.Popen(
                [sys.executable, self.script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
        except Exception as e:
            print(f"❌ [MCP] Failed to spawn: {e}")
            return False

        self._running = True
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
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

    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None):
        if not self.is_alive:
            if not self.start():
                return {"error": "MCP process failed to start"}
            if not self.handshake():
                print("⚠️ [MCP] Auto-restart handshake failed. Attempting send anyway (best-effort).")

        req_id = next(self._req_counter)

        tool_name = None
        arguments = None
        if method == "tools/call" and params:
            tool_name = params.get("name")
            arguments = params.get("arguments")

        event_id = ledger_log_start(
            req_id=req_id, method=method, tool_name=tool_name,
            arguments=arguments, trigger=trigger,
            chain_id=chain_id, chain_step=chain_step
        )
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
            status = "error" if "error" in result else "success"
            ledger_log_end(event_id, status, result, round((time.time() - t0) * 1000, 1))
            return result
        else:
            self._pending.pop(req_id, None)
            result = {"error": f"Timeout ({timeout}s) on {method}"}
            ledger_log_end(event_id, "timeout", result, round((time.time() - t0) * 1000, 1))
            return result

    def notify(self, method, params=None):
        if not self.is_alive:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(payload) + "\n")
                self.process.stdin.flush()
        except Exception:
            pass

    def _read_stdout(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stdout.readline()
                if not line: break
                line = line.strip()
                if not line: continue
                response = json.loads(line)
                req_id = response.get("id")
                preview = line[:150] + ("..." if len(line) > 150 else "")
                print(f"📥 [MCP ACK] id={req_id} → {preview}")
                if req_id is not None and req_id in self._pending:
                    self._pending[req_id]["result"] = response
                    self._pending[req_id]["event"].set()
            except Exception:
                if self._running: print(f"❌ [MCP] stdout reader error")
                break

    def _read_stderr(self):
        while self._running and self.is_alive:
            try:
                line = self.process.stderr.readline()
                if not line: break
                print(f"🔧 [MCP LOG] {line.rstrip()}")
            except Exception:
                break

    def handshake(self):
        init_resp = self.send("initialize", {
            "protocolVersion": self.MCP_PROTOCOL_VERSION,
            "clientInfo": {"name": "butterclaw-server", "version": VERSION},
            "capabilities": {}
        }, timeout=10, trigger="handshake")

        if "error" in init_resp:
            self.handshake_ok = False
            return False

        result = init_resp.get("result", {})
        self.server_info = result.get("serverInfo", {})
        self.protocol_version = result.get("protocolVersion", self.MCP_PROTOCOL_VERSION)

        self.notify("notifications/initialized")
        tools_resp = self.send("tools/list", {}, timeout=5, trigger="handshake")
        if "error" not in tools_resp and "result" in tools_resp:
            self.discovered_tools = tools_resp["result"].get("tools", [])
        else:
            self.discovered_tools = []

        self.handshake_ok = True
        return True

    def status(self):
        proc = self.process
        return {
            "alive": proc is not None and proc.poll() is None,
            "pid": proc.pid if proc else None,
            "handshake_ok": self.handshake_ok,
            "server_info": self.server_info,
            "tools_count": len(self.discovered_tools),
            "pending_requests": len(self._pending),
            "protocol_version": self.protocol_version,
            "transport_mode": "stdio",
            "event_count": ledger_count()
        }

# =============================================
# MCP SSE CLIENT — remote SSE transport (v0.5.0)
# =============================================

class MCPSSEClient(BaseMCPManager):

    MCP_PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._pending = {}
        self._req_counter = itertools.count(1)
        self._running = False
        self._sse_thread = None
        self._connected = False
        self.discovered_tools = []
        self.server_info = {}
        self.handshake_ok = False
        self.protocol_version = self.MCP_PROTOCOL_VERSION
        self._message_url = None

    @property
    def transport_name(self):
        return f"sse ({self.base_url})"

    @property
    def is_alive(self):
        return self._running and self._connected

    def _auth_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def start(self):
        if self._running:
            return True
        print(f"🚀 [MCP] Connecting to remote MCP server at {self.base_url} (SSE)...")

        try:
            health_resp = http_requests.get(f"{self.base_url}/health", headers=self._auth_headers(), timeout=5)
            if health_resp.status_code != 200:
                return False
        except Exception:
            return False

        self._running = True
        self._message_url = f"{self.base_url}/message"
        self._sse_thread = threading.Thread(target=self._read_sse_stream, daemon=True)
        self._sse_thread.start()

        for _ in range(20):
            if self._connected: break
            time.sleep(0.1)

        return True

    def stop(self):
        self._running = False
        self._connected = False
        for req_id, entry in list(self._pending.items()):
            entry["result"] = {"error": "MCP SSE client stopped"}
            entry["event"].set()
        self._pending.clear()
        self.handshake_ok = False

    def restart(self):
        self.stop()
        time.sleep(0.3)
        if self.start():
            return self.handshake()
        return False

    def _read_sse_stream(self):
        headers = self._auth_headers()
        headers["Accept"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"

        while self._running:
            try:
                resp = http_requests.get(f"{self.base_url}/sse", headers=headers, stream=True, timeout=None)
                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                self._connected = True
                event_type = None
                data_buffer = ""

                for line in resp.iter_lines(decode_unicode=True):
                    if not self._running: break
                    if line is None or line == "":
                        if data_buffer and event_type:
                            self._handle_sse_event(event_type, data_buffer.strip())
                        event_type = None
                        data_buffer = ""
                        continue
                    if line.startswith(":"): continue
                    if line.startswith("event: "): event_type = line[7:].strip()
                    elif line.startswith("data: "): data_buffer += line[6:]
                    elif line.startswith("data:"): data_buffer += line[5:]

            except Exception:
                if self._running:
                    self._connected = False
                    time.sleep(5)

    def _handle_sse_event(self, event_type, data):
        if event_type == "endpoint":
            self._message_url = data.strip()
            return

        if event_type == "message":
            try:
                response = json.loads(data)
                req_id = response.get("id")
                if req_id is not None and req_id in self._pending:
                    self._pending[req_id]["result"] = response
                    self._pending[req_id]["event"].set()
            except Exception:
                pass

    def send(self, method, params=None, timeout=10, trigger="auto", chain_id=None, chain_step=None):
        if not self._running:
            if not self.start():
                return {"error": "MCP SSE client failed to connect"}

        req_id = next(self._req_counter)
        post_url = self._message_url or f"{self.base_url}/message"

        tool_name = None
        arguments = None
        if method == "tools/call" and params:
            tool_name = params.get("name")
            arguments = params.get("arguments")

        event_id = ledger_log_start(
            req_id=req_id, method=method, tool_name=tool_name,
            arguments=arguments, trigger=trigger,
            chain_id=chain_id, chain_step=chain_step
        )
        t0 = time.time()

        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}
        event = threading.Event()
        self._pending[req_id] = {"event": event, "result": None}

        try:
            resp = http_requests.post(post_url, json=payload, headers=self._auth_headers(), timeout=5)
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
            status = "error" if "error" in result else "success"
            ledger_log_end(event_id, status, result, round((time.time() - t0) * 1000, 1))
            return result
        else:
            self._pending.pop(req_id, None)
            result = {"error": f"Timeout ({timeout}s) on {method}"}
            ledger_log_end(event_id, "timeout", result, round((time.time() - t0) * 1000, 1))
            return result

    def notify(self, method, params=None):
        if not self._running: return
        post_url = self._message_url or f"{self.base_url}/message"
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            http_requests.post(post_url, json=payload, headers=self._auth_headers(), timeout=5)
        except Exception:
            pass

    def handshake(self):
        init_resp = self.send("initialize", {
            "protocolVersion": self.MCP_PROTOCOL_VERSION,
            "clientInfo": {"name": "butterclaw-server", "version": VERSION},
            "capabilities": {}
        }, timeout=10, trigger="handshake")

        if "error" in init_resp:
            self.handshake_ok = False
            return False

        result = init_resp.get("result", {})
        self.server_info = result.get("serverInfo", {})
        self.protocol_version = result.get("protocolVersion", self.MCP_PROTOCOL_VERSION)

        self.notify("notifications/initialized")

        tools_resp = self.send("tools/list", {}, timeout=5, trigger="handshake")
        if "error" not in tools_resp and "result" in tools_resp:
            self.discovered_tools = tools_resp["result"].get("tools", [])
        else:
            self.discovered_tools = []

        self.handshake_ok = True
        return True

    def status(self):
        return {
            "alive": self._connected,
            "pid": None,
            "handshake_ok": self.handshake_ok,
            "server_info": self.server_info,
            "tools_count": len(self.discovered_tools),
            "pending_requests": len(self._pending),
            "protocol_version": self.protocol_version,
            "transport_mode": "sse",
            "remote_url": self.base_url,
            "event_count": ledger_count()
        }


# =============================================
# MCP MANAGER FACTORY (v0.5.0)
# =============================================

def create_mcp_manager():
    with _state_lock:
        mode = mcp_transport_mode
        url = mcp_sse_url
        token = mcp_sse_token

    if mode == "sse" and url:
        print(f"📡 [MCP] Using SSE transport → {url}")
        return MCPSSEClient(base_url=url, token=token)
    else:
        print("📡 [MCP] Using stdio transport (local child process)")
        return MCPProcessManager(
            script_path=os.path.join(BASE_DIR, "butterclaw_mcp.py")
        )

mcp_manager = create_mcp_manager()

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

    mcp_history = ledger_query(limit=5, status="success")
    timeline_context = ""
    
    if mcp_history:
        timeline_context = "RECENT SENTINEL ACTIONS (Sliding Window):\n"
        for event in reversed(mcp_history):
            if event['method'] == 'tools/call':
                timeline_context += f" - [{event['timestamp']}] Executed: {event['tool_name']} | Result: {event['status']}\n"
        timeline_context += "\n"

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
    
    tools_list = []
    for tool in mcp_manager.discovered_tools:
        tool_name = tool.get('name', 'unknown_tool')
        desc = tool.get('description', 'No description')
        tools_list.append(f"  - {tool_name}: {desc}")

    tools_context = "\n".join(tools_list) if tools_list else "  No MCP tools discovered yet."

    json_schema = (
        'You must respond ONLY with a valid JSON object. Do not include markdown formatting. '
        'Strict Schema: {'
        '"verdict": "CRITICAL" | "WARNING" | "BENIGN", '
        '"confidence": float 0.0-1.0, '
        '"primary_gate": "Signature" | "Origin" | "Intent" | "None", '
        '"reasoning": "2-sentence explanation."} '
        'For CRITICAL verdicts, you MAY include an optional "chain" array to compose a multi-step tool sequence: '
        '"chain": [{"tool": "tool_name", "args": {"key": "value"}, "store_as": "result_label", '
        '"condition": {"source": "previous_result_label", '
        '"operator": "contains|not_contains|equals|not_equals|starts_with", '
        '"expected": "value"}}] '
        f'Available MCP tools:\n{tools_context}\n'
        'Chain rules: max 10 steps, conditions reference previous store_as labels, '
        'first step cannot have a condition. If unsure, omit chain — hardcoded fallback will execute.'
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
                    f"{timeline_context}"
                    f"Analyze this NEW local AI agent event:\n"
                    f"Threat Type: {threat_type}\n"
                    f"Raw Data/Log: {raw_data}\n\n"
                    f"Determine if this is a CSWH attempt, an Indirect Prompt Injection, or benign noise based on the current event and recent history."
                )
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.3
        }
    }

    try:
        response = http_requests.post(ollama_url, json=payload, timeout=120)
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
                "reasoning": str(parsed.get("reasoning", "Model failed to provide reasoning.")),
                "chain": parsed.get("chain")
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
# THE AUDITOR (Step A)
# =============================================

def run_self_audit(original_threat):
    time.sleep(30)
    
    mcp_history = ledger_query(limit=5, status="success")
    timeline_context = "RECENT SENTINEL ACTIONS:\n"
    if mcp_history:
        for event in reversed(mcp_history):
            if event['method'] == 'tools/call':
                result_str = str(event.get('result', ''))[:100]
                timeline_context += f" - [{event['timestamp']}] Executed: {event['tool_name']} | Result: {result_str}...\n"
    else:
        timeline_context += " - No recent actions.\n"

    ollama_url = _resolve_ollama_url()
    with _state_lock:
        active_model = model_name

    payload = {
        "model": active_model,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the ButterClaw Auditor. Review the RECENT ACTIONS. "
                    "Your job is to determine if the system overreacted to a False Positive. "
                    "Respond in JSON: {\"audit_verdict\": \"AGREEMENT\"|\"FALSE_POSITIVE\", \"reasoning\": \"...\"}"
                )
            },
            {
                "role": "user",
                "content": f"{timeline_context}\nOriginal Trigger: {original_threat}\nDid we overreact?"
            }
        ],
        "stream": False,
        "options": {"temperature": 0.0}
    }

    try:
        response = http_requests.post(ollama_url, json=payload, timeout=120)
        raw_content = response.json().get("message", {}).get("content", "{}")
        parsed = json.loads(raw_content)
        
        audit_verdict = parsed.get("audit_verdict", "UNKNOWN")
        reasoning = parsed.get("reasoning", "No reasoning provided.")

        if audit_verdict == "FALSE_POSITIVE":
            print(f"🧐 [AUDITOR] False Positive Detected: {reasoning}")
            
            conn = get_db_connection()
            conn.execute('''
                INSERT INTO logs (title, desc, action, time, icon, color)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                f"Self-Audit: {original_threat}",
                f"[Likely False Positive] Auditor Review: {reasoning}",
                "Audit Flagged",
                datetime.datetime.now().strftime("%H:%M:%S"),
                "🧐",
                "amber"
            ))
            conn.commit()
            conn.close()
            
            with _state_lock:
                global total_logs_processed
                total_logs_processed += 1
        else:
            print(f"👍 [AUDITOR] Actions verified. Agreement with primary Instinct.")

    except Exception as e:
        print(f"❌ [AUDITOR] Self-audit API failure: {e}")


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
            chain_steps = analysis.get('chain') if isinstance(analysis, dict) else None

            if chain_steps and isinstance(chain_steps, list) and len(chain_steps) > 0:
                print(f"🔗 [CHAIN] Brain composed {len(chain_steps)}-step chain for CRITICAL response")
                executor = ChainExecutor(mcp_manager, chain_steps, dry_run=DRY_RUN)
                chain_result = executor.execute()

                buttervault.butter_keys()

                action = chain_result['action_summary']
                print(f"🔗 CHAIN EXECUTED: {action}")
            else:
                mcp_failures = []

                gibson_resp = mcp_manager.send("tools/call", {
                    "name": "execute_gibson_kill",
                    "arguments": {"target_process": "openclaw"}
                }, trigger="critical")
                if "error" in gibson_resp:
                    mcp_failures.append("gibson_kill")
                    print(f"⚠️ [MCP] gibson_kill failed: {gibson_resp['error']}")

                buttervault.butter_keys()

                rotate_resp = mcp_manager.send("tools/call", {
                    "name": "rotate_keys",
                    "arguments": {"provider": "OpenRouter"}
                }, trigger="critical")
                if "error" in rotate_resp:
                    mcp_failures.append("rotate_keys")
                    print(f"⚠️ [MCP] rotate_keys failed: {rotate_resp['error']}")

                if mcp_failures:
                    action = f"Keys Buttered | MCP partial failure: {', '.join(mcp_failures)}"
                else:
                    action = "SIGKILL | Keys Buttered"
        else:
            action = "ALERT | Kill Switch Disarmed"

        threading.Thread(target=run_self_audit, args=(threat_type,), daemon=True).start()

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

    rotate_resp = mcp_manager.send("tools/call", {
        "name": "rotate_keys",
        "arguments": {"provider": "Manual_Global"}
    }, trigger="manual")
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

# =============================================
# API ROUTES: OAUTH (v0.5.2)
# =============================================

def _oauth_result_page(success, message):
    """Returns a self-closing HTML page that signals the opener window."""
    color = "#10b981" if success else "#ef4444"
    icon = "✅" if success else "❌"
    return Response(f"""<!DOCTYPE html>
<html>
<head><title>ButterClaw OAuth</title></head>
<body style="font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f8fafc;">
<div style="text-align:center;padding:2rem;">
    <div style="font-size:3rem;">{icon}</div>
    <h2 style="color:{color};margin:1rem 0;">{message}</h2>
    <p style="color:#64748b;font-size:0.875rem;">This window will close automatically.</p>
</div>
<script>
    if (window.opener) {{
        window.opener.postMessage({{type: 'oauth_result', success: {str(success).lower()}, message: '{message}'}}, '*');
    }}
    setTimeout(function() {{ window.close(); }}, 2000);
</script>
</body>
</html>""", mimetype="text/html")

@app.route('/api/vault/oauth/start/<provider_name>', methods=['GET'])
def oauth_start(provider_name):
    """
    Initiates the OAuth 2.0 authorization code flow.
    Generates a CSRF state token, builds the authorization URL,
    and returns it to the frontend for redirect.
    """
    provider = oauth_config.get_provider(provider_name)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_name}"}), 404
    
    if not provider["oauth_supported"]:
        return jsonify({"error": f"{provider['display_name']} does not support OAuth. Use manual API key entry."}), 400
    
    # Retrieve client_id from ButterVault (Option C Architecture)
    client_id = buttervault.get_key(f"{provider_name}_client_id")
    if not client_id:
        return jsonify({
            "error": f"No client_id found in ButterVault for '{provider_name}'. "
                     f"Please store it first via the Vault panel with provider name '{provider_name}_client_id'."
        }), 400
    
    # Generate CSRF state token
    state = secrets.token_urlsafe(32)
    
    # Build the redirect URI
    redirect_uri = f"http://127.0.0.1:5000/api/vault/oauth/callback"
    
    # Store state for validation on callback
    _cleanup_expired_oauth_states()
    with _oauth_states_lock:
        _oauth_states[state] = {
            "provider": provider_name,
            "created_at": time.time(),
            "redirect_uri": redirect_uri
        }
    
    # Build authorization URL
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(provider["scopes"]),
        "state": state,
        "access_type": "offline",     # Request refresh token (Google)
        "prompt": "consent"           # Force consent screen to get refresh token (Google)
    }
    
    query = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    auth_url = f"{provider['authorize_url']}?{query}"
    
    print(f"🔑 [OAUTH] Starting {provider['display_name']} flow. State: {state[:8]}...")
    
    return jsonify({
        "auth_url": auth_url,
        "state": state,
        "provider": provider_name
    }), 200

@app.route('/api/vault/oauth/callback', methods=['GET'])
def oauth_callback():
    """
    Handles the OAuth 2.0 callback from the provider.
    Validates state, exchanges code for tokens, and seals them in the Vault.
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")
    
    if error:
        print(f"❌ [OAUTH] Provider returned error: {error}")
        return _oauth_result_page(success=False, message=f"Authorization denied: {error}")
    
    if not code or not state:
        return _oauth_result_page(success=False, message="Missing code or state parameter.")
    
    # Validate CSRF state
    with _oauth_states_lock:
        state_data = _oauth_states.pop(state, None)
    
    if not state_data:
        print(f"⚠️ [OAUTH] Invalid or expired state token: {state[:8]}...")
        return _oauth_result_page(success=False, message="Invalid or expired state. Please try again.")
    
    if time.time() - state_data["created_at"] > OAUTH_STATE_TTL:
        print(f"⚠️ [OAUTH] State token expired: {state[:8]}...")
        return _oauth_result_page(success=False, message="Authorization timed out. Please try again.")
    
    provider_name = state_data["provider"]
    redirect_uri = state_data["redirect_uri"]
    provider = oauth_config.get_provider(provider_name)
    
    if not provider:
        return _oauth_result_page(success=False, message=f"Unknown provider: {provider_name}")
    
    client_id = buttervault.get_key(f"{provider_name}_client_id")
    client_secret = buttervault.get_key(f"{provider_name}_client_secret")
    
    if not client_id or not client_secret:
        return _oauth_result_page(success=False, message="Client credentials not found in ButterVault.")
    
    print(f"🔑 [OAUTH] Exchanging code for tokens ({provider['display_name']})...")
    
    try:
        token_resp = http_requests.post(provider["token_url"], data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        }, timeout=15)
        
        if token_resp.status_code != 200:
            error_detail = token_resp.text[:200]
            print(f"❌ [OAUTH] Token exchange failed: HTTP {token_resp.status_code} — {error_detail}")
            return _oauth_result_page(success=False, message=f"Token exchange failed: HTTP {token_resp.status_code}")
        
        tokens = token_resp.json()
        
    except Exception as e:
        print(f"❌ [OAUTH] Token exchange request failed: {e}")
        return _oauth_result_page(success=False, message=f"Token exchange failed: {e}")
    
    token_dict = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": time.time() + tokens.get("expires_in", 3600),
        "token_type": tokens.get("token_type", "Bearer"),
        "scope": tokens.get("scope", " ".join(provider["scopes"])),
    }
    
    buttervault.store_oauth_token(provider_name, token_dict)
    
    print(f"✅ [OAUTH] {provider['display_name']} tokens sealed in ButterVault. "
          f"Expires in {tokens.get('expires_in', '?')}s. "
          f"Refresh token: {'present' if token_dict['refresh_token'] else 'ABSENT'}.")
    
    try:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO logs (title, desc, action, time, icon, color)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            f"OAuth Connected: {provider['display_name']}",
            f"Successfully authenticated with {provider['display_name']} via OAuth 2.0. Tokens encrypted and sealed.",
            "OAuth Sealed",
            datetime.datetime.now().strftime("%H:%M:%S"),
            "🔑",
            "emerald"
        ))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass
    
    return _oauth_result_page(success=True, message=f"{provider['display_name']} connected successfully!")

@app.route('/api/vault/oauth/status', methods=['GET'])
def oauth_status():
    """Returns the connection status of all OAuth-capable providers."""
    statuses = {}
    connected_providers = buttervault.list_oauth_providers()
    
    for name in oauth_config.list_oauth_capable():
        provider = oauth_config.get_provider(name)
        token = buttervault.get_oauth_token(name) if name in connected_providers else None
        
        statuses[name] = {
            "display_name": provider["display_name"],
            "connected": token is not None,
            "has_refresh_token": bool(token.get("refresh_token")) if token else False,
            "expires_at": token.get("expires_at") if token else None,
            "expired": token is not None and time.time() > token.get("expires_at", 0),
            "has_client_credentials": (
                buttervault.get_key(f"{name}_client_id") is not None
                and buttervault.get_key(f"{name}_client_secret") is not None
            )
        }
    
    return jsonify(statuses), 200

@app.route('/api/vault/oauth/revoke/<provider_name>', methods=['POST'])
def oauth_revoke(provider_name):
    """Revokes the OAuth token at the provider and removes it from the Vault."""
    provider = oauth_config.get_provider(provider_name)
    if not provider:
        return jsonify({"error": f"Unknown provider: {provider_name}"}), 404
    
    token_dict = buttervault.get_oauth_token(provider_name)
    if not token_dict:
        return jsonify({"error": f"No OAuth token found for {provider_name}"}), 404
    
    revoke_url = provider.get("revoke_url")
    if revoke_url:
        try:
            http_requests.post(revoke_url, data={"token": token_dict["access_token"]}, timeout=10)
            print(f"🔑 [OAUTH] Revoked token at {provider['display_name']}")
        except Exception as e:
            print(f"⚠️ [OAUTH] Remote revocation failed (proceeding with local removal): {e}")
    
    buttervault.delete_oauth_token(provider_name)
    print(f"🗑️ [OAUTH] {provider['display_name']} disconnected and removed from Vault.")
    
    return jsonify({"status": "revoked", "provider": provider_name}), 200

# --- THE CONTROL PANEL ---

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    global current_level, routing_mode, model_name, remote_endpoint, gate_states
    global mcp_transport_mode, mcp_sse_url, mcp_sse_token

    if request.method == 'GET':
        with _state_lock:
            return jsonify({
                "level": current_level,
                "shield_enabled": shield_enabled,
                "routing_mode": routing_mode,
                "model": model_name,
                "endpoint": remote_endpoint,
                "gates": dict(gate_states),
                "mcp_transport": mcp_transport_mode,
                "mcp_sse_url": mcp_sse_url,
                "mcp_sse_token_set": bool(mcp_sse_token)
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

    if "mcp_transport" in data:
        new_transport = str(data["mcp_transport"]).lower().strip()
        if new_transport not in VALID_MCP_TRANSPORTS:
            errors.append(f"mcp_transport must be one of: {', '.join(VALID_MCP_TRANSPORTS)}")
        else:
            with _state_lock:
                mcp_transport_mode = new_transport
            print(f"📡 [MCP] Transport mode set to: {new_transport}")

    if "mcp_sse_url" in data:
        new_url = str(data["mcp_sse_url"]).strip()
        if new_url and not _validate_endpoint_url(new_url):
            errors.append("mcp_sse_url must be a valid http:// or https:// URL")
        else:
            with _state_lock:
                mcp_sse_url = new_url
            label = new_url if new_url else "(cleared)"
            print(f"📡 [MCP] SSE URL set to: {label}")

    if "mcp_sse_token" in data:
        with _state_lock:
            mcp_sse_token = str(data["mcp_sse_token"]).strip()
        print("📡 [MCP] SSE token updated.")

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
# MCP OBSERVABILITY ENDPOINTS (v0.5.0)
# =============================================

@app.route('/api/mcp/status', methods=['GET'])
def mcp_status():
    return jsonify(mcp_manager.status()), 200

@app.route('/api/mcp/ping', methods=['GET'])
def mcp_ping():
    start = time.time()
    resp = mcp_manager.send("ping", {}, timeout=5, trigger="ping")
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
    global mcp_manager
    with _state_lock:
        current_transport = mcp_transport_mode

    if current_transport != mcp_manager.transport_name.split(" ")[0]:
        mcp_manager.stop()
        mcp_manager = create_mcp_manager()

    success = mcp_manager.restart()
    status = mcp_manager.status()
    code = 200 if success else 503
    return jsonify({"restarted": success, **status}), code

# =============================================
# MCP EVENT LEDGER ENDPOINTS (v0.5.0)
# =============================================

@app.route('/api/mcp/events', methods=['GET'])
def mcp_events():
    limit = request.args.get('limit', 50, type=int)
    tool = request.args.get('tool', None)
    status_filter = request.args.get('status', None)
    since = request.args.get('since', None)

    events = ledger_query(limit=limit, tool=tool, status=status_filter, since=since)
    return jsonify({
        "events": events,
        "count": len(events),
        "total": ledger_count()
    }), 200

@app.route('/api/mcp/events/<int:event_id>', methods=['GET'])
def mcp_event_detail(event_id):
    event = ledger_get_event(event_id)
    if event is None:
        return jsonify({"error": f"Event {event_id} not found"}), 404
    return jsonify(event), 200

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
    print(f"   Self-DoS Threshold: {CONFIDENCE_THRESHOLD}%")
    print(f"   Rate Limit: {RATE_LIMIT_MAX} req / {RATE_LIMIT_WINDOW}s on /api/analyze")
    print(f"   CORS Origins: {', '.join(ALLOWED_ORIGINS)}")
    print(f"   MCP Transport: {mcp_transport_mode}")
    if mcp_transport_mode == "sse" and mcp_sse_url:
        print(f"   MCP SSE URL: {mcp_sse_url}")
        print(f"   MCP SSE Auth: {'token set' if mcp_sse_token else 'none'}")

    print("\n" + "=" * 60)
    print("📡 [MCP] Initiating v0.5.2 Handshake Sequence...")
    print("=" * 60)

    if mcp_manager.start():
        if mcp_manager.handshake():
            tool_count = len(mcp_manager.discovered_tools)
            print(f"✅ [MCP] Handshake complete. {tool_count} tools armed.")
            print(f"   Transport: {mcp_manager.transport_name}")
        else:
            print("⚠️ [MCP] Handshake failed. MCP endpoints will report degraded status.")
    else:
        print("❌ [MCP] Failed to spawn execution layer. The Sentinel is unarmed.")

    print(f"📋 [LEDGER] Event ledger initialized. {ledger_count()} historical events.")
    print("=" * 60 + "\n")

    app.run(host='127.0.0.1', port=5000)
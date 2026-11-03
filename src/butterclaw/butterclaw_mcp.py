"""
ButterClaw v0.9.3 — The Claws (MCP Execution Layer) - src layout
=====================================================================
Changelog:
  [v0.3]   Context Shift: Local keys destroyed by ButterVault.
           rotate_keys() simulates external provider API revocation.
           Added True MCP Protocol server scaffolding (stdio preparation).
  [v0.3.1] Stability patches and self-DoS prevention.
  [v0.4.0] Full MCP Protocol compliance:
           - protocolVersion / serverInfo in initialize
           - tools/list with inputSchema (MCP standard)
           - tools/call returns content array format
           - ping support
           - notifications/initialized handling
           - Expanded tool registry (system_status, scan_port, log_event)
           - Dispatch table architecture (no more if/elif chains)
  [v0.4.1] QA Sterilization Patch:
           - M1: Error responses now correlate to request id when available
           - M2: Argument validation against inputSchema before dispatch
           - M3: Module-level basicConfig documented as architecturally correct
           - M4: Pre-initialization guard on tools/call (MCP spec compliance)
  [v0.5.0] The Nervous System:
           - Transport abstraction: main loop now uses BaseTransport interface
           - CLI flags: --transport stdio|sse, --host, --port, --token
           - SSE transport runs a threaded HTTP server (stdlib, zero new deps)
           - stdio remains the default for local child process mode
           - Protocol logic unchanged — only I/O layer refactored
  [v0.9.3] SkillGuard Supply-Chain & TOCTOU Defense:
           - Added SkillGuard integration (audit_skill, load_skill_stage)
           - M5: Runtime Merkle verification & session taint capability gate
           - M10: Path traversal containment on skill resource loads

*** KINETIC OS ACTIONS REMAIN IN DRY RUN / SIMULATION MODE ***
"""

import argparse
import logging
import time
import json
import sys
import os
import platform
import socket
from pathlib import Path

from butterclaw.mcp_transport import create_transport
from butterclaw.skill_guard import SkillGuard

# =====================================================================
# LOGGING — strictly stderr to protect the JSON-RPC stdout pipe
# [M3] Module-level basicConfig is architecturally correct here.
# =====================================================================

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger("butterclaw.mcp")

# =====================================================================
# CONFIGURATION
# =====================================================================

VERSION = "0.9.3"
PROTOCOL_VERSION = "2024-11-05"  # MCP spec version this server speaks
# Set BUTTERCLAW_MCP_DRY_RUN=false to enable live kinetic actions
DRY_RUN = os.environ.get("BUTTERCLAW_MCP_DRY_RUN", "true").lower() != "false"

# Strict allowlists for SSRF prevention [M9]
SCAN_PORT_HOST_ALLOWLIST = {"127.0.0.1", "localhost", "host.docker.internal"}
SCAN_PORT_ALLOWLIST = {11434}  # Ollama default

# Shared SkillGuard engine instance
SKILL_GUARD = SkillGuard()


# =====================================================================
# TOOL IMPLEMENTATIONS
# =====================================================================

def rotate_keys(provider="OpenRouter"):
    """
    [v0.3] Local keys are now physically shredded by the ButterVault.
    This simulates reaching out to the provider's external API
    to invalidate the old token globally.
    """
    logger.warning(f"🌐 EXT-ROTATE: Requesting external key revocation for {provider}...")
    time.sleep(0.5)

    if DRY_RUN:
        logger.info(f"🛡️ [DRY RUN] Would have POSTed to {provider} API to roll tokens globally.")
        return f"[DRY RUN] Key rotation simulated for {provider}. External tokens invalidated."
    else:
        raise NotImplementedError(
            f"Production key rotation for {provider} is not yet implemented. "
            f"Set DRY_RUN = True or implement real .env key overwrite logic here."
        )


def execute_gibson_kill(target_process="openclaw"):
    """Simulates hunting down a rogue process and issuing a SIGKILL."""
    logger.warning(f"☢️ GIBSON KILL SWITCH: Hunting unauthorized process '{target_process}'...")
    time.sleep(0.5)

    if DRY_RUN:
        logger.info(f"🛡️ [DRY RUN] Found '{target_process}' running on PID 8842.")
        logger.info(f"🛡️ [DRY RUN] Would have executed: pkill -9 {target_process}")
        logger.info(f"🛡️ [DRY RUN] Process neutralized. The Sentinel rests.")
        return f"[DRY RUN] Process '{target_process}' terminated (simulated PID 8842)."
    else:
        raise NotImplementedError(
            f"Production process kill for '{target_process}' is not yet implemented."
        )


def system_status(active_skill=None):
    """Returns current ButterClaw system health metrics."""
    return json.dumps({
        "version": VERSION,
        "dry_run": DRY_RUN,
        "platform": platform.system(),
        "python": platform.python_version(),
        "active_skill_taint": active_skill,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }, indent=2)


def scan_port(host="127.0.0.1", port=11434):
    """Quick TCP connect check — is a service alive at host:port?"""
    if str(host) not in SCAN_PORT_HOST_ALLOWLIST:
        return f"Error: Host '{host}' not permitted by security policy."
    if int(port) not in SCAN_PORT_ALLOWLIST:
        return f"Error: Port {port} not permitted by security policy."

    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return f"Port {host}:{port} is OPEN."
    except (ConnectionRefusedError, TimeoutError, OSError) as e:
        return f"Port {host}:{port} is CLOSED or unreachable ({type(e).__name__})."


def log_event(severity="INFO", message="No message provided"):
    """Writes a structured event to the MCP stderr log stream for audit trails."""
    severity = severity.upper()
    if severity not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        severity = "INFO"
    entry = f"[{severity}] [{time.strftime('%H:%M:%S')}] {message}"
    logger.log(getattr(logging, severity, logging.INFO), entry)
    return f"Logged: {entry}"


def audit_skill(skill_path):
    """
    [v0.9.3] Pre-flight static & Merkle scanner for SKILL.md packages.
    Inspects YAML frontmatter, Markdown body, references/, and scripts/.
    """
    report = SKILL_GUARD.audit_and_attest(skill_path)
    return json.dumps(report, indent=2)


# =====================================================================
# TOOL REGISTRY — MCP-compliant with inputSchema
# =====================================================================

TOOL_DEFINITIONS = [
    {
        "name": "execute_gibson_kill",
        "description": "Kinetic Response: Terminates a rogue process by name using OS-level SIGKILL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_process": {
                    "type": "string",
                    "description": "Name of the process to terminate."
                }
            },
            "required": ["target_process"]
        }
    },
    {
        "name": "rotate_keys",
        "description": "Kinetic Response: Invalidates provider API tokens globally via external API call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Name of the API provider whose keys should be rotated."
                }
            },
            "required": ["provider"]
        }
    },
    {
        "name": "system_status",
        "description": "Returns current ButterClaw system health: version, platform, DRY_RUN state, and active skill taint.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "scan_port",
        "description": "Quick TCP connect check to see if a host:port is alive (e.g., Ollama at 11434).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Target hostname or IP.",
                    "default": "127.0.0.1"
                },
                "port": {
                    "type": "integer",
                    "description": "Target port number.",
                    "default": 11434
                }
            },
            "required": []
        }
    },
    {
        "name": "log_event",
        "description": "Writes a structured event to the MCP log stream (stderr). Useful for audit trails.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    "description": "Log severity level.",
                    "default": "INFO"
                },
                "message": {
                    "type": "string",
                    "description": "The event message to log."
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "audit_skill",
        "description": "Pre-flight static scanner for SKILL.md directories. Computes SHA-256 Merkle root and records APPROVED or QUARANTINED status in SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_path": {
                    "type": "string",
                    "description": "Filesystem path to the SKILL.md package directory."
                }
            },
            "required": ["skill_path"]
        }
    },
    {
        "name": "load_skill_stage",
        "description": "Stage 2/3 loader for attested SKILL.md packages. Verifies Merkle integrity before returning SKILL.md or references/ content and taints the active session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Registered name of the skill to activate or read from."
                },
                "resource_path": {
                    "type": "string",
                    "description": "Relative file path inside the skill folder (defaults to 'SKILL.md').",
                    "default": "SKILL.md"
                }
            },
            "required": ["skill_name"]
        }
    }
]

# Build allowed-args lookup from inputSchema for validation [M2]
_TOOL_ALLOWED_ARGS = {}
for _td in TOOL_DEFINITIONS:
    _schema = _td.get("inputSchema", {})
    _TOOL_ALLOWED_ARGS[_td["name"]] = set(_schema.get("properties", {}).keys())

# Dispatch table — maps tool name → callable
TOOL_DISPATCH = {
    "execute_gibson_kill": execute_gibson_kill,
    "rotate_keys":         rotate_keys,
    "system_status":       lambda **_: system_status(),
    "scan_port":           scan_port,
    "log_event":           log_event,
    "audit_skill":         audit_skill,
}


# =====================================================================
# MCP SERVER — Protocol Handler (transport-agnostic)
# =====================================================================

class ButterClawMCPServer:
    """
    MCP-compliant JSON-RPC 2.0 protocol handler.
    Transport-agnostic: takes a dict in, returns a dict out.
    The I/O layer (stdio, SSE, etc.) is handled by mcp_transport.
    """

    def __init__(self, skill_guard=None):
        self.initialized = False
        self.tools = TOOL_DEFINITIONS
        self.skill_guard = skill_guard or SKILL_GUARD
        self.active_skill = None  # [M5] Tracks Stage 2/3 session taint

        # Instance-level dispatch binds stateful handlers cleanly
        self.dispatch = dict(TOOL_DISPATCH)
        self.dispatch["system_status"] = lambda **_: system_status(active_skill=self.active_skill)
        self.dispatch["load_skill_stage"] = self._handle_load_skill_stage

    def _handle_load_skill_stage(self, skill_name, resource_path="SKILL.md"):
        """
        [M5 / M10] Verifies Merkle root before Stage 2/3 progressive disclosure load.
        Taints the session with active_skill on success; triggers kinetic defense on TOCTOU tampering.
        """
        is_valid, reason, record = self.skill_guard.verify_runtime_integrity(skill_name)
        if not is_valid:
            logger.error(f"🚨 [SkillGuard] Stage load blocked for '{skill_name}': {reason}")
            if "TOCTOU MERKLE MISMATCH" in reason:
                kill_msg = execute_gibson_kill(target_process="openclaw")
                rot_msg = rotate_keys(provider="OpenRouter")
                raise PermissionError(f"{reason} | KINETIC RESPONSE: {kill_msg} | {rot_msg}")
            raise PermissionError(f"SkillGuard blocked '{skill_name}': {reason}")

        # [M10] Prevent relative path traversal outside the attested skill directory
        skill_dir = Path(record["package_path"]).resolve()
        target_file = (skill_dir / resource_path).resolve()
        if not str(target_file).startswith(str(skill_dir)) or not target_file.is_file():
            raise PermissionError(f"Invalid or unauthorized skill resource path: '{resource_path}'")

        # Apply session taint
        self.active_skill = skill_name
        logger.info(f"🔒 [SkillGuard] Session tainted by active skill '{skill_name}' (loaded '{resource_path}').")
        return target_file.read_text(encoding="utf-8", errors="replace")

    # ----- MCP Method Handlers -----

    def handle_initialize(self, params, req_id):
        self.initialized = True
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {
                    "name": "butterclaw-mcp",
                    "version": VERSION
                },
                "capabilities": {
                    "tools": {"listChanged": False}
                }
            }
        }

    def handle_initialized_notification(self, params):
        logger.info("📡 [MCP] Client acknowledged initialization.")
        return None

    def handle_ping(self, params, req_id):
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    def handle_tools_list(self, params, req_id):
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": self.tools}
        }

    def handle_tools_call(self, params, req_id):
        # [M4] Guard: reject tools/call before initialization (MCP spec compliance)
        if not self.initialized:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32002, "message": "Server not initialized. Send 'initialize' first."}
            }

        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name not in self.dispatch:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
            }

        # [M2] Validate arguments against inputSchema before dispatch
        allowed_args = _TOOL_ALLOWED_ARGS.get(tool_name, set())
        unknown_args = set(tool_args.keys()) - allowed_args
        if unknown_args:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Invalid arguments: {', '.join(sorted(unknown_args))}. Allowed: {', '.join(sorted(allowed_args)) or '(none)'}"}],
                    "isError": True
                }
            }

        # [M5] Runtime SkillGuard Taint & Anti-TOCTOU Gate
        if self.active_skill is not None:
            is_valid, reason, record = self.skill_guard.verify_runtime_integrity(self.active_skill)
            if not is_valid:
                logger.error(f"🚨 [Gate M5] Integrity failure on active skill '{self.active_skill}': {reason}")
                kill_res = execute_gibson_kill(target_process="openclaw")
                rot_res = rotate_keys(provider="OpenRouter")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"[GATE M5 BLOCK] {reason} | {kill_res} | {rot_res}"}],
                        "isError": True
                    }
                }

            allowed_mcp_tools = set(record.get("allowed_mcp_tools", []))
            if tool_name not in allowed_mcp_tools:
                logger.warning(f"🛡️ [Gate M5] Tainted session ('{self.active_skill}') attempted unauthorized tool '{tool_name}'.")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"[GATE M5 BLOCK] Active skill '{self.active_skill}' is not authorized to invoke tool '{tool_name}'."}],
                        "isError": True
                    }
                }

        try:
            result = self.dispatch[tool_name](**tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(result)}],
                    "isError": False
                }
            }
        except Exception as e:
            logger.error(f"❌ Tool '{tool_name}' failed: {e}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool error: {e}"}],
                    "isError": True
                }
            }

    # ----- Method Dispatch Table -----

    METHOD_MAP = {
        "initialize":                "handle_initialize",
        "notifications/initialized": "handle_initialized_notification",
        "ping":                      "handle_ping",
        "tools/list":                "handle_tools_list",
        "tools/call":                "handle_tools_call",
    }

    def route(self, request):
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        handler_name = self.METHOD_MAP.get(method)

        if handler_name is None:
            if req_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            return None

        handler = getattr(self, handler_name)

        if req_id is None:
            handler(params)
            return None

        return handler(params, req_id)


# =====================================================================
# CLI ARGUMENT PARSER
# =====================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="ButterClaw MCP Execution Layer — Model Context Protocol server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Transport modes:
  stdio   Read JSON-RPC from stdin, write to stdout. (default)
          Used when spawned as a child process by server.py.

  sse     Run a threaded HTTP server. Clients connect via GET /sse
          for Server-Sent Events and POST /message for JSON-RPC.
          Used for remote or network-accessible MCP clients.

Examples:
  python butterclaw_mcp.py                              # stdio (default)
  python butterclaw_mcp.py --transport sse               # SSE on 127.0.0.1:5001
  python butterclaw_mcp.py --transport sse --port 6001   # SSE on custom port
  python butterclaw_mcp.py --transport sse --bind 0.0.0.0 --token mysecret
        """
    )
    parser.add_argument(
        "--version", action="version", version=f"ButterClaw MCP v{VERSION}"
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport mode: stdio (default) or sse."
    )
    parser.add_argument(
        "--bind", default="127.0.0.1", metavar="HOST",
        help="Bind address for SSE transport (default: 127.0.0.1). "
             "Use 0.0.0.0 for remote access (requires --token)."
    )
    parser.add_argument(
        "--port", type=int, default=5001,
        help="Port for SSE transport (default: 5001)."
    )
    parser.add_argument(
        "--token", default=None, metavar="SECRET",
        help="Bearer token for SSE transport authentication. "
             "Required when binding to 0.0.0.0."
    )
    return parser.parse_args()


# =====================================================================
# MAIN LOOP — Transport-agnostic
# =====================================================================

def main():
    args = parse_args()

    # Safety check: remote binding without a token is dangerous
    if args.transport == "sse" and args.bind == "0.0.0.0" and not args.token:
        logger.error("❌ Binding SSE to 0.0.0.0 without --token is not allowed.")
        logger.error("   Use --token <secret> to require authentication for remote clients.")
        sys.exit(1)

    logger.info(f"🦞 ButterClaw MCP v{VERSION} starting (PID {os.getpid()})...")
    logger.info(f"   Protocol:  {PROTOCOL_VERSION}")
    logger.info(f"   Transport: {args.transport}")
    logger.info(f"   DRY_RUN:   {DRY_RUN}")
    logger.info(f"   Tools:     {len(TOOL_DEFINITIONS)}")

    if args.transport == "sse":
        logger.info(f"   Bind:      {args.bind}:{args.port}")
        logger.info(f"   Auth:      {'token required' if args.token else 'none (local only)'}")

    # Create the transport
    transport = create_transport(
        transport_type=args.transport,
        host=args.bind,
        port=args.port,
        token=args.token
    )

    # Create the protocol handler
    server = ButterClawMCPServer()

    # Start the transport
    transport.start()

    # Track last successfully parsed request for error correlation [M1]
    last_request = {}

    try:
        while True:
            try:
                request = transport.read()

                if request is None:
                    logger.info("📡 [MCP] Transport closed. Shutting down.")
                    break

                last_request = request  # [M1] save for error correlation
                response = server.route(request)

                if response is not None:
                    transport.write(response)

            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON parse error: {e}")
                err = {"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": f"Parse error: {e}"}}
                transport.write(err)

            except Exception as e:
                correlated_id = last_request.get("id") if last_request else None
                logger.error(f"❌ Unhandled exception (id={correlated_id}): {e}")
                err = {"jsonrpc": "2.0", "id": correlated_id,
                       "error": {"code": -32603, "message": f"Internal error: {e}"}}
                transport.write(err)
                last_request = {}

    except KeyboardInterrupt:
        logger.info("📡 [MCP] Interrupted. Shutting down.")
    finally:
        transport.stop()
        logger.info(f"🦞 ButterClaw MCP v{VERSION} stopped.")


if __name__ == "__main__":
    main()
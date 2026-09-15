"""
ButterClaw v0.6.4 — The Claws (MCP Execution Layer)
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

from mcp_transport import create_transport

# =====================================================================
# LOGGING — strictly stderr to protect the JSON-RPC stdout pipe
# [M3] Module-level basicConfig is architecturally correct here.
# This file runs as a standalone subprocess (spawned by server.py),
# never imported as a library. The v0.3.2 I6 fix (move to function
# scope) addressed import-time collision, which does not apply.
# =====================================================================

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger("butterclaw.mcp")

# =====================================================================
# CONFIGURATION
# =====================================================================

VERSION = "0.6.3.2"
PROTOCOL_VERSION = "2024-11-05"  # MCP spec version this server speaks
# Set BUTTERCLAW_MCP_DRY_RUN=false to enable live kinetic actions
DRY_RUN = os.environ.get("BUTTERCLAW_MCP_DRY_RUN", "true").lower() != "false"

# Strict allowlists for SSRF prevention [M9]
SCAN_PORT_HOST_ALLOWLIST = {"127.0.0.1", "localhost", "host.docker.internal"}
SCAN_PORT_ALLOWLIST = {11434}  # Ollama default


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


def system_status():
    """Returns current ButterClaw system health metrics."""
    return json.dumps({
        "version": VERSION,
        "dry_run": DRY_RUN,
        "platform": platform.system(),
        "python": platform.python_version(),
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
        "description": "Returns current ButterClaw system health: version, platform, DRY_RUN state.",
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
    "rotate_keys":        rotate_keys,
    "system_status":      lambda **_: system_status(),
    "scan_port":          scan_port,
    "log_event":          log_event,
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

    def __init__(self):
        self.initialized = False
        self.tools = TOOL_DEFINITIONS
        self.dispatch = TOOL_DISPATCH

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
        "initialize":               "handle_initialize",
        "notifications/initialized": "handle_initialized_notification",
        "ping":                     "handle_ping",
        "tools/list":               "handle_tools_list",
        "tools/call":               "handle_tools_call",
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
# [v0.5.0] Refactored to use BaseTransport interface.
# The protocol handler (ButterClawMCPServer) takes a dict and returns
# a dict. The transport handles all I/O serialization.
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
                # No valid request exists — id must be None per JSON-RPC spec
                logger.error(f"❌ JSON parse error: {e}")
                err = {"jsonrpc": "2.0", "id": None,
                       "error": {"code": -32700, "message": f"Parse error: {e}"}}
                transport.write(err)

            except Exception as e:
                # [M1] Correlate error response to request id when available
                correlated_id = last_request.get("id") if last_request else None
                logger.error(f"❌ Unhandled exception (id={correlated_id}): {e}")
                err = {"jsonrpc": "2.0", "id": correlated_id,
                       "error": {"code": -32603, "message": f"Internal error: {e}"}}
                transport.write(err)
                last_request = {}  # Reset after error

    except KeyboardInterrupt:
        logger.info("📡 [MCP] Interrupted. Shutting down.")
    finally:
        transport.stop()
        logger.info(f"🦞 ButterClaw MCP v{VERSION} stopped.")


if __name__ == "__main__":
    main()
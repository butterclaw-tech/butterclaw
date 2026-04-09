"""
ButterClaw v0.4.0 — The Claws (MCP Execution Layer)
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

*** KINETIC OS ACTIONS REMAIN IN DRY RUN / SIMULATION MODE ***
"""

import logging
import time
import json
import sys
import os
import platform
import socket

# =====================================================================
# LOGGING — strictly stderr to protect the JSON-RPC stdout pipe
# =====================================================================

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger("butterclaw.mcp")

# =====================================================================
# CONFIGURATION
# =====================================================================

VERSION = "0.4.0"
PROTOCOL_VERSION = "2024-11-05"  # MCP spec version this server speaks
DRY_RUN = True                  # SAFETY HARNESS — kinetic actions are simulated


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
        "hostname": platform.node(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }, indent=2)


def scan_port(host="127.0.0.1", port=11434):
    """Quick TCP connect check — is a service alive at host:port?"""
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
        "description": "Returns current ButterClaw system health: version, platform, DRY_RUN state, PID.",
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

# Dispatch table — maps tool name → callable
TOOL_DISPATCH = {
    "execute_gibson_kill": execute_gibson_kill,
    "rotate_keys":        rotate_keys,
    "system_status":      lambda **_: system_status(),
    "scan_port":          scan_port,
    "log_event":          log_event,
}


# =====================================================================
# MCP SERVER — Protocol Handler
# =====================================================================

class ButterClawMCPServer:
    """
    MCP-compliant stdio JSON-RPC 2.0 server.
    Speaks the Model Context Protocol over stdin/stdout.
    """

    def __init__(self):
        self.initialized = False
        self.tools = TOOL_DEFINITIONS
        self.dispatch = TOOL_DISPATCH

    # ----- MCP Method Handlers -----

    def handle_initialize(self, params, req_id):
        """MCP initialize — returns protocol version, server info, capabilities."""
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
        """notifications/initialized — client acknowledges init. No response."""
        logger.info("📡 [MCP] Client acknowledged initialization.")
        return None

    def handle_ping(self, params, req_id):
        """MCP ping — keepalive check."""
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    def handle_tools_list(self, params, req_id):
        """tools/list — returns all registered tools with inputSchema."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": self.tools}
        }

    def handle_tools_call(self, params, req_id):
        """tools/call — executes a tool, returns MCP content array format."""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name not in self.dispatch:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
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
        """Routes a JSON-RPC request to the correct handler."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        handler_name = self.METHOD_MAP.get(method)

        if handler_name is None:
            if req_id is not None:
                # Unknown method with an id → error response
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            return None  # Unknown notification → ignore silently

        handler = getattr(self, handler_name)

        # Notifications (no id) → call handler, return nothing
        if req_id is None:
            handler(params)
            return None

        return handler(params, req_id)


# =====================================================================
# STDIO MAIN LOOP
# =====================================================================

def main():
    logger.info(f"🦞 ButterClaw MCP v{VERSION} starting (PID {os.getpid()})...")
    logger.info(f"   Protocol: {PROTOCOL_VERSION}")
    logger.info(f"   DRY_RUN:  {DRY_RUN}")
    logger.info(f"   Tools:    {len(TOOL_DEFINITIONS)}")

    server = ButterClawMCPServer()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                logger.info("📡 [MCP] stdin closed. Shutting down.")
                break

            line = line.strip()
            if not line:
                continue

            request = json.loads(line)
            response = server.route(request)

            # Only write a response for requests (not notifications)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parse error: {e}")
            err = {"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": f"Parse error: {e}"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()

        except Exception as e:
            logger.error(f"❌ Unhandled exception: {e}")
            err = {"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32603, "message": f"Internal error: {e}"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

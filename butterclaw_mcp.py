"""
ButterClaw v0.3.1 — The Claws (MCP Execution Layer)
=====================================================================
Changelog from v0.2:
[v0.3] Context Shift: Local keys are now destroyed by ButterVault.
       rotate_keys() now specifically simulates external provider API revocation.
[v0.3] Added True MCP Protocol server scaffolding (stdio/SSE preparation).

*** KINETIC OS ACTIONS REMAIN IN DRY RUN / SIMULATION MODE ***
"""

import logging
import time
import json
import sys

# Set up loud, clear logging, strictly routed to stderr to protect the JSON pipe
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger("butterclaw.mcp")

# SAFETY HARNESS IS ON FOR KINETIC OS ACTIONS
DRY_RUN = True


def rotate_keys(provider="OpenRouter"):
    """
    [v0.3 Update] Local keys are now physically shredded by the ButterVault.
    This function simulates reaching out to the provider's external API
    to invalidate the old token globally so the attacker can't use it.
    """
    logger.warning(f"🌐 EXT-ROTATE: Requesting external key revocation for {provider}...")
    time.sleep(0.5)  # Dramatic pause for the tech demo

    if DRY_RUN:
        logger.info(f"🛡️ [DRY RUN] Would have POSTed to {provider} API to roll tokens globally.")
        logger.info(f"🛡️ [DRY RUN] External tokens successfully 'Buttered'.")
        return True
    else:  # PATCHED B3 — was silent pass, now fails loud
        raise NotImplementedError(
            f"Production key rotation for {provider} is not yet implemented. "
            f"Set DRY_RUN = True or implement real .env key overwrite logic here."
        )


def execute_gibson_kill(target_process="openclaw"):
    """
    Simulates hunting down the rogue process and issuing a SIGKILL.
    """
    logger.warning(f"☢️ GIBSON KILL SWITCH: Hunting unautclated process '{target_process}'...")
    time.sleep(0.5)  # Dramatic pause

    if DRY_RUN:
        logger.info(f"🛡️ [DRY RUN] Found '{target_process}' running on PID 8842.")
        logger.info(f"🛡️ [DRY RUN] Would have executed: pkill -9 {target_process}")
        logger.info(f"🛡️ [DRY RUN] Process neutralized. The Sentinel rests.")
        return True
    else:  # PATCHED B3 — was silent pass, now fails loud
        raise NotImplementedError(
            f"Production process kill for '{target_process}' is not yet implemented. "
            f"Set DRY_RUN = True or implement real subprocess.run/taskkill logic here."
        )


# =====================================================================
# THE TRUE MCP PROTOCOL SCAFFOLD (v0.3)
# =====================================================================

class ButterClawMCPServer:
    """
    Scaffolding for the True MCP implementation.
    Will eventually listen on stdio or SSE to allow the Brain to dynamically
    discover these tools via JSON-RPC rather than hardcoded Python imports.
    """
    def __init__(self):
        self.tools = [
            {
                "name": "execute_gibson_kill",
                "description": "Kinetic Response: Terminates a rogue process by name using OS-level SIGKILL.",
                "parameters": {
                    "type": "object",
                    "properties": {"target_process": {"type": "string"}},
                    "required": ["target_process"]
                }
            },
            {
                "name": "rotate_keys",
                "description": "Kinetic Response: Invalidates provider API tokens globally.",
                "parameters": {
                    "type": "object",
                    "properties": {"provider": {"type": "string"}},
                    "required": ["provider"]
                }
            }
        ]

    def list_tools(self):
        """Returns the available tools formatted for an LLM system prompt."""
        return json.dumps(self.tools, indent=2)

    def execute_tool(self, tool_name, kwargs):
        """Routes the LLM's dynamic JSON request to the actual Python function."""
        if tool_name == "execute_gibson_kill":
            return execute_gibson_kill(**kwargs)
        elif tool_name == "rotate_keys":
            return rotate_keys(**kwargs)
        else:
            logger.error(f"❌ Unknown MCP tool invoked: {tool_name}")
            raise ValueError(f"Unknown tool: {tool_name}")


def main():
    server = ButterClawMCPServer()
    
    # The Claws are now a standalone background service
    while True:
        line = sys.stdin.readline()
        if not line:
            break
            
        try:
            # Parse the incoming JSON-RPC request
            request = json.loads(line)
            method = request.get("method")
            params = request.get("params", {})
            req_id = request.get("id")

            # Route to the appropriate tool
            if method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {}) # MCP standard uses 'arguments'
                result = server.execute_tool(tool_name, tool_args)
                
                response = {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": req_id
                }
            elif method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "result": {"capabilities": {"tools": server.tools}},
                    "id": req_id
                }
            else:
                response = {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": req_id}

        except Exception as e:
            response = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": None}

        # Send back to the Brain
        print(json.dumps(response))
        sys.stdout.flush()

if __name__ == "__main__":
    # Ensure sys is imported at the top of the file!
    import sys
    main()

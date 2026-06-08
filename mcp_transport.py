"""
ButterClaw v0.6.4 — MCP Transport Abstraction Layer
=====================================================================
Provides transport-agnostic I/O for the MCP server. The protocol
handler (ButterClawMCPServer) doesn't care how bytes arrive — it
takes a dict and returns a dict. This module handles the plumbing.

Two transports:
  - StdioTransport: stdin/stdout (default, local child process)
  - SSETransport:   HTTP POST + Server-Sent Events (network-accessible)

Usage:
  from mcp_transport import StdioTransport, SSETransport

  transport = StdioTransport()       # or SSETransport(port=5001)
  transport.start()
  while True:
      request = transport.read()     # blocks until a request arrives
      if request is None: break      # transport closed
      response = server.route(request)
      if response is not None:
          transport.write(response)
  transport.stop()
"""

import sys
import json
import queue
import logging
import threading
from abc import ABC, abstractmethod
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from config import cfg

logger = logging.getLogger("butterclaw.transport")

_CORS_ORIGIN = getattr(cfg, "BASE_URL", "http://127.0.0.1:5000")

# =====================================================================
# BASE TRANSPORT — Abstract interface
# =====================================================================

class BaseTransport(ABC):
    """
    Transport contract for the MCP server.
    All transports must implement read/write/start/stop.
    """

    @abstractmethod
    def start(self):
        """Initialize the transport (open connections, start servers)."""
        pass

    @abstractmethod
    def stop(self):
        """Shut down the transport cleanly."""
        pass

    @abstractmethod
    def read(self):
        """
        Block until a JSON-RPC request dict is available.
        Returns None when the transport is closed.
        """
        pass

    @abstractmethod
    def write(self, response):
        """Send a JSON-RPC response dict to the client."""
        pass

    @property
    @abstractmethod
    def transport_name(self):
        """Human-readable transport identifier."""
        pass


# =====================================================================
# STDIO TRANSPORT — stdin/stdout (default, local)
# =====================================================================

class StdioTransport(BaseTransport):
    """
    Reads JSON-RPC requests from stdin (one per line).
    Writes JSON-RPC responses to stdout (one per line).
    This is the default transport for local child process mode.
    """

    def __init__(self):
        self._running = False

    @property
    def transport_name(self):
        return "stdio"

    def start(self):
        self._running = True
        logger.info("📡 [Transport] stdio transport started.")

    def stop(self):
        self._running = False
        logger.info("📡 [Transport] stdio transport stopped.")

    def read(self):
        while True:
            if not self._running:
                return None
            try:
                line = sys.stdin.readline()
                if not line:
                    return None  # stdin closed
                line = line.strip()
                if line:
                    return json.loads(line)
            except json.JSONDecodeError as e:
                # Return a parse error response directly — caller handles it
                logger.error(f"❌ [Transport] JSON parse error on stdin: {e}")
                raise
            except Exception:
                return None

    def write(self, response):
        try:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            logger.error("❌ [Transport] stdout pipe broken.")
            self._running = False


# =====================================================================
# SSE TRANSPORT — HTTP POST + Server-Sent Events (network)
# =====================================================================

class SSETransport(BaseTransport):
    """
    MCP-compatible SSE transport using stdlib http.server.
    No additional pip dependencies required.

    Endpoints:
      GET  /sse      → Opens an SSE stream. Server pushes JSON-RPC
                       responses through this channel.
      POST /message  → Client sends JSON-RPC requests here.
      GET  /health   → Simple health check for the transport.

    The main loop calls read() to dequeue incoming requests and
    write() to push responses to all connected SSE clients.

    Security:
      - Binds to 127.0.0.1 by default (local only).
      - Optional bearer token via --token flag.
      - Remote binding (0.0.0.0) requires explicit --bind flag.
    """

    def __init__(self, host="127.0.0.1", port=5001, token=None):
        self.host = host
        self.port = port
        self.token = token
        self._request_queue = queue.Queue()
        self._sse_clients = []       # list of response queues for SSE clients
        self._sse_lock = threading.Lock()
        self._server = None
        self._server_thread = None
        self._running = False
        self._endpoint_url = None    # sent to client in initial SSE message

    @property
    def transport_name(self):
        return f"sse ({self.host}:{self.port})"

    def start(self):
        self._running = True
        self._endpoint_url = f"http://{self.host}:{self.port}/message"

        # Build the handler with a reference back to this transport
        transport_ref = self

        class MCPSSEHandler(BaseHTTPRequestHandler):
            """Handles GET /sse, POST /message, GET /health."""

            def log_message(self, format, *args):
                # Suppress default stderr logging — we use our own logger
                pass

            def _check_auth(self):
                if transport_ref.token is None:
                    return True
                auth = self.headers.get("Authorization", "")
                expected = f"Bearer {transport_ref.token}"
                if auth != expected:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
                    return False
                return True

            def do_GET(self):
                # 1. Auth check (if token is configured)
                if transport_ref.token:
                    if not self._check_auth():
                        return  # 401 already sent by _check_auth()

                path = urlparse(self.path).path

                if path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "status": "ok",
                        "transport": "sse"
                    }).encode())
                    return

                if path == "/sse":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
                    self.end_headers()

                    # Send the endpoint URL as the first SSE event
                    # MCP spec: first event tells client where to POST
                    endpoint_msg = f"event: endpoint\ndata: {transport_ref._endpoint_url}\n\n"
                    try:
                        self.wfile.write(endpoint_msg.encode())
                        self.wfile.flush()
                    except Exception:
                        return

                    # Register this client's response queue
                    client_queue = queue.Queue()
                    with transport_ref._sse_lock:
                        transport_ref._sse_clients.append(client_queue)

                    logger.info("📡 [SSE] Client connected.")

                    try:
                        while transport_ref._running:
                            try:
                                response = client_queue.get(timeout=30)
                                if response is None:
                                    break  # poison pill
                                sse_data = f"event: message\ndata: {json.dumps(response)}\n\n"
                                self.wfile.write(sse_data.encode())
                                self.wfile.flush()
                            except queue.Empty:
                                # Send keepalive comment
                                try:
                                    self.wfile.write(b": keepalive\n\n")
                                    self.wfile.flush()
                                except Exception:
                                    break
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        with transport_ref._sse_lock:
                            if client_queue in transport_ref._sse_clients:
                                transport_ref._sse_clients.remove(client_queue)
                        logger.info("📡 [SSE] Client disconnected.")
                    return

                # Unknown path
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not found"}).encode())

            def do_POST(self):
                path = urlparse(self.path).path

                if path != "/message":
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Not found"}).encode())
                    return

                if not self._check_auth():
                    return

                content_length = int(self.headers.get("Content-Length", 0))
                if content_length == 0:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Empty body"}).encode())
                    return

                body = self.rfile.read(content_length)

                try:
                    request = json.loads(body)
                except json.JSONDecodeError as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "error": f"Invalid JSON: {e}"
                    }).encode())
                    return

                # Queue the request for the main loop
                transport_ref._request_queue.put(request)

                # Respond with 202 Accepted — response comes via SSE
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"accepted": True}).encode())

            def do_OPTIONS(self):
                """Handle CORS preflight."""
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.end_headers()

        # Create and start the threaded HTTP server
        class ThreadedHTTPServer(HTTPServer):
            """HTTPServer with threading for concurrent SSE clients."""
            allow_reuse_address = True
            daemon_threads = True

            def process_request(self, request, client_address):
                t = threading.Thread(target=self.process_request_thread,
                                     args=(request, client_address), daemon=True)
                t.start()

            def process_request_thread(self, request, client_address):
                try:
                    self.finish_request(request, client_address)
                except Exception:
                    self.handle_error(request, client_address)
                finally:
                    self.shutdown_request(request)

        self._server = ThreadedHTTPServer((self.host, self.port), MCPSSEHandler)
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="mcp-sse-server",
            daemon=True
        )
        self._server_thread.start()

        auth_note = " (token required)" if self.token else " (no auth)"
        logger.info(f"📡 [Transport] SSE transport started on {self.host}:{self.port}{auth_note}")
        logger.info(f"   GET  http://{self.host}:{self.port}/sse      → SSE stream")
        logger.info(f"   POST http://{self.host}:{self.port}/message  → JSON-RPC requests")

    def stop(self):
        self._running = False

        # Poison-pill all SSE clients
        with self._sse_lock:
            for client_q in self._sse_clients:
                client_q.put(None)
            self._sse_clients.clear()

        # Unblock read() if waiting
        self._request_queue.put(None)

        if self._server:
            self._server.shutdown()
            logger.info("📡 [Transport] SSE transport stopped.")

    def read(self):
        while self._running:
            try:
                request = self._request_queue.get(timeout=1)
                return request  # None is the poison pill
            except queue.Empty:
                continue
        return None

    def write(self, response):
        """Push a response to all connected SSE clients."""
        with self._sse_lock:
            dead_clients = []
            for client_q in self._sse_clients:
                try:
                    client_q.put(response, timeout=5)
                except queue.Full:
                    dead_clients.append(client_q)
            for dead in dead_clients:
                self._sse_clients.remove(dead)


# =====================================================================
# FACTORY — Create transport from CLI args or config
# =====================================================================

def create_transport(transport_type="stdio", host="127.0.0.1", port=5001, token=None):
    """
    Factory function to create a transport from configuration.

    Args:
        transport_type: "stdio" or "sse"
        host: Bind address for SSE transport (default: 127.0.0.1)
        port: Port for SSE transport (default: 5001)
        token: Bearer token for SSE auth (optional)

    Returns:
        BaseTransport instance
    """
    if transport_type == "stdio":
        return StdioTransport()
    elif transport_type == "sse":
        return SSETransport(host=host, port=port, token=token)
    else:
        raise ValueError(f"Unknown transport type: {transport_type}. Use 'stdio' or 'sse'.")
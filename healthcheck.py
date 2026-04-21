#!/usr/bin/env python3
"""
ButterClaw v0.6.3 — Docker Health Check
Hits /api/health and exits 0 (healthy) or 1 (unhealthy).
Used by Docker HEALTHCHECK directive.
"""
import sys
import os
from urllib.request import urlopen
from urllib.error import URLError

port = os.environ.get('BUTTERCLAW_PORT', '5000')
url = f"http://localhost:{port}/api/health"

try:
    resp = urlopen(url, timeout=5)
    if resp.status == 200:
        sys.exit(0)
    sys.exit(1)
except (URLError, Exception):
    sys.exit(1)

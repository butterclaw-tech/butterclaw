#!/usr/bin/env python3
"""
ButterClaw v0.8.1 — Test Spatial API Integration
"""

import requests
import time
import json
import os
import sys
from butterclaw.config import cfg, PROJECT_ROOT

def get_auth_key():
    """Environment scraper to extract the API key via the package config."""
    # 1. Check environment (config.py automatically loads the .env into os.environ)
    api_key = os.environ.get("BUTTERCLAW_API_KEY")
    if api_key:
        return api_key

    # 2. Bulletproof fallback using the canonical root anchor
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, 'r', encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith('BUTTERCLAW_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return None

API_KEY = get_auth_key()

if not API_KEY:
    print("❌ Error: BUTTERCLAW_API_KEY not found in environment or .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# The v0.8.0 Gateway Endpoint
URL = "http://localhost/api/spatial/telemetry"

def fire_payload(name, payload):
    print(f"\n🔫 Firing {name}...")
    start_time = time.time()
    
    try:
        response = requests.post(URL, headers=HEADERS, json=payload)
        elapsed = (time.time() - start_time) * 1000
        print(f"⏱️  Latency: {elapsed:.2f}ms")
        print(f"📥 Response [{response.status_code}]: {json.dumps(response.json(), indent=2)}")
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed! Is the Docker container running?")

if __name__ == "__main__":
    session = "ses_test_trigger_001"
    
    # 1. The Benign Action (Should return 200 OK)
    benign_payload = {
        "session_id": session,
        "action_type": "mouse_click",
        "payload": {"x": 500, "y": 500, "button": "left"},
        "screenshot_ref": "/dev/shm/butterclaw_hot_frames/frame_001.webp"
    }
    
    fire_payload("Benign Mouse Click", benign_payload)
    
    time.sleep(1) # Brief pause to mimic human delay
    
    # 2. The Malicious Attractor (Should return 403 Forbidden + trigger Watcher)
    malicious_payload = {
        "session_id": session,
        "action_type": "keyboard_type",
        "payload": {"text": "powershell.exe -ExecutionPolicy Bypass -w hidden"},
        "screenshot_ref": "/dev/shm/butterclaw_hot_frames/frame_002.webp"
    }
    
    fire_payload("Restricted Subsystem Invocation (Powershell)", malicious_payload)
#!/usr/bin/env python3
"""
ButterClaw v0.8.0 — Test Spatial API Integration
"""

import requests
import time
import json
import os

def get_auth_key():
    """Zero-dependency environment scraper to extract the API key."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    try:
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('BUTTERCLAW_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None

API_KEY = get_auth_key()

if not API_KEY:
    print("❌ Error: BUTTERCLAW_API_KEY not found in .env")
    exit(1)

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
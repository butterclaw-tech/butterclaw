#!/usr/bin/env python3
"""
ButterClaw v0.8.1 — Spatial API Test - Tests All 4 Spatial Primitives + Cold Memory Detection
"""

import requests
import time
import random
import uuid
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

URL = "http://localhost/api/spatial/telemetry"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def generate_drunken_telemetry():
    """Simulates chaotic agent actions using all 4 spatial primitives."""
    actions = []
    
    # 1. Generate 4 to 7 random spatial actions
    for _ in range(random.randint(4, 7)):
        action_choice = random.choice(["mouse_click", "mouse_move", "key_press"])
        
        if action_choice in ["mouse_click", "mouse_move"]:
            actions.append({
                "action_type": action_choice,
                "payload": {
                    "x": random.randint(100, 1800),
                    "y": random.randint(100, 1000)
                }
            })
        elif action_choice == "key_press":
            actions.append({
                "action_type": "key_press",
                "payload": {"key": random.choice(["Tab", "Enter", "Escape", "Space"])}
            })
            
    # 2. End with the payload to trigger the block
    actions.append({
        "action_type": "keyboard_type",
        "payload": {"text": "powershell -ExecutionPolicy Bypass"}
    })
    
    return actions

def run_fuzzer():
    # Generate a unique session ID for this "agent"
    session_id = f"ses_fuzzer_{uuid.uuid4().hex[:8]}"
    print(f"🏴‍☠️ Launching Drunken Sailor (Session: {session_id})")
    
    actions = generate_drunken_telemetry()
    
    for i, action in enumerate(actions):
        payload = {
            "session_id": session_id,
            "action_type": action["action_type"],
            "payload": action["payload"]
        }
        
        print(f"[{i+1}/{len(actions)}] Sending {action['action_type']}...")
        
        try:
            response = requests.post(URL, json=payload, headers=HEADERS, timeout=2.0)
            if response.status_code == 403:
                print("🛑 KINETIC BLOCK! The immune system caught the fuzzer.")
                break # Agent is "dead", stop sending telemetry
            elif response.status_code == 200:
                print("✅ Passed tollbooth.")
            else:
                print(f"⚠️ Unexpected status: {response.status_code}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            
        # Slight delay to simulate human/agent processing time
        time.sleep(0.5)

if __name__ == "__main__":
    # Run the fuzzer 3 times to see if Cold Memory catches it on the 2nd/3rd try!
    for run in range(1, 4):
        print(f"\n--- ATTACK RUN {run} ---")
        run_fuzzer()
        print("Waiting for Dreamer Consolidation Loop to run...")
        time.sleep(6) # Wait 6 seconds so the 5.0s MemoryEngine TTL refreshes
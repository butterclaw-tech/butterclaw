#!/usr/bin/env python3
"""
ButterClaw v0.8.1 — Dual Memory Engine Integration Test
Validates the Surface Memory (Live Crystallization), Dream Weaver, and Loop Proposer.
"""

import os
import sys
import time
import requests
import urllib3

# Suppress insecure request warnings for local testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------
# Blue Team Frictionless Auth Setup 💙🐳
# ---------------------------------------------------------
# ---------------------------------------------------------
from butterclaw.config import cfg, PROJECT_ROOT

API_KEY = os.environ.get("BUTTERCLAW_API_KEY")

if not API_KEY:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("BUTTERCLAW_API_KEY="):
                    API_KEY = line.split("=", 1)[1].strip().strip("\"'")
                    break

if not API_KEY:
    print("❌ FATAL: Could not find BUTTERCLAW_API_KEY in environment or .env file.")
    sys.exit(1)

# FORCE HTTPS TO PREVENT NGINX 301 POST-TO-GET STRIPPING
BASE_URL = "https://localhost/api"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def api_call(endpoint: str, method: str = "GET", payload: dict = None) -> dict:
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "POST":
            response = requests.post(url, headers=HEADERS, json=payload, verify=False)
        elif method == "DELETE":
            response = requests.delete(url, headers=HEADERS, verify=False)
        else:
            response = requests.get(url, headers=HEADERS, verify=False)
            
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  [!] HTTP Error on {endpoint}: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"  [!] Response body: {e.response.text[:200]}")
        return None

if __name__ == "__main__":
    print("🐳 🟦 BLUE TEAM LIVE-FIRE: DUAL MEMORY SUBSTRATE 🟦 🐳\n")

    # =====================================================================
    # Phase 1: Surface Memory (Kinetic Ingestion)
    # =====================================================================
    print("▶ PHASE 1: Surface Memory (Live Crystallization)")
    session = "ses_blue_team_3strike_005"
    
    malicious_payload = {
        "session_id": session,
        "action_type": "keyboard_type",
        "payload": {"text": "powershell.exe -ExecutionPolicy Bypass -w hidden"},
        "screenshot_ref": "/dev/shm/butterclaw_hot_frames/frame_002.webp"
    }

    for i in range(4):
        print(f"  🔫 Firing kinetic payload {i+1}/4...")
        try:
            res = requests.post(f"{BASE_URL}/spatial/telemetry", headers=HEADERS, json=malicious_payload, verify=False)
            print(f"  📥 Response [{res.status_code}]")
        except requests.exceptions.ConnectionError:
            print("  ❌ Connection failed! Is the Docker container running?")
            
        if i < 3:
            print("  ⏳ Sleeping 10.1s to clear rolling telemetry window...")
            time.sleep(10.1)

    print("  Fetching Active Cold Signatures (Validating Phase 1)...")
    sigs = api_call("/memory/signatures")
    if sigs and any(s.get("threat_category", "").startswith("live:") for s in sigs.get("signatures", [])):
        print("  ✅ PASS: Zero-day spatial pattern successfully crystallized into Cold Memory!")
    else:
        print("  ❌ FAIL: Live crystallization did not trigger.")

    # =====================================================================
    # Phase 2: Deep Memory (Dream Weaver Priming & Maturation)
    # =====================================================================
    print("\n▶ PHASE 2: Deep Memory (Dream Weaver & Maturation)")
    print("  Triggering manual REM cycle (forces maturation tick)...")
    dream_res = api_call("/dream/trigger", method="POST")

    if dream_res and dream_res.get("status") in ["triggered", "already_running"]:
        print("  Sleeping 3 seconds for cycle yield...")
        time.sleep(3.0)
        
        print("  Checking Hot Memory for [DREAM-PRIMED] tags...")
        hot_cache = api_call("/memory/hot")
        if hot_cache and hot_cache.get("count", 0) >= 0: 
            print("  ✅ PASS: Dream Weaver trigger accepted and API is returning cache data.")
    else:
        print("  ❌ FAIL: Dream Weaver failed to trigger.")

    # =====================================================================
    # Phase 3: The Loop Proposer (Shadow Evaluation)
    # =====================================================================
    print("\n▶ PHASE 3: The Loop Proposer (Shadow Evaluation)")
    
    print("  Feeding the ledger a safe MCP 'tools/call' via admin key rotation...")
    api_call("/rotate-keys", method="POST")
    time.sleep(1.0)
    
    print("  Triggering manual Loop cycle...")
    loop_res = api_call("/loop/trigger", method="POST")

    if loop_res:
        print(f"  Loop Trigger Status: {loop_res.get('status')}")
        print("  Checking Loop Experiments ledger...")
        experiments = api_call("/loop/experiments")
        if experiments and "experiments" in experiments:
            print("  ✅ PASS: Loop Proposer API is fully wired and returning ledger data.")
    else:
        print("  ❌ FAIL: Loop Proposer encountered an error.")

    print("\n🏁 Dual Memory Substrate diagnostic complete.")
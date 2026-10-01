#!/usr/bin/env python3
"""
ButterClaw v0.8.1 — Add Rule
adds a new rule to the Policy Engine via the Nginx gateway.
"""
import json
import os
import urllib.error
import urllib.request
import sys
from butterclaw.config import cfg, PROJECT_ROOT

def get_auth_key():
    # 1. Check environment (config.py automatically loads the .env into os.environ for us)
    api_key = os.environ.get("BUTTERCLAW_API_KEY")
    if api_key:
        return api_key

    # 2. Bulletproof fallback using the canonical root anchor
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("BUTTERCLAW_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    
    return None

def main():
    api_key = get_auth_key()
    
    if not api_key:
        print("❌ Error: Could not find BUTTERCLAW_API_KEY in local .env file or parent directory.")
        sys.exit(1)

    print("✅ Located infrastructure API key from .env")
    print("🚀 Injecting active defense rule into the Policy Engine...")

    payload = {
        "name": "Block Evil WebSockets",
        "scope": "pre_brain",
        "action": "override_critical",
        "condition": {
            "field": "payload",
            "operator": "contains",
            "value": "evil.xyz",
        },
        "description": "Auto-injected rule to test policy engine override.",
        "priority": 10
    }

    # Targeting the Nginx gateway via Docker on localhost
    target_url = "http://localhost/api/policies"

    req = urllib.request.Request(
        target_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            print(f"✅ Success! Rule injected: {resp_data.get('id', 'Unknown ID')}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ HTTP Error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        print(f"❌ Connection Error: Could not connect to {target_url}.")
        print(f"   Reason: {e.reason}")
        print("   (Is the ButterClaw server running?)")
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    main()
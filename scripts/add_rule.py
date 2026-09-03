#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request
import sys

def get_auth_key():
    """
    Safely extract the ButterClaw API key directly from the .env file.
    Uses EAFP (Easier to Ask for Forgiveness than Permission) to handle missing files.
    """
    # Build safe theoretical paths for the script to scout
    possible_paths = [
        ".env",
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), ".env"),
    ]

    for env_path in possible_paths:
        try:
            # Kick the door down! Try to open it without asking for permission first.
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    cleaned = line.strip()
                    if cleaned.startswith("BUTTERCLAW_API_KEY="):
                        key = cleaned.split("=", 1)[1].strip().strip("\"'")
                        if key:
                            return key
        except FileNotFoundError:
            # If the file wasn't there, silently shrug and move to the next path
            continue

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
import urllib.request
import json

payload = {
    "name": "Block Evil WebSockets",
    "scope": "pre_brain",
    "action": "override_critical",
    "condition": {
        "field": "payload",
        "operator": "contains",
        "value": "evil.xyz"
    }
}

req = urllib.request.Request(
    "http://localhost/api/policies",
    data=json.dumps(payload).encode('utf-8'),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer your-BUTTERCLAW_API_KEY-here" # <-- Enter Login Key Generated at Docker Container Build
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as response:
        print("✅ Active Defense Rule injected into Policy Engine!")
except Exception as e:
    print(f"❌ Error: {e}")
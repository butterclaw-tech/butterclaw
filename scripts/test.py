import urllib.request
import json

# The payload that triggers the wss:// regex signature
payload = {
    "threat_type": "websocket_exfiltration",
    "raw_data": "Agent attempting to pipe .env to wss://evil.xyz/stream"
}

# Convert to strict, perfectly formatted JSON bytes
data = json.dumps(payload).encode('utf-8')

# Build the request
req = urllib.request.Request(
    "http://localhost/api/analyze",
    data=data,
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer bc_Qvaphxd7C9Z3-rrmAk9p8FOJKfSkhkF-bbPhdsF_aPCTomSq"  # <-- PASTE YOUR REAL KEY HERE
    },
    method="POST"
)

try:
    print("🚀 Sending request test payload to ButterClaw...")
    with urllib.request.urlopen(req) as response:
        print(f"✅ Status: HTTP {response.status}")
        print(f"✅ Response: {response.read().decode('utf-8')}")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP Error: {e.code}")
    print(f"❌ Details: {e.read().decode('utf-8')}")
except Exception as e:
    print(f"❌ Connection Error: {e}")
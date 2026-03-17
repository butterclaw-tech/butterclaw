import re
import time
import requests
import os

# Configuration
LOG_FILE = "openclaw_gateway.log"
VPS_ENDPOINT = "http://127.0.0.1:5000/api/analyze"

print(f"👀 Watcher online. Staring intensely at {LOG_FILE}...")

# 1. Create the empty log file if it doesn't exist yet
if not os.path.exists(LOG_FILE):
    open(LOG_FILE, 'w').close()

# 2. Open the file and jump to the very end
try:
    with open(LOG_FILE, 'r') as file:
        file.seek(0, 2) # Go to the last byte of the file

        # 3. The Infinite Stare
        while True:
            line = file.readline()
            
            if not line:
                time.sleep(0.5)
                continue
                
            clean_log = line.strip()
            
            if not clean_log:
                continue
                
            # --- THE MAIL SLOT BOUNCER 🚪 ---
            # 1. Truncate the payload to 500 characters (Stops RAM exhaustion)
            truncated = str(clean_log)[:500] 
            # 2. Scrub out all dangerous shell characters ($, {, }, <, >, |)
            safe_line = re.sub(r'[^a-zA-Z0-9\s\.\-\"\/:\_]', '', truncated)
            # ---------------------------------
                
            print(f"\n🚨 [NEW LOG DETECTED] {safe_line}")
            print("📡 Forwarding to ButterClaw Brain...")
            
            payload = {
                "threat_type": "Live Gateway Log",
                "raw_data": safe_line  # <-- We now send the sanitized line!
            }
            
            try:
                requests.post(VPS_ENDPOINT, json=payload, timeout=60)
            except Exception:
                print("❌ Brain offline. Log dropped.")

# --- THE SHIELD ---
except KeyboardInterrupt:
    print("\n🛑 [SHUTDOWN] Watcher received SIGINT. Autclator going dark.")
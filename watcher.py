"""
ButterClaw v0.6.3.1 — Log Watcher
=================================================
[v0.6.3.1] - Full Docker Updated
| `watcher.py` | ~5 | ~5 | Auth compliance (Bearer tokens), boot warning logic fix. |
- monitors bridged 'openclaw_gateway.log' in base directory

ButterClaw v0.3.1 — Log Watcher (Expanded Context)

Changelog from v0.1.1:
  [v0.3] CONTEXT EXPANSION: Increased log truncation from 500 to 4096 chars.
         (Crucial for passing massive Indirect Prompt Injections to the Brain).
  [v0.3] Vibe sync and terminal formatting to match the v0.3 ecosystem.
  [C1] Log rotation detection — reopens file on truncation or inode change
  [C2] Sanitizer preserves log structure — targeted blacklist instead of aggressive whitelist
  [C3] In-memory retry queue for failed POSTs (deque, maxlen=100)
"""

import re
import time
import requests
import os
import sys
import logging
import argparse
import atexit
from collections import deque

# =============================================
# [M2] STRUCTURED LOGGING
# =============================================

logger = logging.getLogger("butterclaw.watcher")  # PATCHED I6: basicConfig moved to main() — prevents collision when imported as module

# =============================================
# CONFIGURATION
# =============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "openclaw_gateway.log")
VPS_ENDPOINT = "http://127.0.0.1:5000/api/analyze"
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")

# [v0.6.0] API Auth Key
API_KEY = os.environ.get("BUTTERCLAW_API_KEY")

# [C3] Retry queue for failed POSTs
RETRY_QUEUE_MAX = 100
retry_queue = deque(maxlen=RETRY_QUEUE_MAX)

# [M3] POST Timeout
POST_TIMEOUT = 120

# =============================================
# [M4] PID / LOCK FILE
# =============================================

def check_pid_file():
    """Prevents duplicate watcher instances."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            logger.error("❌ Another watcher is already running (PID %d). Exiting.", old_pid)
            sys.exit(1)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            logger.warning("🧹 Stale PID file found. Cleaning up.")
            os.remove(PID_FILE)

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def cleanup_pid_file():
    """Remove PID file on exit."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except OSError:
        pass

# =============================================
# [v0.3] SANITIZER — TARGETED BLACKLIST
# =============================================

def sanitize_log_line(raw_line):
    """
    Strips shell-dangerous characters while preserving log structure.
    v0.3 Update: Truncation expanded from 500 -> 4096 to capture full prompt injections.
    """
    truncated = str(raw_line)[:4096]
    # Remove only chars that enable shell injection / command execution
    safe_line = re.sub(r'[$`{}<>|;!]', '', truncated)
    return safe_line

# =============================================
# [C3] RETRY QUEUE (v0.6.0 patch)
# =============================================

def send_to_server(payload):
    """POST a payload to the ButterClaw server with Auth Headers."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    try:
        resp = requests.post(VPS_ENDPOINT, json=payload, headers=headers, timeout=POST_TIMEOUT)
        
        if resp.status_code == 401:
            logger.error("🚫 HTTP 401 Unauthorized: API Badge rejected! Check your BUTTERCLAW_API_KEY.")
            return False
            
        if resp.status_code == 429:
            logger.warning("⚠️ Rate limited by server. Queuing for retry.")
            return False
            
        return True
    except requests.RequestException as e:
        logger.warning("⚠️ Brain offline. Queuing log for retry.")
        return False

def flush_retry_queue():
    """Attempt to re-send queued payloads before processing new lines."""
    retried = 0
    while retry_queue:
        payload = retry_queue[0]
        if send_to_server(payload):
            retry_queue.popleft()
            retried += 1
        else:
            break
    if retried > 0:
        logger.info("✅ Flushed %d queued log(s) to server.", retried)

# =============================================
# [C1] LOG ROTATION DETECTION
# =============================================

def get_file_identity(filepath):
    """Returns (inode, size) for rotation detection."""
    try:
        stat = os.stat(filepath)
        return stat.st_ino, stat.st_size
    except OSError:
        return None, None

def watch_log(replay=False):
    """Main watch loop with rotation detection."""
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, 'w').close()
        logger.info("📄 Created empty log file: %s", LOG_FILE)

    file = open(LOG_FILE, 'r')

    if replay:
        logger.info("⏪ REPLAY MODE: Processing entire log file from start.")
        file.seek(0)
    else:
        file.seek(0, 2)  # Jump to EOF — tail mode

    current_inode, _ = get_file_identity(LOG_FILE)

    while True:
        if retry_queue:
            flush_retry_queue()

        line = file.readline()

        if not line:
            time.sleep(0.5)

            current_pos = file.tell()
            _, current_size = get_file_identity(LOG_FILE)
            if current_size is not None and current_pos > current_size:
                logger.warning("🔄 Log file truncated. Reopening from start.")
                file.close()
                file = open(LOG_FILE, 'r')
                file.seek(0)
                current_inode, _ = get_file_identity(LOG_FILE)
                continue

            new_inode, _ = get_file_identity(LOG_FILE)
            if new_inode is not None and new_inode != current_inode:
                logger.warning("🔄 Log file replaced (new inode). Reopening.")
                file.close()
                file = open(LOG_FILE, 'r')
                file.seek(0)
                current_inode = new_inode
                continue
            continue

        clean_log = line.strip()
        if not clean_log:
            continue

        safe_line = sanitize_log_line(clean_log)

        logger.info("📡 New log detected: %.80s%s", safe_line, "..." if len(safe_line) > 80 else "")

        payload = {
            "threat_type": "Live Gateway Log",
            "raw_data": safe_line
        }

        if not send_to_server(payload):
            retry_queue.append(payload)

# =============================================
# BOOT
# =============================================

def main():
    # PATCHED I6: basicConfig here — only runs when watcher is the entry point, not on import
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.INFO
    )
    parser = argparse.ArgumentParser(description="ButterClaw Log Watcher v0.3.1")  # PATCHED I3
    parser.add_argument("--replay", action="store_true", help="Process entire log file from start")
    args = parser.parse_args()

    check_pid_file()
    atexit.register(cleanup_pid_file)

    logger.info("🦞 ButterClaw Watcher v0.6.3.1 online. 👁️ Staring intensely at %s...", LOG_FILE)
    
    if not API_KEY:
        logger.warning("⚠️ BUTTERCLAW_API_KEY environment variable not found. Server will likely reject payloads (401).")

    if retry_queue:
        logger.info("Retry queue initialized (max %d entries).", RETRY_QUEUE_MAX)

    try:
        watch_log(replay=args.replay)
    except KeyboardInterrupt:
        logger.info("🛑 SHUTDOWN: Watcher received SIGINT. Automator going dark.")
        if retry_queue:
            logger.warning("%d unsent log(s) in retry queue — will be lost.", len(retry_queue))

if __name__ == "__main__":
    main()

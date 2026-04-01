"""
ButterClaw v0.1.1 — Log Watcher (Patched)
==========================================
Changelog from v0.1:
  [C1] Log rotation detection — reopens file on truncation or inode change
  [C2] Sanitizer preserves log structure — targeted blacklist instead of
       aggressive whitelist that destroyed timestamps and query strings
  [C3] In-memory retry queue for failed POSTs (deque, maxlen=100)
  [M1] Fixed shutdown typo → "Automator"
  [M2] Structured logging via logging module (timestamps + levels)
  [M3] POST timeout reduced 60s → 10s to prevent pipeline stall
  [M4] PID/lock file prevents duplicate watcher instances
  [L1] --replay flag for cold-start log recovery
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

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger("butterclaw.watcher")

# =============================================
# CONFIGURATION
# =============================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "openclaw_gateway.log")
VPS_ENDPOINT = "http://127.0.0.1:5000/api/analyze"
PID_FILE = os.path.join(BASE_DIR, "watcher.pid")

# [C3] Retry queue for failed POSTs
RETRY_QUEUE_MAX = 100
retry_queue = deque(maxlen=RETRY_QUEUE_MAX)

# [M3] Reduced timeout — cold loads handled by retry queue - changed from 10 to 120
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
            # Check if that process is still alive
            os.kill(old_pid, 0)
            # If we get here, process is alive
            logger.error(
                "Another watcher is already running (PID %d). Exiting.", old_pid
            )
            sys.exit(1)
        except (ValueError, ProcessLookupError, PermissionError):
            # PID file is stale — process is gone
            logger.warning("Stale PID file found. Cleaning up.")
            os.remove(PID_FILE)
        except OSError:
            # os.kill can raise OSError on some platforms for dead PIDs
            logger.warning("Stale PID file found. Cleaning up.")
            os.remove(PID_FILE)

    # Write our PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logger.info("PID file written: %s (PID %d)", PID_FILE, os.getpid())


def cleanup_pid_file():
    """Remove PID file on exit."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("PID file cleaned up.")
    except OSError:
        pass


# =============================================
# [C2] SANITIZER — TARGETED BLACKLIST
# =============================================

def sanitize_log_line(raw_line):
    """
    Strips shell-dangerous characters while preserving log structure.

    Old regex destroyed [], (), =, ?, &, #, @ — all critical for reading
    HTTP logs, timestamps, and query strings.

    New approach: remove only chars that enable shell injection / command
    execution: $ ` { } < > | ; !
    """
    truncated = str(raw_line)[:500]
    safe_line = re.sub(r'[$`{}<>|;!]', '', truncated)
    return safe_line


# =============================================
# [C3] RETRY QUEUE
# =============================================

def send_to_server(payload):
    """
    POST a payload to the ButterClaw server.
    Returns True on success, False on failure (payload queued for retry).
    """
    try:
        # [M3] 10s timeout instead of 60s
        resp = requests.post(VPS_ENDPOINT, json=payload, timeout=POST_TIMEOUT)
        if resp.status_code == 429:
            logger.warning("Rate limited by server. Queuing for retry.")
            return False
        return True
    except requests.RequestException as e:
        logger.warning("Brain offline (%s). Queuing log for retry.", e)
        return False


def flush_retry_queue():
    """
    Attempt to re-send queued payloads before processing new lines.
    Stops on first failure to avoid hammering a down server.
    """
    retried = 0
    while retry_queue:
        payload = retry_queue[0]  # Peek
        if send_to_server(payload):
            retry_queue.popleft()  # Success — remove from queue
            retried += 1
        else:
            break  # Server still down — stop flushing
    if retried > 0:
        logger.info("Flushed %d queued log(s) to server.", retried)


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
    """
    Main watch loop with rotation detection.

    [C1] After each empty readline, checks:
      - File truncated (position > current size) → reopen from 0
      - File replaced (inode changed) → reopen from 0
    [L1] --replay mode starts from position 0 instead of EOF
    """
    # Create the log file if it doesn't exist
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, 'w').close()
        logger.info("Created empty log file: %s", LOG_FILE)

    file = open(LOG_FILE, 'r')

    if replay:
        logger.info("REPLAY MODE: Processing entire log file from start.")
        file.seek(0)
    else:
        file.seek(0, 2)  # Jump to EOF — tail mode

    current_inode, _ = get_file_identity(LOG_FILE)

    while True:
        # [C3] Try to flush any queued logs before reading new ones
        if retry_queue:
            flush_retry_queue()

        line = file.readline()

        if not line:
            # No new data — check for rotation
            time.sleep(0.5)

            # [C1] Check if file was truncated
            current_pos = file.tell()
            _, current_size = get_file_identity(LOG_FILE)
            if current_size is not None and current_pos > current_size:
                logger.warning("Log file truncated. Reopening from start.")
                file.close()
                file = open(LOG_FILE, 'r')
                file.seek(0)
                current_inode, _ = get_file_identity(LOG_FILE)
                continue

            # [C1] Check if file was replaced (new inode)
            new_inode, _ = get_file_identity(LOG_FILE)
            if new_inode is not None and new_inode != current_inode:
                logger.warning("Log file replaced (new inode). Reopening.")
                file.close()
                file = open(LOG_FILE, 'r')
                file.seek(0)
                current_inode = new_inode
                continue

            continue

        clean_log = line.strip()
        if not clean_log:
            continue

        # [C2] Sanitize with structure-preserving blacklist
        safe_line = sanitize_log_line(clean_log)

        logger.info("New log detected: %.80s%s",
                     safe_line, "..." if len(safe_line) > 80 else "")
        logger.info("Forwarding to ButterClaw Brain...")

        payload = {
            "threat_type": "Live Gateway Log",
            "raw_data": safe_line
        }

        if not send_to_server(payload):
            retry_queue.append(payload)
            logger.warning(
                "Log queued for retry. Queue depth: %d/%d",
                len(retry_queue), RETRY_QUEUE_MAX
            )


# =============================================
# BOOT
# =============================================

def main():
    # [L1] CLI argument for replay mode
    parser = argparse.ArgumentParser(
        description="ButterClaw Log Watcher v0.2"
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Process entire log file from start instead of tailing"
    )
    args = parser.parse_args()

    # [M4] Prevent duplicate instances
    check_pid_file()
    atexit.register(cleanup_pid_file)

    logger.info("Watcher online. Staring intensely at %s...", LOG_FILE)

    if retry_queue:
        logger.info("Retry queue initialized (max %d entries).", RETRY_QUEUE_MAX)

    try:
        watch_log(replay=args.replay)
    except KeyboardInterrupt:
        # [M1] Fixed shutdown typo
        logger.info("SHUTDOWN: Watcher received SIGINT. Automator going dark.")
        if retry_queue:
            logger.warning(
                "%d unsent log(s) in retry queue — will be lost.",
                len(retry_queue)
            )


if __name__ == "__main__":
    main()

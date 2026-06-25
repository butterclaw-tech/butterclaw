"""
ButterClaw v0.6.5 — Visual TUI Dashboard
=========================================
Real-time terminal monitoring for the Agentic SOC.
"""

import os
import sys
import time
import sqlite3
import shutil
from policy_engine import _get_db, get_policy_event_count, get_policy_events, init_policy_db

# Ensure tables exist before we try to read them!
init_policy_db()

# ANSI Terminal Escapes for UI layout
HOME = "\033[H"
CLEAR_EOS = "\033[J"
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
REVERSE = "\033[7m"

def render_loop():
    # Initial full screen clear before the loop starts
    sys.stdout.write("\033[2J")
    
    try:
        while True:
            size = shutil.get_terminal_size()
            width = size.columns
            height = size.lines

            # Reserve lines for Header, Metrics, and Footer
            max_events = height - 6
            
            # 1. Start building the frame buffer in memory
            frame = []
            frame.append(HOME) # Move cursor to top-left instantly
            
            # 2. Draw Header
            frame.append(f"{REVERSE}{BOLD}{' 🦞 BUTTERCLAW AGENTIC SOC // REAL-TIME EVENT STREAM ':^{width}}{RESET}")
            frame.append(f"{CYAN}{'=' * width}{RESET}")
            
            # 3. Draw Metrics
            try:
                conn = _get_db()
                total_events = conn.execute("SELECT COUNT(*) FROM policy_events").fetchone()[0]
                blocked = conn.execute("SELECT COUNT(*) FROM policy_events WHERE action_taken IN ('block', 'override_critical', 'skip_tool')").fetchone()[0]
                active_rules = conn.execute("SELECT COUNT(*) FROM policies WHERE enabled = 1").fetchone()[0]
                conn.close()
            except Exception:
                total_events, blocked, active_rules = 0, 0, 0

            import policy_engine
            arsenal_count = len(policy_engine.COMPILED_SIGNATURES)
            paranoia = os.getenv("BUTTERCLAW_PARANOIA", "2")

            metrics_str = f" [Paranoia: Lv {paranoia}]  [Active Rules: {active_rules}]  [Zero-Day Arsenal: {arsenal_count}]  [Events: {total_events}]  [Blocked: {RED}{blocked}{RESET}]"
            frame.append(metrics_str)
            frame.append(f"{CYAN}{'-' * width}{RESET}")
            
            # 4. Draw Events
            events = get_policy_events(limit=max_events)
            if not events:
                frame.append(f"\n{YELLOW}{'  [ SYSTEM IDLE — LISTENING FOR NETWORK/TOOL TRAFFIC ]':^{width}}{RESET}")
            else:
                for ev in events:
                    ts = ev["timestamp"].split("T")[-1].replace("Z", "")
                    action = ev["action_taken"].upper()
                    
                    # Color code based on threat lethality
                    if action in ("BLOCK", "OVERRIDE_CRITICAL", "SKIP_TOOL"):
                        action_fmt = f"{RED}{BOLD}[{action:^17}]{RESET}"
                    else:
                        action_fmt = f"{GREEN}[{action:^17}]{RESET}"

                    p_name = ev["policy_name"]
                    if len(p_name) > 25:
                        p_name = p_name[:22] + "..."

                    preview = ev["payload_preview"] or ""
                    if len(preview) > 40:
                        preview = preview[:37] + "..."

                    frame.append(f" {ts} | {action_fmt} | {CYAN}{p_name:<25}{RESET} | {preview}")

            # Clear any leftover artifacts from the end of our events to the bottom of the screen
            frame.append(CLEAR_EOS)
            
            # 5. Draw Footer (Locked to bottom row)
            frame.append(f"\033[{height};0H{BOLD}{CYAN}Ctrl+C to exit dashboard. Monitoring Policy Events...{RESET}")
            
            # 6. Flush the entire frame to the terminal instantly
            sys.stdout.write('\n'.join(frame))
            sys.stdout.flush()
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        print("👋 Dashboard detached. ButterClaw daemon remains running in background.")

if __name__ == "__main__":
    render_loop()
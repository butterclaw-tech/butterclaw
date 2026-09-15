"""
ButterClaw v0.8.0 — Visual TUI Dashboard
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
                semantic_blocked = conn.execute("SELECT COUNT(*) FROM policy_events WHERE action_taken IN ('block', 'override_critical', 'skip_tool')").fetchone()[0]
                
                # --- v0.8.0 SPATIAL METRICS ---
                spatial_events = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
                spatial_blocked = conn.execute("SELECT COUNT(*) FROM telemetry_events WHERE spatial_payload LIKE '%\"_verdict\": \"BLOCK\"%'").fetchone()[0]
                tainted_swarms = conn.execute("SELECT COUNT(*) FROM sessions WHERE taint_level > 0").fetchone()[0]
                
                # --- DREAMER METRICS ---
                try:
                    dreamer_sigs = conn.execute("SELECT COUNT(*) FROM memory_signatures").fetchone()[0]
                except Exception:
                    dreamer_sigs = 0 # Fallback in case table migration hasn't run
                # ------------------------------
                
                active_rules = conn.execute("SELECT COUNT(*) FROM policies WHERE enabled = 1").fetchone()[0]
                conn.close()
            except Exception:
                total_events, semantic_blocked, active_rules, spatial_events, tainted_swarms, spatial_blocked, dreamer_sigs = 0, 0, 0, 0, 0, 0, 0

            import policy_engine
            # Combine static hardcoded signatures with dynamic Dreamer attractors
            arsenal_count = len(policy_engine.COMPILED_SIGNATURES) + dreamer_sigs
            
            # Combine legacy blocks with new kinetic spatial blocks
            total_blocked = semantic_blocked + spatial_blocked

            # Combine legacy events with new spatial events for the grand total
            total_combined_events = total_events + spatial_events
            
            paranoia = os.getenv("BUTTERCLAW_PARANOIA", "2")

            # Emphasize tainted swarms in RED if they exist
            swarm_fmt = f"{RED}{BOLD}[Tainted: {tainted_swarms}]{RESET}" if tainted_swarms > 0 else f"[Tainted: 0]"

            #metrics_str = f" [Paranoia: Lv {paranoia}]  [Spatial: {spatial_events}]  {swarm_fmt}  [Zero-Day Arsenal: {arsenal_count}]  [Events: {total_events}]  [Blocked: {RED}{total_blocked}{RESET}]"
            metrics_str = f" [Paranoia: Lv {paranoia}]  [Spatial: {spatial_events}]  {swarm_fmt}  [Zero-Day Arsenal: {arsenal_count}]  [Semantic: {total_events}]  [Blocked: {RED}{total_blocked}{RESET}]"
            #metrics_str = f" [Paranoia: Lv {paranoia}]  [Spatial: {spatial_events}]  {swarm_fmt}  [Zero-Day Arsenal: {arsenal_count}]  [Events: {total_combined_events}]  [Blocked: {RED}{total_blocked}{RESET}]"
            frame.append(metrics_str)
            frame.append(f"{CYAN}{'-' * width}{RESET}")
            
            # 4. Draw Unified Events (Semantic + Spatial)
            try:
                import datetime # Import inline to ensure float conversion works
                conn = _get_db()
                conn.row_factory = sqlite3.Row
            
                # Fetch legacy semantic events
                sem_events = conn.execute(
                    "SELECT timestamp, action_taken, policy_name, payload_preview FROM policy_events ORDER BY id DESC LIMIT ?", 
                    (max_events,)
                ).fetchall()
                events = [dict(e) for e in sem_events]
            
                # Fetch new spatial telemetry (Fixed column names: event_id, spatial_payload)
                spat_events = conn.execute(
                    "SELECT timestamp, action_type, spatial_payload FROM telemetry_events ORDER BY event_id DESC LIMIT ?", 
                    (max_events,)
                ).fetchall()
            
                for r in spat_events:
                    # 1. Safely extract the string FIRST so it always exists in memory
                    raw_payload = r["spatial_payload"]
                    payload_str = str(raw_payload) if raw_payload else "{}"
                
                    # 2. Parse the injected meta-tags
                    try:
                        import json
                        p_dict = json.loads(payload_str)
                        is_block = p_dict.get("_verdict") == "BLOCK"
                        policy_name = p_dict.get("_policy", "Spatial Pipeline")
                    
                        # Hide the meta-tags from the preview so it looks clean
                        p_dict.pop("_verdict", None)
                        p_dict.pop("_policy", None)
                        display_payload = json.dumps(p_dict)
                    except Exception:
                        # If JSON parsing fails, use the raw string and default values
                        is_block = False
                        policy_name = "Spatial Pipeline"
                        display_payload = payload_str
                
                    # Convert UNIX float timestamp to ISO format
                    import datetime
                    iso_time = datetime.datetime.fromtimestamp(r["timestamp"], tz=datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                
                    events.append({
                        "timestamp": iso_time,
                        "action_taken": "BLOCK" if is_block else "ALLOW",
                        "policy_name": policy_name,
                        "payload_preview": f"{r['action_type']} -> {display_payload[:30]}"
                    })
            
                conn.close()
            
                # Sort combined list by timestamp descending
                events.sort(key=lambda x: str(x["timestamp"]), reverse=True)
                events = events[:max_events]
            except Exception as e:
                events = []
                frame.append(f"{RED}🚨 SQL ERROR: {e}{RESET}")

            if not events:
                frame.append(f"\n{YELLOW}{'  [ SYSTEM IDLE — LISTENING FOR NETWORK/TOOL TRAFFIC ]':^{width}}{RESET}")
            else:
                for ev in events:
                    ts = ev.get("timestamp", "").split("T")[-1].replace("Z", "")
                    action = ev.get("action_taken", "").upper()
                
                    # Color code based on threat lethality
                    if action in ("BLOCK", "OVERRIDE_CRITICAL", "SKIP_TOOL"):
                        action_fmt = f"{RED}{BOLD}[{action:^17}]{RESET}"
                    else:
                        action_fmt = f"{GREEN}[{action:^17}]{RESET}"

                    p_name = ev.get("policy_name", "")
                    if len(p_name) > 25:
                        p_name = p_name[:22] + "..."

                    preview = str(ev.get("payload_preview") or "")
                
                    # Dynamically calculate remaining horizontal space to prevent terminal wrapping
                    # 65 = the total width of the timestamp, action block, and policy name combined
                    avail_space = width - 65 
                    if len(preview) > avail_space and avail_space > 0:
                        preview = preview[:avail_space-3] + "..."
                    elif avail_space <= 0:
                        preview = ""

                    frame.append(f" {ts} | {action_fmt} | {CYAN}{p_name:<25}{RESET} | {preview}\033[K")

            # Clear any leftover artifacts
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
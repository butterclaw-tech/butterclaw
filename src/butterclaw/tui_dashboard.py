"""
ButterClaw v0.9.3 — Visual TUI Dashboard - src layout Mega
=========================================
Real-time terminal monitoring for the Agentic SOC.
"""

import os
import re
import sys
import time
import json
import datetime
import sqlite3
import shutil
from contextlib import closing
from butterclaw.policy_engine import _get_db, get_policy_event_count, get_policy_events, init_policy_db

# ANSI Terminal Escapes for UI layout
HOME = "\033[H"
CLEAR_SCREEN = "\033[2J"
CLEAR_EOS = "\033[J"
CLEAR_EOL = "\033[K"
WRAP_OFF = "\033[?7l"
WRAP_ON = "\033[?7h"
CURSOR_HIDE = "\033[?25l"
CURSOR_SHOW = "\033[?25h"

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
REVERSE = "\033[7m"

ANSI_RE = re.compile(r"\033\[[0-9;]*[a-zA-Z]")


def _fit_line(text: str, max_cols: int) -> str:
    """Truncates a string containing ANSI escapes to max_cols visible cells without bleeding styles."""
    if max_cols <= 0:
        return CLEAR_EOL
    visible = 0
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\033":
            m = ANSI_RE.match(text, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        ch = text[i]
        ch_w = 2 if ord(ch) > 0xFFFF else 1
        if visible + ch_w > max_cols:
            break
        out.append(ch)
        visible += ch_w
        i += 1
    return "".join(out) + RESET + CLEAR_EOL


def render_loop():
    # Ensure tables exist before we try to read them!
    init_policy_db()

    # Clear screen, hide cursor, and disable terminal auto-line-wrap
    sys.stdout.write(CLEAR_SCREEN + HOME + CURSOR_HIDE + WRAP_OFF)
    sys.stdout.flush()

    last_size = (0, 0)

    try:
        while True:
            size = shutil.get_terminal_size((100, 30))
            width = max(20, size.columns)
            height = max(8, size.lines)
            safe_w = width - 1  # Stay 1 col shy of right margin to prevent ConPTY wrap glitches

            # Wipe reflowed border artifacts immediately when terminal is stretched/shrunk
            if (width, height) != last_size:
                sys.stdout.write(CLEAR_SCREEN + HOME)
                last_size = (width, height)

            # Reserve lines for Header (2), Metrics (2), Blank/Clear (1), and Footer (1)
            max_events = max(1, height - 6)

            # 1. Start building the frame buffer (attach HOME directly to Row 1, no extra \n)
            frame = []

            # 2. Draw Header (subtract 1 extra char because 🦞 renders 2 cells wide)
            title = " 🦞 BUTTERCLAW AGENTIC SOC // REAL-TIME EVENT STREAM "
            header_pad = max(1, safe_w - 1)
            frame.append(f"{HOME}{REVERSE}{BOLD}{title[:header_pad]:^{header_pad}}{RESET}{CLEAR_EOL}")
            frame.append(f"{CYAN}{'=' * safe_w}{RESET}{CLEAR_EOL}")

            # 3. Draw Metrics
            try:
                with closing(_get_db()) as conn:
                    total_events = conn.execute("SELECT COUNT(*) FROM policy_events").fetchone()[0]
                    semantic_blocked = conn.execute(
                        "SELECT COUNT(*) FROM policy_events WHERE action_taken IN ('block', 'override_critical', 'skip_tool')"
                    ).fetchone()[0]

                    # --- v0.8.0 SPATIAL METRICS ---
                    spatial_events = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
                    spatial_blocked = conn.execute(
                        'SELECT COUNT(*) FROM telemetry_events WHERE spatial_payload LIKE \'%"_verdict": "BLOCK"%\''
                    ).fetchone()[0]
                    tainted_swarms = conn.execute("SELECT COUNT(*) FROM sessions WHERE taint_level > 0").fetchone()[0]

                    # --- DREAMER METRICS ---
                    try:
                        dreamer_sigs = conn.execute("SELECT COUNT(*) FROM memory_signatures").fetchone()[0]
                    except Exception:
                        dreamer_sigs = 0

                    # --- v0.9.3 SKILLGUARD METRICS (Gate M5) ---
                    try:
                        skills_ok = conn.execute(
                            "SELECT COUNT(*) FROM skill_attestations WHERE status = 'APPROVED'"
                        ).fetchone()[0]
                        skills_quar = conn.execute(
                            "SELECT COUNT(*) FROM skill_attestations WHERE status != 'APPROVED'"
                        ).fetchone()[0]
                    except Exception:
                        skills_ok, skills_quar = 0, 0

                    active_rules = conn.execute("SELECT COUNT(*) FROM policies WHERE enabled = 1").fetchone()[0]
            except Exception:
                (
                    total_events, semantic_blocked, active_rules,
                    spatial_events, tainted_swarms, spatial_blocked,
                    dreamer_sigs, skills_ok, skills_quar
                ) = 0, 0, 0, 0, 0, 0, 0, 0, 0

            import butterclaw.policy_engine as policy_engine
            arsenal_count = len(policy_engine.COMPILED_SIGNATURES) + dreamer_sigs
            total_blocked = semantic_blocked + spatial_blocked + skills_quar
            paranoia = os.getenv("BUTTERCLAW_PARANOIA", "2")

            swarm_fmt = f"{RED}{BOLD}[Tainted: {tainted_swarms}]{RESET}" if tainted_swarms > 0 else "[Tainted: 0]"
            if skills_quar > 0:
                skill_fmt = f"{RED}{BOLD}[Skills: {skills_ok} OK / {skills_quar} QUAR]{RESET}"
            else:
                skill_fmt = f"[Skills: {skills_ok} OK]"

            metrics_str = (
                f" [Paranoia: Lv {paranoia}]  [Spatial: {spatial_events}]  {swarm_fmt}  "
                f"{skill_fmt}  [Arsenal: {arsenal_count}]  [Semantic: {total_events}]  "
                f"[Blocked: {RED}{total_blocked}{RESET}]"
            )
            frame.append(_fit_line(metrics_str, safe_w))
            frame.append(f"{CYAN}{'-' * safe_w}{RESET}{CLEAR_EOL}")

            # 4. Draw Unified Events (Semantic + Spatial + SkillGuard Attestations)
            try:
                with closing(_get_db()) as conn:
                    conn.row_factory = sqlite3.Row

                    sem_events = conn.execute(
                        "SELECT timestamp, action_taken, policy_name, payload_preview FROM policy_events ORDER BY id DESC LIMIT ?",
                        (max_events,)
                    ).fetchall()
                    events = [dict(e) for e in sem_events]

                    spat_events = conn.execute(
                        "SELECT timestamp, action_type, spatial_payload FROM telemetry_events ORDER BY event_id DESC LIMIT ?",
                        (max_events,)
                    ).fetchall()

                    for r in spat_events:
                        raw_payload = r["spatial_payload"]
                        payload_str = str(raw_payload) if raw_payload else "{}"

                        try:
                            p_dict = json.loads(payload_str)
                            is_block = p_dict.get("_verdict") == "BLOCK"
                            policy_name = p_dict.get("_policy", "Spatial Pipeline")

                            p_dict.pop("_verdict", None)
                            p_dict.pop("_policy", None)
                            display_payload = json.dumps(p_dict)
                        except Exception:
                            is_block = False
                            policy_name = "Spatial Pipeline"
                            display_payload = payload_str

                        iso_time = datetime.datetime.fromtimestamp(
                            r["timestamp"], tz=datetime.timezone.utc
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")

                        events.append({
                            "timestamp": iso_time,
                            "action_taken": "BLOCK" if is_block else "ALLOW",
                            "policy_name": policy_name,
                            "payload_preview": f"{r['action_type']} -> {display_payload[:30]}"
                        })

                    # Fetch v0.9.3 SkillGuard attestation events
                    try:
                        skill_rows = conn.execute(
                            "SELECT skill_name, status, risk_score, merkle_root, attested_at "
                            "FROM skill_attestations ORDER BY attested_at DESC LIMIT ?",
                            (max_events,)
                        ).fetchall()
                        for sr in skill_rows:
                            is_quar = sr["status"] != "APPROVED"
                            events.append({
                                "timestamp": sr["attested_at"],
                                "action_taken": "QUARANTINED" if is_quar else "ATTESTED",
                                "policy_name": "SkillGuard (Gate M5)",
                                "payload_preview": (
                                    f"skill={sr['skill_name']} risk={sr['risk_score']}% "
                                    f"merkle={sr['merkle_root'][:10]}..."
                                )
                            })
                    except Exception:
                        pass

                events.sort(key=lambda x: str(x["timestamp"]), reverse=True)
                events = events[:max_events]
            except Exception as e:
                events = []
                frame.append(_fit_line(f" {RED}🚨 SQL ERROR: {e}{RESET}", safe_w))

            if not events:
                idle_msg = "  [ SYSTEM IDLE — LISTENING FOR NETWORK/TOOL TRAFFIC ]"
                frame.append(CLEAR_EOL)
                frame.append(_fit_line(f"{YELLOW}{idle_msg:^{safe_w}}{RESET}", safe_w))
            else:
                for ev in events:
                    ts = ev.get("timestamp", "").split("T")[-1].replace("Z", "")[:8]
                    action = ev.get("action_taken", "").upper()[:17]

                    if action in ("BLOCK", "OVERRIDE_CRITICAL", "SKIP_TOOL", "QUARANTINED"):
                        action_fmt = f"{RED}{BOLD}[{action:^17}]{RESET}"
                    else:
                        action_fmt = f"{GREEN}[{action:^17}]{RESET}"

                    p_name = ev.get("policy_name", "")
                    if len(p_name) > 25:
                        p_name = p_name[:22] + "..."

                    preview = str(ev.get("payload_preview") or "").replace("\n", " ")
                    avail_space = safe_w - 64
                    if len(preview) > avail_space and avail_space > 3:
                        preview = preview[:avail_space - 3] + "..."
                    elif avail_space <= 3:
                        preview = ""

                    row_str = f" {ts:<8} | {action_fmt} | {CYAN}{p_name:<25}{RESET} | {preview}"
                    frame.append(_fit_line(row_str, safe_w))

            # 5. Clear below last event row and pin Footer to bottom line without trailing \n
            footer_text = f"{BOLD}{CYAN}Ctrl+C to exit dashboard. Monitoring Policy, Spatial & SkillGuard Events...{RESET}"
            output = "\n".join(frame)
            if len(frame) < height:
                output += "\n" + CLEAR_EOS
            output += f"\033[{height};1H{_fit_line(footer_text, safe_w)}"

            # 6. Flush the entire frame to the terminal instantly
            sys.stdout.write(output)
            sys.stdout.flush()

            # Poll terminal resize every 0.2s while keeping DB queries at 1.0s cadence
            for _ in range(5):
                time.sleep(0.2)
                cur = shutil.get_terminal_size((100, 30))
                if (max(20, cur.columns), max(8, cur.lines)) != last_size:
                    break

    except KeyboardInterrupt:
        pass
    finally:
        # Always restore line-wrap and cursor visibility on exit
        sys.stdout.write(WRAP_ON + CURSOR_SHOW + CLEAR_SCREEN + HOME)
        sys.stdout.flush()
        print("👋 Dashboard detached. ButterClaw daemon remains running in background.")


if __name__ == "__main__":
    render_loop()
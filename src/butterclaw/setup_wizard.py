#!/usr/bin/env python3
"""
ButterClaw Setup Wizard — ButterClaw v0.9.3 - src layout Mega
Interactively generates a .env configuration file and provides CLI
utilities for SkillGuard SKILL.md package auditing.

Usage:
    python setup_wizard.py
    python setup_wizard.py --output /path/to/.env
    python setup_wizard.py --audit-skill ./skills/my-skill
    python setup_wizard.py --list-skills

Zero external dependencies. Requires Python 3.8+.
"""

import os
import sys
import json
import shutil
import sqlite3
import secrets
import argparse
import textwrap
import datetime
from typing import Optional
from pathlib import Path

# Ensure src/ layout is importable when running CLI skill commands
REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------

def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _safe_print(text: str) -> None:
    """Print with graceful ASCII fallback for terminals that can't handle Unicode."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _configure_stdout_encoding() -> None:
    """On Windows, attempt to upgrade stdout to UTF-8 so box-drawing chars and
    emoji don't throw UnicodeEncodeError on legacy cp1252 terminals."""
    if sys.platform == "win32":
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass  # best-effort; _safe_print handles the fallback


_COLOR = _supports_color()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def bold(t):    return _c(t, "1")
def dim(t):     return _c(t, "2")
def cyan(t):    return _c(t, "36")
def green(t):   return _c(t, "32")
def yellow(t):  return _c(t, "33")
def red(t):     return _c(t, "31")
def blue(t):    return _c(t, "34")


def section(title: str):
    width = 62
    _safe_print("")
    _safe_print(cyan("\u250c" + "\u2500" * width + "\u2510"))
    pad = (width - len(title) - 2) // 2
    _safe_print(cyan("\u2502") + " " * pad + bold(cyan(title)) + " " * (width - pad - len(title)) + cyan("\u2502"))
    _safe_print(cyan("\u2514" + "\u2500" * width + "\u2518"))

def info(msg):  _safe_print(f"  {blue('i')}  {msg}")
def warn(msg):  _safe_print(f"  {yellow('!')}  {yellow(msg)}")
def ok(msg):    _safe_print(f"  {green('*')}  {green(msg)}")
def tip(msg):   _safe_print(f"  {dim('-')}  {dim(msg)}")


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def ask(prompt: str, default: Optional[str] = None, required: bool = False,
        secret: bool = False, validator=None) -> str:
    display_default = dim(f" [{default}]") if default is not None else ""
    if secret and default:
        display_default = dim(f" [{'*' * min(len(default), 8)}]")
    while True:
        try:
            raw = input(f"  {bold('?')} {prompt}{display_default}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            _safe_print(yellow("\n  Setup interrupted. No file was written."))
            sys.exit(0)
        value = raw if raw else (default or "")
        if required and not value:
            warn("This field is required. Please enter a value.")
            continue
        if validator and value:
            error = validator(value)
            if error:
                warn(error)
                continue
        return value


def ask_choice(prompt: str, choices: list, default: Optional[str] = None) -> str:
    """Numbered menu picker."""
    _safe_print(f"\n  {bold('?')} {prompt}")
    for i, (key, label) in enumerate(choices, 1):
        marker = green("*") if key == default else dim("o")
        _safe_print(f"    {marker} {i}) {label}")
    nums = "/".join(str(i) for i in range(1, len(choices) + 1))
    default_num = next((str(i) for i, (k, _) in enumerate(choices, 1) if k == default), None)

    def _validate(v):
        if not v.isdigit() or int(v) < 1 or int(v) > len(choices):
            return f"Enter a number between 1 and {len(choices)}"
    # Fix #2: required=True prevents int("") crash when default_num is None
    result = ask(f"Choice ({nums})", default=default_num, required=True, validator=_validate)
    idx = int(result) - 1
    return choices[idx][0]


def ask_bool(prompt: str, default: bool = True) -> bool:
    def_str = "Y/n" if default else "y/N"
    raw = ask(f"{prompt} ({def_str})", default="y" if default else "n").lower()
    return raw in ("y", "yes", "true", "1")


def generate_key(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_hex(24)}"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def valid_port(v):
    if not v.isdigit() or not (1 <= int(v) <= 65535):
        return "Port must be a number between 1 and 65535."

def valid_url(v):
    if not (v.startswith("http://") or v.startswith("https://")):
        return "Must start with http:// or https://"

def valid_int_range(lo, hi):
    def _v(v):
        if not v.isdigit() or not (lo <= int(v) <= hi):
            return f"Must be an integer between {lo} and {hi}."
    return _v

def valid_positive_int(v):
    if not v.isdigit() or int(v) < 1:
        return "Must be a positive integer."

def valid_positive_float(v):
    try:
        if float(v) <= 0:
            raise ValueError
    except ValueError:
        return "Must be a positive number (e.g. 6.0 or 300)."


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = r"""
  ██████╗ ██╗   ██╗████████╗████████╗███████╗██████╗  ██████╗██╗      █████╗ ██╗    ██╗
  ██╔══██╗██║   ██║╚══██╔══╝╚══██╔══╝██╔════╝██╔══██╗██╔════╝██║     ██╔══██╗██║    ██║
  ██████╔╝██║   ██║   ██║      ██║   █████╗  ██████╔╝██║     ██║     ███████║██║ █╗ ██║
  ██╔══██╗██║   ██║   ██║      ██║   ██╔══╝  ██╔══██╗██║     ██║     ██╔══██║██║███╗██║
  ██████╔╝╚██████╔╝   ██║      ██║   ███████╗██║  ██║╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝  ╚═════╝    ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
"""

def print_banner():
    _safe_print(cyan(BANNER))
    _safe_print(bold(cyan("  ButterClaw v0.9.3 -- Interactive Setup Wizard")))
    _safe_print(dim("  Agentic SOC * Local-first * Zero-trust credential locker"))
    _safe_print("")
    _safe_print(dim("  This wizard will ask you a series of questions and generate a"))
    _safe_print(dim("  ready-to-use .env file. Press Ctrl+C at any time to abort."))
    _safe_print(dim("  Defaults shown in [brackets] -- press Enter to accept them."))
    _safe_print("")

def _guard_windows_docker_path(db_path: Optional[str]) -> None:
    """Prevents CLI commands run on the Windows host from creating C:\\data when .env uses Docker /data paths."""
    if sys.platform != "win32":
        return
    from butterclaw.config import cfg
    resolved_db = str(db_path or cfg.DB_PATH).replace("\\", "/")
    if resolved_db.startswith("/data/") or resolved_db.startswith("C:/data/"):
        warn("Docker path (/data/...) detected on Windows host!")
        info("To keep host drives clean, run SkillGuard inside the container:")
        _safe_print(f"    {cyan('dash.bat skills')}")
        _safe_print(f"    {cyan('dash.bat audit /data/skills/<skill-folder>')}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# SkillGuard CLI Actions (--audit-skill / --list-skills)
# ---------------------------------------------------------------------------

def cli_audit_skill(skill_path: str, db_path: Optional[str] = None, strict: bool = False) -> int:
    """Runs SkillGuard static + Merkle attestation on a SKILL.md folder and prints a formatted report."""
    _guard_windows_docker_path(db_path)
    from butterclaw.skill_guard import SkillGuard

    section("SkillGuard Pre-Flight Package Auditor")
    guard = SkillGuard(db_path=db_path)
    try:
        report = guard.audit_and_attest(skill_path)
    except Exception as exc:
        _safe_print(f"  {red('X')}  {red(f'Audit failed: {exc}')}")
        return 1

    status_str = green(bold("APPROVED")) if report["status"] == "APPROVED" else red(bold("QUARANTINED"))
    risk_color = green if report["risk_score"] == 0 else (yellow if report["risk_score"] < 50 else red)

    _safe_print(f"  {bold('Skill Name   :')} {cyan(report['skill_name'])}")
    _safe_print(f"  {bold('Package Path :')} {dim(report['package_path'])}")
    _safe_print(f"  {bold('Description  :')} {report['declared_description'] or dim('(none)')}")
    _safe_print(f"  {bold('Merkle Root  :')} {yellow(report['merkle_root'])}")
    _safe_print(f"  {bold('Files Hashed :')} {len(report['file_hashes'])}")
    _safe_print(f"  {bold('Risk Score   :')} {risk_color(str(report['risk_score']) + ' / 100')}")
    _safe_print(f"  {bold('Verdict      :')} {status_str}")
    _safe_print("")

    if report["findings"]:
        warn(f"Detected {len(report['findings'])} supply-chain / policy finding(s):")
        for finding in report["findings"]:
            _safe_print(f"    {red('-')} {finding}")
    else:
        ok("Zero static, AST, or steganographic findings detected.")

    _safe_print("")
    if strict and report["status"] != "APPROVED":
        return 2
    return 0


def cli_list_skills(db_path: Optional[str] = None) -> int:
    """Prints a formatted table of all attested SKILL.md packages stored in SQLite."""
    _guard_windows_docker_path(db_path)
    from contextlib import closing
    from butterclaw.skill_guard import SkillGuard

    guard = SkillGuard(db_path=db_path)
    section("SkillGuard Attestation Registry (Gate M5)")
    info(f"Database: {dim(guard.db_path)}")
    _safe_print("")

    if not Path(guard.db_path).exists():
        warn("Database file does not exist yet. Audit a skill first with --audit-skill.")
        return 0

    with closing(sqlite3.connect(guard.db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT skill_name, status, risk_score, merkle_root, attested_at, package_path "
            "FROM skill_attestations ORDER BY attested_at DESC"
        ).fetchall()

    if not rows:
        tip("No SKILL.md packages attested yet.")
        _safe_print("")
        return 0

    header = f"  {'SKILL NAME':<22} {'STATUS':<13} {'RISK':<6} {'MERKLE PREFIX':<16} {'ATTESTED AT'}"
    _safe_print(bold(cyan(header)))
    _safe_print(dim("  " + "-" * 78))

    for r in rows:
        name_col = bold(f"{r['skill_name'][:22]:<22}")
        st_raw = r["status"]
        st_col = green(f"{st_raw:<13}") if st_raw == "APPROVED" else red(f"{st_raw:<13}")
        risk_str = f"{r['risk_score']:>3}%"
        merkle_short = r["merkle_root"][:12] + "..."
        merkle_col = yellow(f"{merkle_short:<16}")
        _safe_print(
            f"  {name_col} {st_col} {risk_str:<6} "
            f"{merkle_col} {dim(r['attested_at'])}"
        )
    _safe_print("")
    return 0

    header = f"  {'SKILL NAME':<22} {'STATUS':<13} {'RISK':<6} {'MERKLE PREFIX':<16} {'ATTESTED AT'}"
    _safe_print(bold(cyan(header)))
    _safe_print(dim("  " + "-" * 78))

    for r in rows:
        st_raw = r["status"]
        st_col = green(f"{st_raw:<13}") if st_raw == "APPROVED" else red(f"{st_raw:<13}")
        risk_str = f"{r['risk_score']:>3}%"
        merkle_short = r["merkle_root"][:12] + "..."
        _safe_print(
            f"  {bold(r['skill_name'][:22]):<22} {st_col} {risk_str:<6} "
            f"{yellow(merkle_short):<16} {dim(r['attested_at'])}"
        )
    _safe_print("")
    return 0


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

def run_wizard() -> dict:
    cfg = {}

    # ── 1 / 11 DEPLOYMENT MODE ───────────────────────────────────────────────
    section("  1 / 11  *  Deployment Mode")
    info("How are you running ButterClaw?")
    tip("Docker is recommended for production; bare-metal is fine for local dev.")

    deploy_mode = ask_choice(
        "Select deployment mode:",
        choices=[
            ("docker",    "Docker / Docker Compose  (recommended)"),
            ("baremetal", "Bare-metal / virtualenv  (local dev)"),
            ("systemd",   "systemd service          (Linux server)"),
        ],
        default="docker",
    )
    cfg["_deploy_mode"] = deploy_mode

    # ── 2 / 11 INSTANCE IDENTITY ─────────────────────────────────────────────
    section("  2 / 11  *  Instance Identity")
    info("A unique name for this node. Appears in health checks, alert payloads,")
    info("and the boot banner. Use separate names for prod / staging / dev.")
    _safe_print("")

    cfg["BUTTERCLAW_INSTANCE_ID"] = ask("Instance ID", default="butterclaw-prod")

    # ── 3 / 11 SERVER ────────────────────────────────────────────────────────
    section("  3 / 11  *  Server Settings")

    default_host = "0.0.0.0" if deploy_mode in ("docker", "systemd") else "127.0.0.1"
    info("Bind address: 0.0.0.0 exposes on all interfaces (Docker/prod).")
    info("Use 127.0.0.1 to restrict to localhost only (local dev).")
    _safe_print("")

    cfg["BUTTERCLAW_HOST"] = ask("Bind host", default=default_host)
    cfg["BUTTERCLAW_PORT"] = ask("HTTP port", default="5000", validator=valid_port)

    debug_default = deploy_mode == "baremetal"
    if ask_bool("Enable debug mode?  " + red("! NEVER in production"), default=debug_default):
        cfg["BUTTERCLAW_DEBUG"] = "true"
        warn("Debug mode exposes stack traces. Keep it disabled in production.")
    else:
        cfg["BUTTERCLAW_DEBUG"] = "false"

    # ── 4 / 11 DATABASE & CORS ───────────────────────────────────────────────
    section("  4 / 11  *  Database & CORS")
    info("ButterClaw uses a single SQLite file for all persistent data.")
    _safe_print("")

    if deploy_mode == "docker":
        tip("Docker: mount a named volume and set DB_PATH inside it.")
        tip("  volumes: butterclaw-data:/data")
        db_default = "/data/butterclaw.db"
    else:
        db_default = "./butterclaw.db"

    cfg["BUTTERCLAW_DB_PATH"] = ask("SQLite DB path", default=db_default)

    _safe_print("")
    info("CORS origins: comma-separated list of allowed browser origins.")
    tip("Docker + nginx: use your domain.  Local: leave blank for defaults.")
    cors_raw = ask("CORS origins (leave blank for localhost defaults)", default="")
    if cors_raw:
        cfg["BUTTERCLAW_CORS_ORIGINS"] = cors_raw

    # ── 5 / 11 BRAIN / OLLAMA ────────────────────────────────────────────────
    section("  5 / 11  *  Guardian Brain")
    info("ButterClaw supports local Ollama (privacy-first) and remote Gemini APIs.")

    if deploy_mode == "docker":
        ollama_default = "http://host.docker.internal:11434"
        tip("Docker networking detected: using host.docker.internal for Ollama")
    else:
        ollama_default = "http://localhost:11434"

    cfg["BUTTERCLAW_OLLAMA_URL"]  = ask("Ollama base URL", default=ollama_default, validator=valid_url)
    cfg["BUTTERCLAW_OLLAMA_PATH"] = "/api/chat"

    _safe_print("")
    if ask_bool("Configure a Google Gemini API key? (allows switching models later)", default=True):
        cfg["BUTTERCLAW_GOOGLE_API_KEY"] = ask(
            "Google API key", required=True, secret=True,
            validator=lambda v: "Looks like a placeholder -- enter your real key." if v.startswith("your-") else None,
        )

    _safe_print("")
    info("Which model should be active on boot?")
    tip("  Local:  butterclaw-optimized:latest")
    tip("  Remote: gemini-3.5-flash-lite")

    cfg["BUTTERCLAW_MODEL"] = ask("Active model name", default="butterclaw-optimized:latest")
    cfg["_brain_mode"] = "remote" if "gemini" in cfg["BUTTERCLAW_MODEL"].lower() else "local"

    # ── 6 / 11 API KEYS ──────────────────────────────────────────────────────
    section("  6 / 11  *  API Keys & Alerts")
    info("BUTTERCLAW_API_KEY -- Bootstrap token for the Watcher daemon and")
    info("  auto-healing infrastructure. Keep this secret.")
    _safe_print("")

    if ask_bool("Auto-generate a secure API key?", default=True):
        api_key = generate_key("bc_")
        cfg["BUTTERCLAW_API_KEY"] = api_key
        ok(f"Generated: {green(bold(api_key))}")
    else:
        cfg["BUTTERCLAW_API_KEY"] = ask(
            "Custom API key", required=True, secret=True,
            validator=lambda v: "Minimum 16 characters recommended." if len(v) < 16 else None,
        )

    _safe_print("")
    info("ntfy push topic -- used by the Alert Dispatcher for native push")
    info("  notifications (phone / browser) with zero cloud telemetry.")
    tip("  Choose any secret string; share it with your ntfy subscriber.")
    cfg["BUTTERCLAW_ALERT_NTFY_TOPIC"] = ask(
        "ntfy topic name", default=f"butterclaw-{secrets.token_hex(6)}"
    )

    # ── 7 / 11 SAFETY / PARANOIA ─────────────────────────────────────────────
    section("  7 / 11  *  Safety & Paranoia Dial")
    info("DRY_RUN controls whether kinetic actions (SIGKILL, vault shred)")
    info("  are simulated or actually executed.")
    warn("Keep BOTH dry-run flags TRUE until you're confident in your setup.")
    _safe_print("")

    mcp_dry   = ask_bool("MCP dry run?   (blocks real TCP connections & syscalls)", default=True)
    chain_dry = ask_bool("Chain dry run? (simulates tool calls, brain still reasons)", default=True)
    loop_dry  = ask_bool("Loop dry run?  (simulates signature mutations)", default=True)
    cfg["BUTTERCLAW_MCP_DRY_RUN"]  = "true" if mcp_dry   else "false"
    cfg["BUTTERCLAW_DRY_RUN"]      = "true" if chain_dry else "false"
    cfg["BUTTERCLAW_LOOP_DRY_RUN"] = "true" if loop_dry  else "false"

    if not mcp_dry or not chain_dry:
        warn("One or both dry-run flags are OFF -- real kinetic actions will fire.")

    _safe_print("")
    info("Paranoia Dial -- how aggressively ButterClaw responds to threats:")
    tip("  Level 1 * Observe        -- Log threats only, no kinetic response")
    tip("  Level 2 * Active Defense -- SIGKILL compromised processes")
    tip("  Level 3 * Air-Gapped     -- SIGKILL + Shred vault + Revoke all tokens")
    _safe_print("")

    paranoia = ask_choice(
        "Select Paranoia level:",
        choices=[
            ("1", "1 -- Observe Mode        (safe for first run / testing)"),
            ("2", "2 -- Active Defense       (recommended for production)"),
            ("3", "3 -- Air-Gapped Lockdown  (maximum kinetic response)"),
        ],
        default="1" if (mcp_dry or chain_dry) else "2",
    )
    cfg["BUTTERCLAW_PARANOIA"] = paranoia

    if paranoia == "3" and (not mcp_dry or not chain_dry):
        warn("Level 3 with dry-run disabled: vault shred + token revocation WILL fire on threat.")

    _safe_print("")
    info("Fleet Sentinel dry-run (v0.9.0) -- controls whether COLLUDING verdicts")
    info("  from the Fleet Sentinel escalate to the Guardian Brain for kinetic action.")
    tip("  Keep TRUE until you have validated fleet verdicts against the sentinel log.")
    tip("  See docs/RUNBOOK.md for the recommended dry-run rollout procedure.")
    fleet_dry = ask_bool("Fleet Sentinel dry run?  (suppress multi-agent escalation)", default=True)
    cfg["FLEET_SENTINEL_DRY_RUN"] = "true" if fleet_dry else "false"
    if not fleet_dry:
        warn("Fleet Sentinel dry-run is OFF -- COLLUDING verdicts will escalate to Guardian Brain.")

    # ── 8 / 11 FLEET LAYER ───────────────────────────────────────────────────
    section("  8 / 11  *  Fleet Layer (v0.9.0)")
    info("Multi-agent awareness: correlation detection, trust graph, Fleet Sentinel hemisphere.")
    tip("  Defaults are safe for production. Skip unless you have specific scaling needs.")
    _safe_print("")

    if ask_bool("Configure fleet layer settings?", default=False):
        fleet_db_default = "/data/fleet.db" if deploy_mode == "docker" else "./fleet.db"
        cfg["BUTTERCLAW_FLEET_DB_PATH"] = ask(
            "Fleet DB path (separate from butterclaw.db, I-07-fleet)",
            default=fleet_db_default,
        )
        cfg["BUTTERCLAW_SENTINEL_INTERVAL_HOURS"] = ask(
            "Fleet Sentinel proactive sweep interval (hours)",
            default="4", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_SENTINEL_MIN_AGENTS"] = ask(
            "Min agents before Fleet Sentinel fires (INSUFFICIENT_DATA guard)",
            default="2", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_COLLUSION_WINDOW_SECONDS"] = ask(
            "Collusion role accumulation window (seconds)",
            default="180", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_CORRELATION_FLEET_THRESHOLD"] = ask(
            "Distinct agents for a CorrelationEvent (cross-agent same-pattern threshold)",
            default="3", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_TRUST_PROPAGATION_DEPTH"] = ask(
            "Taint propagation depth (1 or 2 hops)",
            default="1", validator=lambda v: "Must be 1 or 2" if v not in ("1", "2") else None,
        )
        cfg["BUTTERCLAW_REPUTATION_DECAY_RATIO"] = ask(
            "Reputation decay ratio (taint:recovery asymmetry, default 3.0)",
            default="3.0",
        )
        cfg["BUTTERCLAW_MAX_CONCURRENT_LLM"] = ask(
            "Max concurrent LLM hemisphere calls (Guardian Brain is exempt)",
            default="2", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD"] = ask(
            "Consecutive LLM errors before circuit breaker opens",
            default="3", validator=valid_positive_int,
        )
        cfg["BUTTERCLAW_CIRCUIT_BREAKER_RESET_SECONDS"] = ask(
            "Circuit breaker reset window (seconds)",
            default="60", validator=valid_positive_int,
        )
    else:
        cfg.setdefault("BUTTERCLAW_FLEET_DB_PATH", "/data/fleet.db" if deploy_mode == "docker" else "./fleet.db")
        cfg.setdefault("BUTTERCLAW_SENTINEL_INTERVAL_HOURS",         "4")
        cfg.setdefault("BUTTERCLAW_SENTINEL_MIN_AGENTS",             "2")
        cfg.setdefault("BUTTERCLAW_COLLUSION_WINDOW_SECONDS",        "180")
        cfg.setdefault("BUTTERCLAW_CORRELATION_FLEET_THRESHOLD",     "3")
        cfg.setdefault("BUTTERCLAW_TRUST_PROPAGATION_DEPTH",         "1")
        cfg.setdefault("BUTTERCLAW_REPUTATION_DECAY_RATIO",          "3.0")
        cfg.setdefault("BUTTERCLAW_MAX_CONCURRENT_LLM",              "2")
        cfg.setdefault("BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD",       "3")
        cfg.setdefault("BUTTERCLAW_CIRCUIT_BREAKER_RESET_SECONDS",   "60")

    # ── 9 / 11 R3 MEMORY WATCHDOG ────────────────────────────────────────────
    section("  9 / 11  *  Memory Watchdog (v0.9.2 R3)")
    info("Fallback maturation daemon that fires when dream_engine has been")
    info("  silent for longer than the configured threshold.")
    info("  Prevents memory activations from freezing if dream_engine stalls.")
    tip("  Defaults (enabled, 6h threshold, 5-min poll) are safe for production.")
    _safe_print("")

    watchdog_enabled = ask_bool("Enable memory maturation watchdog?", default=True)
    cfg["BUTTERCLAW_MEMORY_WATCHDOG_ENABLED"] = "true" if watchdog_enabled else "false"

    if watchdog_enabled:
        cfg["BUTTERCLAW_MEMORY_MATURATION_FALLBACK_HOURS"] = ask(
            "Fallback threshold (hours without a dream_engine tick before watchdog fires)",
            default="6.0",
            validator=valid_positive_float,
        )
        cfg["BUTTERCLAW_MEMORY_WATCHDOG_CHECK_INTERVAL_SEC"] = ask(
            "Watchdog poll cadence (seconds). Lower = faster shutdown response.",
            default="300",
            validator=valid_positive_float,
        )
    else:
        cfg.setdefault("BUTTERCLAW_MEMORY_MATURATION_FALLBACK_HOURS",   "6.0")
        cfg.setdefault("BUTTERCLAW_MEMORY_WATCHDOG_CHECK_INTERVAL_SEC", "300")
        warn("Memory watchdog disabled — dream_engine stalls will not trigger fallback maturation.")

    # ── 10 / 11 SKILLGUARD SUPPLY-CHAIN DEFENSE (v0.9.3) ─────────────────────
    section("  10 / 11  *  SkillGuard Supply-Chain (v0.9.3)")
    info("Static & runtime defense for SKILL.md agent packages (Gate M5 / M10).")
    info("  Inspects YAML frontmatter, references/, and scripts/ before activation,")
    info("  and enforces SHA-256 Merkle integrity on every MCP tool call.")
    _safe_print("")

    skill_root_default = "/data/skills" if deploy_mode == "docker" else "./skills"
    if ask_bool("Configure custom SkillGuard settings?", default=False):
        cfg["BUTTERCLAW_SKILL_ROOT"] = ask(
            "Allowed SKILL.md root directory (Gate M10 path containment)",
            default=skill_root_default,
        )
        cfg["BUTTERCLAW_SKILL_RISK_THRESHOLD"] = ask(
            "Quarantine risk score threshold (1-100, lower = stricter)",
            default="25",
            validator=valid_int_range(1, 100),
        )
        strict_toctou = ask_bool(
            "Enforce runtime Merkle anti-TOCTOU check on every MCP tool call (Gate M5)?",
            default=True,
        )
        cfg["BUTTERCLAW_SKILL_STRICT_TOCTOU"] = "true" if strict_toctou else "false"
    else:
        cfg.setdefault("BUTTERCLAW_SKILL_ROOT",           skill_root_default)
        cfg.setdefault("BUTTERCLAW_SKILL_RISK_THRESHOLD", "25")
        cfg.setdefault("BUTTERCLAW_SKILL_STRICT_TOCTOU",  "true")

    # ── 11 / 11 ADVANCED ─────────────────────────────────────────────────────
    section("  11 / 11  *  Advanced Settings")
    info("Sensible defaults are pre-filled. Skip unless you have specific needs.")
    _safe_print("")

    if ask_bool("Configure advanced settings?", default=False):
        _safe_print("")
        info("--- Server Extras ---")
        tip("  BASE_URL  -- externally reachable URL used for OAuth callbacks.")
        tip("  COOKIE_SECURE -- disable only when running plain HTTP locally.")
        _safe_print("")

        if deploy_mode == "baremetal":
            base_url_default = "http://127.0.0.1:5000"
        elif deploy_mode == "docker":
            base_url_default = "https://localhost"
        else:
            base_url_default = "https://butterclaw.yourdomain.com"
        cfg["BUTTERCLAW_BASE_URL"] = ask(
            "Base URL (externally reachable)", default=base_url_default, validator=valid_url
        )
        cookie_secure_default = deploy_mode != "baremetal"
        cfg["BUTTERCLAW_COOKIE_SECURE"] = (
            "true" if ask_bool(
                "Enable COOKIE_SECURE?  " + red("! disable only for plain-HTTP local dev"),
                default=cookie_secure_default,
            )
            else "false"
        )

        _safe_print("")
        info("--- MCP Transport ---")
        tip("  stdio = local child process (recommended)")
        tip("  sse   = remote SSE server   (distributed setups)")
        mcp_transport = ask_choice(
            "MCP transport:",
            choices=[("stdio", "stdio -- local child process"), ("sse", "sse -- remote SSE")],
            default="stdio",
        )
        cfg["BUTTERCLAW_MCP_TRANSPORT"] = mcp_transport

        if mcp_transport == "sse":
            cfg["BUTTERCLAW_MCP_SSE_URL"]   = ask("Remote MCP SSE URL",   required=True, validator=valid_url)
            cfg["BUTTERCLAW_MCP_SSE_TOKEN"] = ask("MCP SSE bearer token", required=True, secret=True)

        _safe_print("")
        info("--- MCP Script Path (stdio only) ---")
        tip("  Path to butterclaw_mcp.py -- leave blank to use the default.")
        mcp_script_raw = ask("MCP script path (blank = ./butterclaw_mcp.py)", default="")
        if mcp_script_raw:
            cfg["BUTTERCLAW_MCP_SCRIPT"] = mcp_script_raw

        _safe_print("")
        info("--- Authentication Rate Limits (requests / minute) ---")
        cfg["BUTTERCLAW_RATE_ADMIN"]          = ask("Admin rate limit",          default="30",   validator=valid_positive_int)
        cfg["BUTTERCLAW_RATE_OPERATOR"]       = ask("Operator rate limit",       default="15",   validator=valid_positive_int)
        cfg["BUTTERCLAW_RATE_VIEWER"]         = ask("Viewer rate limit",         default="5",    validator=valid_positive_int)
        cfg["BUTTERCLAW_RATE_INFRASTRUCTURE"] = ask("Infrastructure rate limit", default="1000", validator=valid_positive_int)

        _safe_print("")
        info("--- Session & OAuth TTLs ---")
        cfg["BUTTERCLAW_SESSION_TTL"] = ask("Session TTL (seconds)",           default="3600", validator=valid_positive_int)
        cfg["BUTTERCLAW_OAUTH_TTL"]   = ask("OAuth state token TTL (seconds)", default="600",  validator=valid_positive_int)

        _safe_print("")
        info("--- Alert Dispatcher ---")
        cfg["BUTTERCLAW_ALERT_TIMEOUT"] = ask("Alert HTTP timeout (seconds)", default="10", validator=valid_positive_int)
        cfg["BUTTERCLAW_ALERT_RETRIES"] = ask("Max alert retries",            default="3",  validator=valid_positive_int)
        cfg["BUTTERCLAW_ALERT_BACKOFF"] = ask("Retry base backoff (seconds)", default="1",  validator=valid_positive_int)

        _safe_print("")
        info("--- Auth Brute-force Detection ---")
        cfg["BUTTERCLAW_AUTH_FAIL_THRESHOLD"] = ask("Failure threshold (reqs before alert)", default="5",  validator=valid_positive_int)
        cfg["BUTTERCLAW_AUTH_FAIL_WINDOW"]    = ask("Sliding window (seconds)",              default="60", validator=valid_positive_int)

        _safe_print("")
        info("--- Dual Memory Engine ---")
        cfg["BUTTERCLAW_LIVE_CRYSTALLIZATION_ENABLED"] = "true" if ask_bool("Enable Live Signature Crystallization (3-strike rule)?", default=True) else "false"
        cfg["BUTTERCLAW_ATTRACTOR_DECAY_DAYS"] = ask("Cold Memory Attractor Decay (days)", default="30", validator=valid_positive_int)

        _safe_print("")
        info("--- Confidence Threshold ---")
        tip("  0-100. Below this, CRITICAL verdicts are downgraded to WARNING.")
        cfg["BUTTERCLAW_CONFIDENCE_THRESHOLD"] = ask("Confidence threshold", default="85", validator=valid_int_range(0, 100))

    else:
        if deploy_mode == "baremetal":
            base_url_default = "http://127.0.0.1:5000"
        elif deploy_mode == "docker":
            base_url_default = "https://localhost"
        else:
            base_url_default = "https://butterclaw.yourdomain.com"
        cfg.setdefault("BUTTERCLAW_BASE_URL",               base_url_default)
        cfg.setdefault("BUTTERCLAW_COOKIE_SECURE",          "true" if deploy_mode != "baremetal" else "false")
        cfg.setdefault("BUTTERCLAW_MCP_TRANSPORT",          "stdio")
        cfg.setdefault("BUTTERCLAW_RATE_ADMIN",             "30")
        cfg.setdefault("BUTTERCLAW_RATE_OPERATOR",          "15")
        cfg.setdefault("BUTTERCLAW_RATE_VIEWER",            "5")
        cfg.setdefault("BUTTERCLAW_RATE_INFRASTRUCTURE",    "1000")
        cfg.setdefault("BUTTERCLAW_SESSION_TTL",            "3600")
        cfg.setdefault("BUTTERCLAW_OAUTH_TTL",              "600")
        cfg.setdefault("BUTTERCLAW_ALERT_TIMEOUT",          "10")
        cfg.setdefault("BUTTERCLAW_ALERT_RETRIES",          "3")
        cfg.setdefault("BUTTERCLAW_ALERT_BACKOFF",          "1")
        cfg.setdefault("BUTTERCLAW_AUTH_FAIL_THRESHOLD",    "5")
        cfg.setdefault("BUTTERCLAW_AUTH_FAIL_WINDOW",       "60")
        cfg.setdefault("BUTTERCLAW_CONFIDENCE_THRESHOLD",   "85")
        cfg.setdefault("BUTTERCLAW_LOOP_DRY_RUN",           "true")
        cfg.setdefault("BUTTERCLAW_LIVE_CRYSTALLIZATION_ENABLED", "true")
        cfg.setdefault("BUTTERCLAW_ATTRACTOR_DECAY_DAYS",   "30")

    # Fast-path guards
    cfg.setdefault("FLEET_SENTINEL_DRY_RUN",                     "true")
    cfg.setdefault("BUTTERCLAW_FLEET_DB_PATH",                   "/data/fleet.db" if deploy_mode == "docker" else "./fleet.db")
    cfg.setdefault("BUTTERCLAW_SENTINEL_INTERVAL_HOURS",         "4")
    cfg.setdefault("BUTTERCLAW_SENTINEL_MIN_AGENTS",             "2")
    cfg.setdefault("BUTTERCLAW_COLLUSION_WINDOW_SECONDS",        "180")
    cfg.setdefault("BUTTERCLAW_CORRELATION_FLEET_THRESHOLD",     "3")
    cfg.setdefault("BUTTERCLAW_TRUST_PROPAGATION_DEPTH",         "1")
    cfg.setdefault("BUTTERCLAW_REPUTATION_DECAY_RATIO",          "3.0")
    cfg.setdefault("BUTTERCLAW_MAX_CONCURRENT_LLM",              "2")
    cfg.setdefault("BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD",       "3")
    cfg.setdefault("BUTTERCLAW_CIRCUIT_BREAKER_RESET_SECONDS",   "60")
    cfg.setdefault("BUTTERCLAW_MEMORY_WATCHDOG_ENABLED",            "true")
    cfg.setdefault("BUTTERCLAW_MEMORY_MATURATION_FALLBACK_HOURS",   "6.0")
    cfg.setdefault("BUTTERCLAW_MEMORY_WATCHDOG_CHECK_INTERVAL_SEC", "300")
    cfg.setdefault("BUTTERCLAW_SKILL_ROOT",                      "/data/skills" if deploy_mode == "docker" else "./skills")
    cfg.setdefault("BUTTERCLAW_SKILL_RISK_THRESHOLD",            "25")
    cfg.setdefault("BUTTERCLAW_SKILL_STRICT_TOCTOU",             "true")

    cfg["PYTHONUNBUFFERED"] = "1"
    return cfg


# ---------------------------------------------------------------------------
# .env renderer
# ---------------------------------------------------------------------------

def render_env(cfg: dict) -> str:
    # Fix #3: use .get() not .pop() -- avoids mutating the dict in-place
    brain_mode  = cfg.get("_brain_mode",  "local")
    deploy_mode = cfg.get("_deploy_mode", "baremetal")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# =============================================",
        f"# ButterClaw v0.9.3 -- Environment Configuration",
        f"# Generated by setup_wizard.py on {now}",
        f"# Deploy mode : {deploy_mode}",
        f"# Brain mode  : {brain_mode}",
        f"# =============================================",
        f"",
        f"# --- Instance Identity ---",
        f"BUTTERCLAW_INSTANCE_ID={cfg.get('BUTTERCLAW_INSTANCE_ID', 'butterclaw-prod')}",
        f"",
        f"# --- Server ---",
        f"BUTTERCLAW_HOST={cfg.get('BUTTERCLAW_HOST', '0.0.0.0')}",
        f"BUTTERCLAW_PORT={cfg.get('BUTTERCLAW_PORT', '5000')}",
        f"BUTTERCLAW_DEBUG={cfg.get('BUTTERCLAW_DEBUG', 'false')}",
        f"BUTTERCLAW_BASE_URL={cfg.get('BUTTERCLAW_BASE_URL', 'http://127.0.0.1:5000')}",
        f"BUTTERCLAW_COOKIE_SECURE={cfg.get('BUTTERCLAW_COOKIE_SECURE', 'true')}",
        f"",
        f"# --- Database ---",
        f"BUTTERCLAW_DB_PATH={cfg.get('BUTTERCLAW_DB_PATH', './butterclaw.db')}",
        f"",
        f"# --- Fleet Layer (v0.9.0) ---",
        f"BUTTERCLAW_FLEET_DB_PATH={cfg.get('BUTTERCLAW_FLEET_DB_PATH', '/data/fleet.db')}",
        f"# Fleet Sentinel dry-run: true = log verdicts only, no kinetic escalation",
        f"FLEET_SENTINEL_DRY_RUN={cfg.get('FLEET_SENTINEL_DRY_RUN', 'true')}",
        f"BUTTERCLAW_SENTINEL_INTERVAL_HOURS={cfg.get('BUTTERCLAW_SENTINEL_INTERVAL_HOURS', '4')}",
        f"BUTTERCLAW_SENTINEL_MIN_AGENTS={cfg.get('BUTTERCLAW_SENTINEL_MIN_AGENTS', '2')}",
        f"BUTTERCLAW_COLLUSION_WINDOW_SECONDS={cfg.get('BUTTERCLAW_COLLUSION_WINDOW_SECONDS', '180')}",
        f"BUTTERCLAW_CORRELATION_FLEET_THRESHOLD={cfg.get('BUTTERCLAW_CORRELATION_FLEET_THRESHOLD', '3')}",
        f"BUTTERCLAW_TRUST_PROPAGATION_DEPTH={cfg.get('BUTTERCLAW_TRUST_PROPAGATION_DEPTH', '1')}",
        f"BUTTERCLAW_REPUTATION_DECAY_RATIO={cfg.get('BUTTERCLAW_REPUTATION_DECAY_RATIO', '3.0')}",
        f"BUTTERCLAW_MAX_CONCURRENT_LLM={cfg.get('BUTTERCLAW_MAX_CONCURRENT_LLM', '2')}",
        f"BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD={cfg.get('BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD', '3')}",
        f"BUTTERCLAW_CIRCUIT_BREAKER_RESET_SECONDS={cfg.get('BUTTERCLAW_CIRCUIT_BREAKER_RESET_SECONDS', '60')}",
        f"",
    ]

    if "BUTTERCLAW_CORS_ORIGINS" in cfg:
        lines += [
            f"# --- CORS ---",
            f"BUTTERCLAW_CORS_ORIGINS={cfg['BUTTERCLAW_CORS_ORIGINS']}",
            f"",
        ]
    else:
        lines += [
            f"# --- CORS ---",
            f"# BUTTERCLAW_CORS_ORIGINS=  # using localhost defaults",
            f"",
        ]

    lines += [
        f"# --- Brain / Ollama ---",
        f"BUTTERCLAW_OLLAMA_URL={cfg.get('BUTTERCLAW_OLLAMA_URL', 'http://localhost:11434')}",
        f"BUTTERCLAW_OLLAMA_PATH={cfg.get('BUTTERCLAW_OLLAMA_PATH', '/api/chat')}",
        f"BUTTERCLAW_MODEL={cfg.get('BUTTERCLAW_MODEL', 'butterclaw-optimized:latest')}",
        f"",
    ]

    if "BUTTERCLAW_GOOGLE_API_KEY" in cfg and cfg["BUTTERCLAW_GOOGLE_API_KEY"]:
        lines += [
            f"# --- Remote Brain (Google Gemini) ---",
            f"BUTTERCLAW_GOOGLE_API_KEY={cfg['BUTTERCLAW_GOOGLE_API_KEY']}",
            f"",
        ]
    else:
        lines += [
            f"# --- Remote Brain (Google Gemini) ---",
            f"# BUTTERCLAW_GOOGLE_API_KEY=  # not configured",
            f"",
        ]

    lines += [
        f"# --- API Keys ---",
        f"BUTTERCLAW_API_KEY={cfg.get('BUTTERCLAW_API_KEY', '')}",
        f"BUTTERCLAW_ALERT_NTFY_TOPIC={cfg.get('BUTTERCLAW_ALERT_NTFY_TOPIC', '')}",
        f"",
        f"# --- Confidence & Safety ---",
        f"BUTTERCLAW_CONFIDENCE_THRESHOLD={cfg.get('BUTTERCLAW_CONFIDENCE_THRESHOLD', '85')}",
        f"BUTTERCLAW_MCP_DRY_RUN={cfg.get('BUTTERCLAW_MCP_DRY_RUN', 'true')}",
        f"BUTTERCLAW_DRY_RUN={cfg.get('BUTTERCLAW_DRY_RUN', 'true')}",
        f"",
        f"BUTTERCLAW_LOOP_DRY_RUN={cfg.get('BUTTERCLAW_LOOP_DRY_RUN', 'true')}",
        f"",
        f"# --- Dual Memory Engine ---",
        f"BUTTERCLAW_LIVE_CRYSTALLIZATION_ENABLED={cfg.get('BUTTERCLAW_LIVE_CRYSTALLIZATION_ENABLED', 'true')}",
        f"BUTTERCLAW_ATTRACTOR_DECAY_DAYS={cfg.get('BUTTERCLAW_ATTRACTOR_DECAY_DAYS', '30')}",
        f"",
        f"# --- Paranoia Dial ---",
        f"# 1=Observe  2=Active Defense  3=Air-Gapped Lockdown",
        f"BUTTERCLAW_PARANOIA={cfg.get('BUTTERCLAW_PARANOIA', '2')}",
        f"",
        f"# --- MCP Transport ---",
        f"BUTTERCLAW_MCP_TRANSPORT={cfg.get('BUTTERCLAW_MCP_TRANSPORT', 'stdio')}",
    ]

    if cfg.get("BUTTERCLAW_MCP_SSE_URL"):
        lines += [
            f"BUTTERCLAW_MCP_SSE_URL={cfg['BUTTERCLAW_MCP_SSE_URL']}",
            f"BUTTERCLAW_MCP_SSE_TOKEN={cfg.get('BUTTERCLAW_MCP_SSE_TOKEN', '')}",
        ]

    if cfg.get("BUTTERCLAW_MCP_SCRIPT"):
        lines += [f"BUTTERCLAW_MCP_SCRIPT={cfg['BUTTERCLAW_MCP_SCRIPT']}"]
    else:
        lines += [f"# BUTTERCLAW_MCP_SCRIPT=  # dynamically resolved in src/ layout"]

    lines += [
        f"",
        f"# --- Authentication ---",
        f"BUTTERCLAW_RATE_ADMIN={cfg.get('BUTTERCLAW_RATE_ADMIN', '30')}",
        f"BUTTERCLAW_RATE_OPERATOR={cfg.get('BUTTERCLAW_RATE_OPERATOR', '15')}",
        f"BUTTERCLAW_RATE_VIEWER={cfg.get('BUTTERCLAW_RATE_VIEWER', '5')}",
        f"BUTTERCLAW_RATE_INFRASTRUCTURE={cfg.get('BUTTERCLAW_RATE_INFRASTRUCTURE', '1000')}",
        f"BUTTERCLAW_SESSION_TTL={cfg.get('BUTTERCLAW_SESSION_TTL', '3600')}",
        f"BUTTERCLAW_OAUTH_TTL={cfg.get('BUTTERCLAW_OAUTH_TTL', '600')}",
        f"",
        f"# --- Alert Dispatcher ---",
        f"BUTTERCLAW_ALERT_TIMEOUT={cfg.get('BUTTERCLAW_ALERT_TIMEOUT', '10')}",
        f"BUTTERCLAW_ALERT_RETRIES={cfg.get('BUTTERCLAW_ALERT_RETRIES', '3')}",
        f"BUTTERCLAW_ALERT_BACKOFF={cfg.get('BUTTERCLAW_ALERT_BACKOFF', '1')}",
        f"BUTTERCLAW_AUTH_FAIL_THRESHOLD={cfg.get('BUTTERCLAW_AUTH_FAIL_THRESHOLD', '5')}",
        f"BUTTERCLAW_AUTH_FAIL_WINDOW={cfg.get('BUTTERCLAW_AUTH_FAIL_WINDOW', '60')}",
        f"",
        f"# --- Memory Watchdog (v0.9.2 R3) ---",
        f"# Fallback daemon: fires when dream_engine silent > FALLBACK_HOURS.",
        f"BUTTERCLAW_MEMORY_WATCHDOG_ENABLED={cfg.get('BUTTERCLAW_MEMORY_WATCHDOG_ENABLED', 'true')}",
        f"BUTTERCLAW_MEMORY_MATURATION_FALLBACK_HOURS={cfg.get('BUTTERCLAW_MEMORY_MATURATION_FALLBACK_HOURS', '6.0')}",
        f"BUTTERCLAW_MEMORY_WATCHDOG_CHECK_INTERVAL_SEC={cfg.get('BUTTERCLAW_MEMORY_WATCHDOG_CHECK_INTERVAL_SEC', '300')}",
        f"",
        f"# --- SkillGuard Supply-Chain Defense (v0.9.3 Gate M5/M10) ---",
        f"BUTTERCLAW_SKILL_ROOT={cfg.get('BUTTERCLAW_SKILL_ROOT', './skills')}",
        f"BUTTERCLAW_SKILL_RISK_THRESHOLD={cfg.get('BUTTERCLAW_SKILL_RISK_THRESHOLD', '25')}",
        f"BUTTERCLAW_SKILL_STRICT_TOCTOU={cfg.get('BUTTERCLAW_SKILL_STRICT_TOCTOU', 'true')}",
        f"",
        f"# --- Docker / Python ---",
        f"PYTHONUNBUFFERED=1",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def print_preview(env_text: str):
    _safe_print("")
    _safe_print(bold(cyan("  -- Generated .env preview --")))
    for line in env_text.splitlines():
        if line.startswith("#"):
            _safe_print(dim(f"  {line}"))
        elif "KEY" in line or "TOKEN" in line or "PASSWORD" in line:
            key, _, val = line.partition("=")
            masked = val[:4] + "*" * max(0, len(val) - 4) if val and not val.startswith("#") else val
            _safe_print(f"  {cyan(key)}={yellow(masked)}")
        elif "=" in line:
            key, _, val = line.partition("=")
            _safe_print(f"  {cyan(key)}={green(val)}")
        elif not line:
            _safe_print("")
        else:
            _safe_print(f"  {line}")
    _safe_print(bold(cyan("  ------------------------------------------------")))


# ---------------------------------------------------------------------------
# Next steps
# ---------------------------------------------------------------------------

def print_next_steps(cfg_snapshot: dict, output_path: str):
    _safe_print("")
    _safe_print(bold(cyan("  What's next?")))
    _safe_print("")

    brain_mode = cfg_snapshot.get("_brain_mode_snapshot", "local")
    deploy     = cfg_snapshot.get("_deploy_mode_snapshot", "docker")
    # Fix #4: check both flags -- either flag in dry-run means kinetic actions are suppressed
    dry_run_on = (
        cfg_snapshot.get("BUTTERCLAW_MCP_DRY_RUN") == "true"
        or cfg_snapshot.get("BUTTERCLAW_DRY_RUN") == "true"
    )

    step = 1

    if brain_mode == "local":
        _safe_print(f"  {bold(str(step)+'.')} Pull and build the Ollama model:")
        _safe_print(f"       {dim('ollama pull gemma4:e4b')}")
        _safe_print(f"       {dim('ollama create butterclaw-optimized -f Modelfile.example')}")
        step += 1

    if deploy == "docker":
        _safe_print(f"  {bold(str(step)+'.')} Generate local TLS certificates for nginx:")
        _safe_print(f"       {dim('mkdir -p nginx/certs')}")
        _safe_print("       " + dim('docker run --rm -v "${PWD}/nginx/certs:/certs" alpine/openssl req -x509 -nodes \\'))
        _safe_print("       " + dim('  -days 365 -newkey rsa:2048 -keyout /certs/butterclaw.key -out /certs/butterclaw.crt -subj "/CN=localhost"'))
        step += 1

        _safe_print(f"  {bold(str(step)+'.')} Ignite the stack:")
        _safe_print(f"       {dim('docker compose up -d --build')}")
        step += 1

        _safe_print(f"  {bold(str(step)+'.')} Your {yellow('bootstrap admin API key')} is safely stored in your .env file.")
        _safe_print(f"       {dim('Keep it secret. Keep it safe.')}")
        step += 1

        _safe_print(f"  {bold(str(step)+'.')} Verify the stack is healthy:")
        _safe_print(f"       {dim('docker compose ps')}")
        _safe_print(f"       {dim('curl -k https://localhost/api/health   # via nginx')}")
        _safe_print(f"       {dim('# Dashboard -> https://localhost  |  ntfy UI -> http://localhost:2586')}")
        step += 1

    elif deploy == "baremetal":
        _safe_print(f"  {bold(str(step)+'.')} Install Python dependencies:")
        _safe_print(f"       {dim('pip install -r requirements.txt')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Start the server:")
        _safe_print(f"       {dim('python -m butterclaw.server')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Your {yellow('bootstrap admin API key')} is safely stored in your .env file.")
        _safe_print(f"       {dim('Keep it secret. Keep it safe.')}")
        step += 1

    elif deploy == "systemd":
        _safe_print(f"  {bold(str(step)+'.')} Copy your .env to the systemd environment file:")
        _safe_print(f"       {dim('sudo cp .env /etc/butterclaw.env')}")
        _safe_print(f"       {dim('sudo chmod 600 /etc/butterclaw.env')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Install and start the service:")
        _safe_print(f"       {dim('sudo cp systemd/butterclaw.service /etc/systemd/system/')}")
        _safe_print(f"       {dim('sudo systemctl daemon-reload')}")
        _safe_print(f"       {dim('sudo systemctl enable --now butterclaw')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Your {yellow('bootstrap admin API key')} is safely stored in your .env file.")
        _safe_print(f"       {dim('Keep it secret. Keep it safe.')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Verify the service is running:")
        _safe_print(f"       {dim('sudo systemctl status butterclaw')}")
        _safe_print(f"       {dim('curl http://localhost:5000/api/health')}")
        step += 1

    if dry_run_on:
        _safe_print(f"  {bold(str(step)+'.')} {yellow('Test safely')} -- dry-run is ON, no kinetic actions will fire:")
        _safe_print(f"       {dim('python scripts/test_attack.py')}")
        _safe_print(f"       {dim('python tests/test_skill_guard.py')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Audit & attest SKILL.md packages before agent use:")
        _safe_print(f"       {dim('python setup_wizard.py --audit-skill ./skills/<skill-folder>')}")
        _safe_print(f"       {dim('python setup_wizard.py --list-skills')}")
        step += 1
        _safe_print(f"  {bold(str(step)+'.')} Ready for production? Flip the switches in your .env:")
        _safe_print(f"       {dim('BUTTERCLAW_DRY_RUN=false')}")
        _safe_print(f"       {dim('BUTTERCLAW_MCP_DRY_RUN=false')}")
        _safe_print(f"       {dim('FLEET_SENTINEL_DRY_RUN=false  # only after validating sentinel-log per RUNBOOK')}")
        step += 1
    else:
        _safe_print(f"  {bold(str(step)+'.')} {red('Dry-run is OFF')} -- kinetic actions execute for real.")
        _safe_print(f"       Run the live-fire diagnostic: {dim('python scripts/test_attack.py')}")
        step += 1

    # Fix #5: platform-aware dashboard launcher
    dash_cmd = "dash.bat" if sys.platform == "win32" else "./dash.sh"
    _safe_print(f"  {bold(str(step)+'.')} Launch the TUI dashboard (or check SkillGuard status):")
    _safe_print(f"       {dim(dash_cmd)}")
    _safe_print(f"       {dim(f'{dash_cmd} skills')}")
    _safe_print("")
    _safe_print(dim(f"  .env written to: {os.path.abspath(output_path)}"))
    _safe_print(dim(f"  Full deployment guide: docs/DEPLOYMENT.md"))
    _safe_print(dim(f"  Docs & API: https://github.com/butterclaw-tech/butterclaw"))
    _safe_print("")
    _safe_print(green(bold("  * Setup complete. Good hunting, operator.")))
    _safe_print("")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    _configure_stdout_encoding()  # Fix #7: upgrade Windows stdout to UTF-8 before any print
    parser = argparse.ArgumentParser(
        description="ButterClaw interactive setup wizard & SkillGuard CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python setup_wizard.py                              # write .env interactively
              python setup_wizard.py -o /etc/butterclaw.env
              python setup_wizard.py --no-backup                  # overwrite existing .env silently
              python setup_wizard.py --audit-skill ./skills/foo   # pre-flight scan & Merkle-lock a skill
              python setup_wizard.py --list-skills                # list all attested skills in SQLite
        """),
    )
    parser.add_argument("--output", "-o", default=".env",
                        help="Destination path for the generated .env (default: .env)")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip backup of an existing .env before overwriting")
    parser.add_argument("--audit-skill", metavar="SKILL_DIR", default=None,
                        help="Run SkillGuard static & Merkle attestation on a SKILL.md folder and exit")
    parser.add_argument("--list-skills", action="store_true",
                        help="Display all attested SKILL.md packages stored in SQLite and exit")
    parser.add_argument("--db", metavar="DB_PATH", default=None,
                        help="Optional SQLite DB path override for --audit-skill / --list-skills")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with code 2 when --audit-skill verdicts QUARANTINED (for CI/CD)")
    args = parser.parse_args()

    # Handle direct SkillGuard CLI modes before interactive wizard
    if args.audit_skill:
        sys.exit(cli_audit_skill(args.audit_skill, db_path=args.db, strict=args.strict))
    if args.list_skills:
        sys.exit(cli_list_skills(db_path=args.db))

    output_path = args.output

    print_banner()

    if os.path.exists(output_path) and not args.no_backup:
        backup = output_path + ".backup"
        shutil.copy2(output_path, backup)
        warn(f"Existing {output_path} backed up -> {backup}")
        _safe_print("")

    cfg = run_wizard()

    brain_mode  = cfg.get("_brain_mode",  "local")
    deploy_mode = cfg.get("_deploy_mode", "docker")

    env_text = render_env(cfg)
    print_preview(env_text)
    _safe_print("")

    if not ask_bool("Write this .env file?", default=True):
        warn("Aborted. No file was written.")
        sys.exit(0)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(env_text)

    # Fix #6: restrict .env to owner-only on POSIX -- it contains secrets
    if sys.platform != "win32":
        try:
            os.chmod(output_path, 0o600)
        except OSError:
            pass

    ok(f"Written to {bold(output_path)}")

    # Ensure openclaw_gateway.log and ./skills directory exist for Docker volume mounts
    if deploy_mode == "docker":
        log_path = Path("openclaw_gateway.log")
        if not log_path.exists():
            log_path.touch()
            ok(f"Created blank {bold('openclaw_gateway.log')} for Docker volume mount")
    skills_dir = Path("skills")
    if not skills_dir.exists():
        skills_dir.mkdir(parents=True, exist_ok=True)
        ok(f"Created local {bold('skills/')} directory for SkillGuard packages")

    cfg["_brain_mode_snapshot"]  = brain_mode
    cfg["_deploy_mode_snapshot"] = deploy_mode
    print_next_steps(cfg, output_path)


if __name__ == "__main__":
    main()
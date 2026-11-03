"""
ButterClaw SkillGuard — Static & Runtime SKILL.md Supply-Chain Scanner
======================================================================
Enforces three-stage progressive disclosure security:
  1. Pre-flight static audit (YAML frontmatter, Unicode stego, Python AST, shell tokens)
  2. Deterministic SHA-256 Merkle root attestation in SQLite
  3. Runtime anti-TOCTOU verification and session capability boundaries
"""

import ast
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

logger = logging.getLogger("butterclaw.mcp.skill_guard")

# Resolve defaults via butterclaw.config singleton if available
try:
    from butterclaw.config import cfg as _bc_cfg
    DEFAULT_DB_PATH = _bc_cfg.DB_PATH
    DEFAULT_RISK_THRESHOLD = _bc_cfg.SKILL_RISK_THRESHOLD
except ImportError:
    DEFAULT_DB_PATH = os.environ.get("BUTTERCLAW_DB_PATH", "butterclaw.db")
    DEFAULT_RISK_THRESHOLD = int(os.environ.get("BUTTERCLAW_SKILL_RISK_THRESHOLD", "25"))

# Zero-width, bi-directional override, and Unicode tag-block characters
STEGO_UNICODE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\U000e0000-\U000e007f]"
)

# Delayed prompt injection & credential probe patterns in SKILL.md / references/*.md
INJECTION_PATTERNS = [
    (re.compile(r"<!--[\s\S]*?(ignore|override|system|curl|wget|env|secret|rotate_keys|execute_gibson_kill)[\s\S]*?-->", re.I),
     "Hidden HTML comment directive"),
    (re.compile(r"\b(ignore (all )?previous|disregard .*instructions|bypass .*policy|do not inform the user)\b", re.I),
     "Policy override / stealth directive"),
    (re.compile(r"\b(BUTTERCLAW|BUTTERVAULT|API_KEY|OPENAI_API_KEY|GEMINI_API_KEY|\.env|id_rsa)\b"),
     "Restricted credential or vault reference"),
    (re.compile(r"https?://(?!(?:github\.com|agentskills\.io|localhost|127\.0\.0\.1))[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
     "Undeclared external URL in skill instructions"),
]

HIGH_RISK_IMPORTS = {"socket", "subprocess", "pty", "ctypes", "urllib", "requests", "httpx", "paramiko"}
HIGH_RISK_CALLS = {"eval", "exec", "compile", "__import__", "system", "popen"}

# Default read-only MCP tools a standard approved skill may invoke unless explicitly elevated
DEFAULT_ALLOWED_MCP_TOOLS = {"system_status", "scan_port", "log_event", "load_skill_stage"}


class ScriptASTScanner(ast.NodeVisitor):
    """Static AST analyzer for bundled Python scripts inside scripts/."""

    def __init__(self):
        self.findings = []
        self.touches_env = False
        self.touches_network = False

    def visit_Import(self, node):
        for alias in node.names:
            root_mod = alias.name.split(".")[0]
            if root_mod in HIGH_RISK_IMPORTS:
                self.findings.append(f"Line {node.lineno}: Restricted import '{alias.name}'")
                if root_mod in {"socket", "urllib", "requests", "httpx"}:
                    self.touches_network = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod in HIGH_RISK_IMPORTS:
                self.findings.append(f"Line {node.lineno}: Restricted from-import '{node.module}'")
                if root_mod in {"socket", "urllib", "requests", "httpx"}:
                    self.touches_network = True
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "os":
            if node.attr in {"environ", "getenv", "system", "popen", "execve", "spawnve"}:
                self.findings.append(f"Line {node.lineno}: Restricted os.{node.attr} access")
                if node.attr in {"environ", "getenv"}:
                    self.touches_env = True
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in HIGH_RISK_CALLS:
            self.findings.append(f"Line {node.lineno}: Dynamic code execution '{node.func.id}()'")
        self.generic_visit(node)


class SkillGuard:
    """Pre-flight scanner, SQLite Merkle store, and runtime verifier for SKILL.md folders."""

    def __init__(self, db_path=None, allowed_root=None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        env_root = os.environ.get("BUTTERCLAW_SKILL_ROOT")
        self.allowed_root = Path(allowed_root or env_root).resolve() if (allowed_root or env_root) else None
        self.risk_threshold = DEFAULT_RISK_THRESHOLD
        self._init_db()

    def _init_db(self):
        """Ensures the skill_attestations table exists in SQLite and closes handle immediately."""
        try:
            parent = Path(self.db_path).parent
            if str(parent) and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS skill_attestations (
                        skill_name TEXT PRIMARY KEY,
                        package_path TEXT NOT NULL,
                        merkle_root TEXT NOT NULL,
                        file_hashes_json TEXT NOT NULL,
                        declared_description TEXT NOT NULL,
                        allowed_tools_json TEXT NOT NULL,
                        allow_network INTEGER DEFAULT 0,
                        allow_env_access INTEGER DEFAULT 0,
                        risk_score INTEGER NOT NULL,
                        findings_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attested_at TEXT NOT NULL
                    )
                """)
        except Exception as e:
            logger.error(f"⚠️ [SkillGuard] SQLite init warning ({self.db_path}): {e}")

    def _resolve_safe_dir(self, skill_dir_str):
        """[M10] Resolves path and enforces directory traversal containment (Windows/POSIX safe)."""
        target = Path(skill_dir_str).resolve()
        if self.allowed_root:
            try:
                common = Path(os.path.commonpath([str(self.allowed_root), str(target)]))
                if common != self.allowed_root:
                    raise PermissionError(
                        f"Skill path '{target}' is outside allowed root '{self.allowed_root}'."
                    )
            except ValueError:
                raise PermissionError(
                    f"Skill path '{target}' is on a different drive than '{self.allowed_root}'."
                )
        if not target.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {target}")
        return target

    @staticmethod
    def parse_frontmatter(md_text):
        """Extracts YAML frontmatter keys safely without executing YAML tags."""
        if not md_text.startswith("---"):
            return {}, md_text
        parts = md_text.split("---", 2)
        if len(parts) < 3:
            return {}, md_text
        raw_yaml, body = parts[1].strip(), parts[2].strip()
        meta = {}
        for line in raw_yaml.splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip("'\"")
        return meta, body

    @staticmethod
    def compute_package_hashes(skill_dir):
        """Computes per-file SHA-256 digests and a deterministic package Merkle root."""
        file_hashes = {}
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                rel_path = path.relative_to(skill_dir).as_posix()
                file_hashes[rel_path] = hashlib.sha256(path.read_bytes()).hexdigest()
        combined = "".join(f"{k}:{v}" for k, v in sorted(file_hashes.items()))
        merkle_root = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return merkle_root, file_hashes

    def _scan_markdown(self, rel_path, content):
        findings = []
        if STEGO_UNICODE_RE.search(content):
            findings.append(f"[{rel_path}] Hidden zero-width or tag-block Unicode detected")
        for pattern, label in INJECTION_PATTERNS:
            if pattern.search(content):
                findings.append(f"[{rel_path}] {label}")
        return findings

    def _scan_script(self, rel_path, full_path):
        content = full_path.read_text(encoding="utf-8", errors="replace")
        if full_path.suffix == ".py":
            try:
                tree = ast.parse(content, filename=rel_path)
                scanner = ScriptASTScanner()
                scanner.visit(tree)
                return (
                    [f"[{rel_path}] {f}" for f in scanner.findings],
                    scanner.touches_network,
                    scanner.touches_env,
                )
            except SyntaxError as e:
                return [f"[{rel_path}] Unparseable Python syntax at line {e.lineno}"], False, False

        findings = []
        touches_net = bool(re.search(r"\b(curl|wget|nc|netcat|ssh|scp|/dev/tcp)\b", content))
        touches_env = bool(re.search(r"(\benv\b|\bprintenv\b|\$\{?[A-Z0-9_]*KEY|\bcat\s+.*\.env)", content))
        if touches_net:
            findings.append(f"[{rel_path}] Shell script invokes network utility")
        if touches_env:
            findings.append(f"[{rel_path}] Shell script probes environment/secret variables")
        return findings, touches_net, touches_env

    def audit_and_attest(self, skill_dir_str):
        """Scans a SKILL.md directory and persists its Merkle attestation to SQLite."""
        skill_dir = self._resolve_safe_dir(skill_dir_str)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            raise FileNotFoundError(f"Missing required SKILL.md in {skill_dir}")

        merkle_root, file_hashes = self.compute_package_hashes(skill_dir)
        raw_md = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter, _ = self.parse_frontmatter(raw_md)

        findings = []
        touches_net = False
        touches_env = False

        if "name" not in frontmatter or "description" not in frontmatter:
            findings.append("[SKILL.md] Missing required YAML frontmatter ('name' or 'description')")
        findings.extend(self._scan_markdown("SKILL.md", raw_md))

        for rel_path in file_hashes:
            if rel_path == "SKILL.md":
                continue
            full_path = skill_dir / rel_path
            if full_path.suffix in {".md", ".txt", ".json", ".yaml", ".yml"}:
                findings.extend(
                    self._scan_markdown(rel_path, full_path.read_text(encoding="utf-8", errors="replace"))
                )
            elif full_path.suffix in {".py", ".sh", ".bash", ".js"} or rel_path.startswith("scripts/"):
                s_findings, net, env = self._scan_script(rel_path, full_path)
                findings.extend(s_findings)
                touches_net = touches_net or net
                touches_env = touches_env or env

        risk_score = min(100, len(findings) * 25 + (35 if touches_env else 0) + (20 if touches_net else 0))
        status = "QUARANTINED" if risk_score >= self.risk_threshold else "APPROVED"
        skill_name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        allowed_tools = sorted(DEFAULT_ALLOWED_MCP_TOOLS)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        record = {
            "skill_name": skill_name,
            "package_path": str(skill_dir),
            "merkle_root": merkle_root,
            "file_hashes": file_hashes,
            "declared_description": description,
            "allowed_mcp_tools": allowed_tools,
            "touches_network": touches_net,
            "touches_env": touches_env,
            "risk_score": risk_score,
            "findings": findings,
            "status": status,
            "attested_at": timestamp,
        }

        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                INSERT OR REPLACE INTO skill_attestations (
                    skill_name, package_path, merkle_root, file_hashes_json,
                    declared_description, allowed_tools_json, allow_network,
                    allow_env_access, risk_score, findings_json, status, attested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                skill_name, str(skill_dir), merkle_root, json.dumps(file_hashes),
                description, json.dumps(allowed_tools), int(touches_net),
                int(touches_env), risk_score, json.dumps(findings), status, timestamp
            ))

        logger.info(f"🛡️ [SkillGuard] Audited '{skill_name}': status={status}, risk={risk_score}, merkle={merkle_root[:12]}...")
        return record

    def get_attestation(self, skill_name):
        """Fetches stored attestation record for a skill from SQLite and closes handle."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM skill_attestations WHERE skill_name = ?", (skill_name,)
            ).fetchone()
            if not row:
                return None
            return {
                "skill_name": row["skill_name"],
                "package_path": row["package_path"],
                "merkle_root": row["merkle_root"],
                "file_hashes": json.loads(row["file_hashes_json"]),
                "declared_description": row["declared_description"],
                "allowed_mcp_tools": json.loads(row["allowed_tools_json"]),
                "risk_score": row["risk_score"],
                "findings": json.loads(row["findings_json"]),
                "status": row["status"],
                "attested_at": row["attested_at"],
            }

    def verify_runtime_integrity(self, skill_name):
        """
        Re-computes live Merkle root against SQLite attestation to catch
        Time-of-Check to Time-of-Use (TOCTOU) file tampering.
        Returns (is_valid: bool, reason: str, record: dict|None).
        """
        record = self.get_attestation(skill_name)
        if not record:
            return False, f"Skill '{skill_name}' has no pre-flight attestation record.", None
        if record["status"] != "APPROVED":
            return False, f"Skill '{skill_name}' is {record['status']} (risk_score={record['risk_score']}).", record

        skill_dir = Path(record["package_path"])
        if not skill_dir.is_dir():
            return False, f"Skill directory missing on disk: {skill_dir}", record

        live_merkle, _ = self.compute_package_hashes(skill_dir)
        if live_merkle != record["merkle_root"]:
            return (
                False,
                f"TOCTOU MERKLE MISMATCH for '{skill_name}': expected {record['merkle_root'][:12]}..., got {live_merkle[:12]}...",
                record,
            )
        return True, "Integrity verified.", record
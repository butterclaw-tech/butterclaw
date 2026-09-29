"""
ButterClaw v0.8.0 — Topology Manager
Propagates taint down the agent lineage and preserves visual evidence.
"""

import sqlite3
import os
import shutil
import platform
import tempfile
from typing import List

# Setup Tiered Storage Directories
def get_hot_screenshot_dir() -> str:
    if platform.system() == "Linux" and os.path.exists("/dev/shm"):
        return "/dev/shm/butterclaw_hot_frames"
    return os.path.join(tempfile.gettempdir(), "butterclaw_hot_frames")

HOT_DIR = get_hot_screenshot_dir()
# EVIDENCE_DIR = "/var/lib/butterclaw/evidence_locker"
# Automatically use the Docker /data volume if it exists, otherwise use a local folder
EVIDENCE_DIR = "/data/evidence_locker" if os.path.exists("/data") else "evidence_locker"
os.makedirs(HOT_DIR, exist_ok=True)
os.makedirs(EVIDENCE_DIR, exist_ok=True)

class TopologyManager:
    #def __init__(self, db_path: str = "butterclaw.db"):
    #    self.db_path = db_path
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        else:
            self.db_path = db_path

    def apply_kinetic_taint(self, session_id: str, threat_reason: str) -> List[int]:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE sessions 
                SET taint_level = 2, taint_source = ? 
                WHERE session_id = ?
            """, (threat_reason, session_id))
            
            cursor.execute("SELECT agent_id FROM sessions WHERE session_id = ?", (session_id,))
            root_agent = cursor.fetchone()
            if not root_agent:
                return []
            
            root_agent_id = root_agent['agent_id']

            find_lineage_query = """
                WITH RECURSIVE agent_lineage AS (
                    SELECT agent_id, pid FROM agents WHERE agent_id = ?
                    UNION ALL
                    SELECT a.agent_id, a.pid FROM agents a
                    INNER JOIN agent_lineage al ON a.parent_agent_id = al.agent_id
                )
                SELECT agent_id, pid FROM agent_lineage;
            """
            cursor.execute(find_lineage_query, (root_agent_id,))
            affected_agents = cursor.fetchall()
            
            if not affected_agents:
                return []

            agent_ids = [row['agent_id'] for row in affected_agents]
            pids_to_kill = [row['pid'] for row in affected_agents if row['pid']]

            placeholders = ','.join('?' * len(agent_ids))
            quarantine_query = f"""
                UPDATE agents SET status = 'QUARANTINED' 
                WHERE agent_id IN ({placeholders}) AND status = 'ACTIVE'
            """
            cursor.execute(quarantine_query, agent_ids)
            conn.commit()
            
            print(f"[TOPOLOGY] Taint propagated. Quarantined {len(agent_ids)} agents.")
            return pids_to_kill

        except sqlite3.Error as e:
            print(f"[FATAL] Topology update failed: {e}")
            conn.rollback()
            return []
        finally:
            conn.close()

    def preserve_evidence(self, session_id: str, conn: sqlite3.Connection):
        """Moves screenshots from a blocked session to permanent storage."""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT screenshot_ref FROM telemetry_events 
            WHERE session_id = ? AND screenshot_ref IS NOT NULL
        """, (session_id,))
        
        for row in cursor.fetchall():
            source_path = row['screenshot_ref']
            if os.path.exists(source_path) and source_path.startswith(HOT_DIR):
                filename = os.path.basename(source_path)
                dest_path = os.path.join(EVIDENCE_DIR, f"{session_id}_{filename}")
                try:
                    shutil.move(source_path, dest_path)
                    cursor.execute("""
                        UPDATE telemetry_events SET screenshot_ref = ? 
                        WHERE screenshot_ref = ?
                    """, (dest_path, source_path))
                except Exception as e:
                    print(f"[EVIDENCE] Failed to preserve {filename}: {e}")
        conn.commit()
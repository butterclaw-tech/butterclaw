"""
ButterClaw v0.8.0 — Archiver Daemon
Manages database retention, incremental vacuuming, and RAM disk cleanup.
"""

import sqlite3
import time
import threading
import os
import glob
import platform
import tempfile
import shutil
from datetime import datetime

def get_hot_screenshot_dir() -> str:
    if platform.system() == "Linux" and os.path.exists("/dev/shm"):
        return "/dev/shm/butterclaw_hot_frames"
    return os.path.join(tempfile.gettempdir(), "butterclaw_hot_frames")

HOT_DIR = get_hot_screenshot_dir()

class ArchiverDaemon:
    def __init__(self, main_db: str = None, archive_dir: str = None):
        # Apply the ghost-database fix here too!
        if main_db is None:
            self.main_db = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        else:
            self.main_db = main_db
            
        self.archive_dir = archive_dir or ("/data/archives" if os.path.exists("/data") else "archives")
        self.evidence_dir = "/data/evidence_locker" if os.path.exists("/data") else "evidence_locker"
        
        self.is_running = True
        
        # Ensure persistent directories exist
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(self.evidence_dir, exist_ok=True)
        
        self.RETENTION_SECONDS = 86400 
        self.CHUNK_SIZE = 1000

    def _secure_tainted_evidence(self):
        """Moves screenshots from tainted sessions into permanent storage."""
        conn = sqlite3.connect(self.main_db, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            # Find all screenshots for tainted sessions that are still in volatile RAM
            query = """
                SELECT t.event_id, t.screenshot_ref, s.session_id 
                FROM telemetry_events t
                JOIN sessions s ON t.session_id = s.session_id
                WHERE s.taint_level > 0 
                  AND t.screenshot_ref IS NOT NULL 
                  AND t.screenshot_ref LIKE '%butterclaw_hot_frames%'
            """
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                old_path = row['screenshot_ref']
                if os.path.exists(old_path):
                    filename = os.path.basename(old_path)
                    new_path = os.path.join(self.evidence_dir, f"{row['session_id']}_{filename}")
                    
                    # Move from RAM to persistent Disk
                    shutil.move(old_path, new_path)

                    # Update the ledger so the TUI dashboard can still find the image
                    conn.execute("UPDATE telemetry_events SET screenshot_ref = ? WHERE event_id = ?", (new_path, row['event_id']))
            
            if rows:
                conn.commit()
                print(f"[EVIDENCE SECURED] Moved {len(rows)} malicious frames to permanent storage.")
                
        except sqlite3.Error as e:
            print(f"[ARCHIVER ERROR] Failed to secure evidence: {e}")
        finally:
            conn.close()
    
    def start_archiving(self):
        thread = threading.Thread(target=self._archiver_loop, daemon=True)
        thread.start()
        
        # Start the high-speed RAM sweeper in parallel
        sweeper_thread = threading.Thread(target=self._ram_sweeper_loop, daemon=True)
        sweeper_thread.start()
        print("[ARCHIVER] Retention and RAM sweeping daemons started.")

    def _ram_sweeper_loop(self):
        """Secures evidence, then sweeps the rest every 10 seconds."""
        while self.is_running:
            self._secure_tainted_evidence()  # 1. Save the crime scenes
            self._sweep_volatile_screenshots()  # 2. Burn the benign frames
            time.sleep(10)

    def _sweep_volatile_screenshots(self):
        """Deletes any unflagged screenshot older than 60 seconds."""
        current_time = time.time()
        swept_count = 0
        pattern = os.path.join(HOT_DIR, "*.webp") 
        
        for file_path in glob.glob(pattern):
            try:
                if (current_time - os.path.getmtime(file_path)) > 60.0:
                    os.remove(file_path)
                    swept_count += 1
            except OSError:
                pass 
                
        if swept_count > 0:
            print(f"[SWEEPER] Deleted {swept_count} benign frames from RAM.")

    def _archiver_loop(self):
        while self.is_running:
            self._execute_prune_cycle()
            for _ in range(3600):
                if not self.is_running: break
                time.sleep(1)

    def _execute_prune_cycle(self):
        conn = sqlite3.connect(self.main_db, timeout=15.0)
        current_month = datetime.now().strftime("%Y_%m")
        archive_db_path = os.path.join(self.archive_dir, f"butterclaw_archive_{current_month}.db")
        
        try:
            conn.execute(f"ATTACH DATABASE '{archive_db_path}' AS archive")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS archive.telemetry_events (
                    event_id INTEGER, session_id TEXT, timestamp REAL,
                    action_type TEXT, spatial_payload TEXT,
                    screenshot_ref TEXT, processed_by_dreamer BOOLEAN
                )
            """)
            
            cutoff_time = time.time() - self.RETENTION_SECONDS
            
            while self.is_running:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT event_id FROM main.telemetry_events 
                    WHERE processed_by_dreamer = 1 AND timestamp < ? LIMIT ?
                """, (cutoff_time, self.CHUNK_SIZE))
                
                rows = cursor.fetchall()
                if not rows: break 
                    
                event_ids = [row[0] for row in rows]
                placeholders = ','.join('?' * len(event_ids))
                
                conn.execute(f"""
                    INSERT INTO archive.telemetry_events 
                    SELECT * FROM main.telemetry_events WHERE event_id IN ({placeholders})
                """, event_ids)
                
                conn.execute(f"DELETE FROM main.telemetry_events WHERE event_id IN ({placeholders})", event_ids)
                conn.commit()
                time.sleep(0.5)
            
            conn.execute("PRAGMA main.incremental_vacuum(1000)")
            conn.commit()
            print(f"[ARCHIVER] Prune cycle complete for {current_month}.")
            
        except sqlite3.Error as e:
            print(f"[ERROR] Archiver failed: {e}")
            conn.rollback()
        finally:
            conn.execute("DETACH DATABASE archive")
            conn.close()
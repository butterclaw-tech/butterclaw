"""
ButterClaw v0.8.0 — Dreamer Daemon (Warm Memory)
Extracts resolution-independent behavioral attractors from tainted telemetry.
"""

import sqlite3
import time
import json
import hashlib
import os
from typing import List, Dict
import threading

class DreamerConsolidationLoop:
    def __init__(self, db_path: str = None, batch_size: int = 500):
        if db_path is None:
            self.db_path = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        else:
            self.db_path = db_path
            
        self.batch_size = batch_size
        self.is_running = True
        
        # Attractor window parameters
        self.MIN_PATTERN_LEN = 2
        self.MAX_PATTERN_LEN = 5
        
        # Grid settings to abstract exact (x,y) pixels into topological zones
        self.GRID_COLS = 4
        self.GRID_ROWS = 4
        self.SCREEN_WIDTH = 1920
        self.SCREEN_HEIGHT = 1080

    def start_dreaming(self):
        """Launches the background consolidation worker."""
        thread = threading.Thread(target=self._consolidation_worker, daemon=True)
        thread.start()
        print("[DREAMER] Warm Memory consolidation loop active.")

    def _consolidation_worker(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        
        while self.is_running:
            try:
                # 1. Fetch unprocessed events from terminated or quarantined sessions
                query = """
                    SELECT t.event_id, t.session_id, t.action_type, t.spatial_payload, s.taint_level 
                    FROM telemetry_events t
                    JOIN sessions s ON t.session_id = s.session_id
                    WHERE t.processed_by_dreamer = 0 
                      AND (s.taint_level >= 2 OR s.ended_at IS NOT NULL)
                    ORDER BY t.session_id, t.timestamp ASC
                    LIMIT ?
                """
                cursor = conn.cursor()
                cursor.execute(query, (self.batch_size,))
                rows = cursor.fetchall()
                
                if not rows:
                    time.sleep(10)
                    continue
                    
                # 2. Group events by session
                sessions_map: Dict[str, List[sqlite3.Row]] = {}
                for row in rows:
                    sid = row['session_id']
                    if sid not in sessions_map:
                        sessions_map[sid] = []
                    sessions_map[sid].append(row)
                    
                event_ids_to_mark = []
                
                # 3. Extract behavioral sequence attractors
                for sid, events in sessions_map.items():
                    taint_level = events[0]['taint_level']
                    trajectory = self._abstract_trajectory(events)
                    
                    # Only synthesize threat signatures from tainted sessions
                    if taint_level >= 2 and len(trajectory) >= self.MIN_PATTERN_LEN:
                        # Extract the terminal cascade (the critical closing sequence)
                        terminal_window = trajectory[-self.MAX_PATTERN_LEN:]
                        self._promote_to_cold_memory(conn, terminal_window, threat_category="terminal_taint_cascade")
                        
                        # Also extract 2-to-3 step sub-patterns if trajectory is long
                        if len(trajectory) > self.MIN_PATTERN_LEN:
                            for n in range(self.MIN_PATTERN_LEN, min(len(trajectory), self.MAX_PATTERN_LEN)):
                                sub_pattern = trajectory[-n:]
                                self._promote_to_cold_memory(conn, sub_pattern, threat_category="subsequence_attractor")
                    
                    event_ids_to_mark.extend([e['event_id'] for e in events])
                    
                # 4. Mark events processed within an atomic commit
                if event_ids_to_mark:
                    self._mark_events_processed(conn, event_ids_to_mark)
                    
            except Exception as e:
                print(f"[DREAMER ERROR] Consolidation cycle failed: {e}")
                
            time.sleep(2.0)

    def _abstract_trajectory(self, events: List[sqlite3.Row]) -> List[str]:
        sequence = []
        for event in events:
            action = event['action_type']
            try:
                payload = json.loads(event['spatial_payload']) if event['spatial_payload'] else {}
            except (json.JSONDecodeError, TypeError):
                payload = {}

            if action == 'mouse_click' and 'x' in payload and 'y' in payload:
                col = min(int(payload['x'] / (self.SCREEN_WIDTH / self.GRID_COLS)), self.GRID_COLS - 1)
                row = min(int(payload['y'] / (self.SCREEN_HEIGHT / self.GRID_ROWS)), self.GRID_ROWS - 1)
                sequence.append(f"click_ZONE_{col}_{row}")
            
            elif action == 'keyboard_type':
                text_len = len(payload.get('text', ''))
                sequence.append("type_LONG_BLOCK" if text_len > 50 else "type_SHORT")
            else:
                sequence.append(action)
                
        return sequence

    def _promote_to_cold_memory(self, conn: sqlite3.Connection, pattern: List[str], threat_category: str):
        pattern_str = json.dumps(pattern)
        behavioral_hash = hashlib.sha256(pattern_str.encode()).hexdigest()[:16]
        sig_id = f"SIG_{behavioral_hash}"
        
        query = """
            INSERT OR IGNORE INTO memory_signatures 
            (sig_id, threat_category, behavioral_hash, sequence_pattern, confidence_score)
            VALUES (?, ?, ?, ?, 0.85)
        """
        cursor = conn.cursor()
        cursor.execute(query, (sig_id, threat_category, behavioral_hash, pattern_str))
        conn.commit()
        
        # Only print if a NEW row was actually inserted
        if cursor.rowcount > 0:
            print(f"✨ [COLD MEMORY SYNTHESIZED] New Zero-Day signature {sig_id}: {pattern}")

    def _mark_events_processed(self, conn: sqlite3.Connection, event_ids: List[int]):
        chunk_size = 100
        for i in range(0, len(event_ids), chunk_size):
            chunk = event_ids[i:i+chunk_size]
            placeholders = ','.join('?' * len(chunk))
            query = f"UPDATE telemetry_events SET processed_by_dreamer = 1 WHERE event_id IN ({placeholders})"
            conn.execute(query, chunk)
        conn.commit()
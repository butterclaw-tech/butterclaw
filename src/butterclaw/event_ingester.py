"""
ButterClaw v0.8.0 — Event Ingester
High-speed asynchronous batch writer for spatial telemetry.
"""

import sqlite3
import json
import time
import threading
import queue
import atexit

class EventIngester:
    def __init__(self, db_path: str = "butterclaw.db"):
        self.db_path = db_path
        # Thread-safe queue to buffer incoming telemetry, was maxsize=10000, lowered to prevent unbounded memory growth
        self.write_queue = queue.Queue(maxsize=1000)
        self.is_running = True
        
        # Start the dedicated background writer thread
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        
        # Ensure the queue flushes to disk if the server shuts down
        atexit.register(self.shutdown)
        print("[INGESTER] High-speed RAM queue and background writer active.")

    def _setup_write_connection(self):
        """Dedicated connection for the single writer thread."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        
        # Critical Write PRAGMAs for high-frequency WAL
        conn.execute("PRAGMA journal_mode=WAL;")
        # NORMAL is perfectly safe in WAL mode and significantly faster than FULL
        conn.execute("PRAGMA synchronous=NORMAL;")
        # In-memory temp store for faster transaction processing
        conn.execute("PRAGMA temp_store=MEMORY;")
        return conn

    def log_event(self, session_id: str, action_type: str, spatial_payload: dict, screenshot_ref: str = None):
        """
        Non-blocking ingest. The gateway calls this.
        It pushes to RAM and returns instantly.
        """
        event_tuple = (
            session_id,
            time.time(), # Capture exact epoch timestamp of ingestion
            action_type,
            json.dumps(spatial_payload),
            screenshot_ref,
            0 # processed_by_dreamer = False
        )
        try:
            # Non-blocking put to avoid hanging the gateway if the queue is full
            self.write_queue.put_nowait(event_tuple)
        except queue.Full:
            print("[WARN] Ingest queue is full! Telemetry dropped.")

    def _writer_loop(self):
        """The single dedicated thread that drains the queue and writes to disk."""
        conn = self._setup_write_connection()
        cursor = conn.cursor()
        
        insert_query = """
            INSERT INTO telemetry_events 
            (session_id, timestamp, action_type, spatial_payload, screenshot_ref, processed_by_dreamer)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        batch = []
        batch_size = 50       # How many events to group into a single transaction
        flush_interval = 0.5  # Max seconds to wait before flushing an incomplete batch
        last_flush = time.time()

        while self.is_running or not self.write_queue.empty():
            try:
                # Block for a short time to allow events to accumulate
                event = self.write_queue.get(timeout=0.1)
                batch.append(event)
            except queue.Empty:
                pass # Queue is temporarily empty, check if we need to flush what we have

            # Flush condition: Batch size reached, OR time limit reached, OR shutting down
            time_since_flush = time.time() - last_flush
            if len(batch) >= batch_size or (batch and time_since_flush > flush_interval) or (not self.is_running and batch):
                try:
                    # executemany wraps the batch in a single atomic BEGIN/COMMIT transaction.
                    # This reduces SQLite transaction overhead by 90%.
                    cursor.executemany(insert_query, batch)
                    conn.commit()
                except sqlite3.OperationalError:
                    # Fails gracefully if the migration script hasn't run yet
                    pass
                except sqlite3.Error as e:
                    print(f"[FATAL] Failed to write telemetry batch: {e}")
                
                # Reset for next batch
                batch.clear()
                last_flush = time.time()

        conn.close()
        print("[INGEST] Background writer thread cleanly shut down.")

    def shutdown(self):
        """Signals the writer thread to drain the queue and exit."""
        self.is_running = False
        if self.writer_thread.is_alive():
            self.writer_thread.join(timeout=2.0)
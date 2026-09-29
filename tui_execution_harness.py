"""
ButterClaw v0.8.0 — TUI Execution Harness
A pseudo-TTY wrapper that runs an agent, intercepts its stdout for the dashboard, 
and provides a side-channel hook for spatial telemetry.
"""

#from dbm import sqlite3
import sqlite3
import os
import pty
import json
import uuid
import subprocess
import threading
from typing import Dict

# Import the v0.8.0 Core
from memory_engine import MemoryEngine
from event_ingester import EventIngester
from topology_manager import TopologyManager
from watcher_daemon import WatcherDaemon

class TUIExecutionHarness:
    def __init__(self, agent_command: list):
        self.agent_id = f"agt_{uuid.uuid4().hex[:8]}"
        self.session_id = f"ses_{uuid.uuid4().hex[:8]}"
        self.agent_command = agent_command
        
        # Point everything to the Docker volume so we stop making ghosts
        import os
        db_path = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        
        # Initialize the v0.8.0 Pipeline
        self.memory = MemoryEngine(db_path=db_path)
        self.ingester = EventIngester(db_path=db_path)
        self.topology = TopologyManager(db_path=db_path)
        self.watcher = WatcherDaemon()
        
        self.is_running = True

    def bootstrap_agent(self):
        """Spawns the agent in a PTY and registers it with the OS-level Topology."""
        master_fd, slave_fd = pty.openpty()
        
        # 1. Spawn the agent
        self.agent_process = subprocess.Popen(
            self.agent_command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True
        )
        
        os.close(slave_fd) # Close slave in parent
        
        # 2. Register PID with the SQLite Topology (Crucial for the Watcher)
        self._register_topology(self.agent_process.pid)
        
        print(f"[TUI] Agent {self.agent_id} spawned (PID: {self.agent_process.pid}). Session active.")
        return master_fd

    def _register_topology(self, pid: int):
        """Writes the initial state to the database so Taints can propagate."""
        import sqlite3
        import os # Make sure os is imported
        db_path = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        conn = sqlite3.connect(db_path)
        #conn = sqlite3.connect("butterclaw.db")
        conn.execute(
            "INSERT INTO agents (agent_id, pid, capabilities) VALUES (?, ?, ?)",
            (self.agent_id, pid, json.dumps(["tty", "spatial"]))
        )
        conn.execute(
            "INSERT INTO sessions (session_id, agent_id) VALUES (?, ?)",
            (self.session_id, self.agent_id)
        )
        conn.commit()
        conn.close()

    def intercept_spatial_channel(self, incoming_payload: Dict):
        """
        The critical choke point. This function is called whenever the agent 
        attempts a spatial action (via local socket, HTTP, or side-channel).
        """
        action_type = incoming_payload.get("action_type")
        coordinates = incoming_payload.get("payload")
        screenshot = incoming_payload.get("screenshot_ref")

        # 1. Evaluate via Hot & Cold Memory
        evaluation = self.memory.evaluate_spatial_intent(self.session_id, incoming_payload)
        is_allowed = evaluation["is_allowed"]
        
        # INJECT META-TAGS FOR THE DASHBOARD
        coordinates = coordinates or {}
        coordinates["_verdict"] = "ALLOW" if is_allowed else "BLOCK"
        coordinates["_policy"] = evaluation["reason"]

        if not is_allowed:
            # 2a. LOG THE CRIME BEFORE SHOOTING THE SUSPECT
            self.ingester.log_event(self.session_id, action_type, coordinates, screenshot)
            
            # 2b. Trigger the Kinetic Block
            self._execute_kinetic_block()
            return {"status": "BLOCKED", "reason": evaluation["reason"]}
            
        # 3. If allowed, push to high-speed RAM queue
        self.ingester.log_event(self.session_id, action_type, coordinates, screenshot)
        return {"status": "ALLOW"}

    def _execute_kinetic_block(self):
        """Visually updates the TUI and hands the kill order to the Watcher."""
        print("\n" + "="*50)
        print("🚨 [KINETIC BLOCK INITIATED] 🚨")
        print("MALICIOUS SPATIAL TRAJECTORY DETECTED.")
        print("="*50 + "\n")
        
        # Apply the taint to the SQLite topology and get the PIDs to kill
        pids_to_kill = self.topology.apply_kinetic_taint(
            self.session_id, 
            threat_reason="Matched Cold Memory Signature"
        )
        
        # Hand the execution off to the OS-level Watcher Daemon
        self.watcher.submit_kill_request(pids_to_kill)
        #self.is_running = False
        print("Agent quarantined. Leaving harness open to verify dashboard state.")

    def tui_render_loop(self, master_fd):
        """The loop that renders the pseudo-TTY text output for the operator."""
        while self.is_running:
            try:
                # Read the agent's standard output non-blockingly
                output = os.read(master_fd, 1024).decode('utf-8')
                if output:
                    print(output, end='', flush=True)
            except OSError:
                break

    def cleanup(self):
        """Kills the child process and closes the DB session gracefully."""
        # 1. Kill the orphaned agent process
        if hasattr(self, 'agent_process') and self.agent_process.poll() is None:
            self.agent_process.terminate()
            self.agent_process.wait(timeout=2)
            print(f"[TUI] Agent process {self.agent_process.pid} formally terminated.")
    
        # 2. Cap off the database ledger
        import sqlite3
        import os
        db_path = "/data/butterclaw.db" if os.path.exists("/data") else "butterclaw.db"
        try:
            conn = sqlite3.connect(db_path)
            conn.execute(
                "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE session_id = ?", 
                (self.session_id,)
            )
            # Only mark it terminated if it wasn't already QUARANTINED by the block
            conn.execute(
                "UPDATE agents SET status = 'TERMINATED' WHERE agent_id = ? AND status = 'ACTIVE'", 
                (self.agent_id,)
            )
            conn.commit()
            conn.close()
            print(f"[TUI] Session {self.session_id} officially closed in database.")
        except Exception as e:
            print(f"[TUI] Cleanup DB error: {e}")

if __name__ == "__main__":
    import time
    
    print("🚀 Bootstrapping Agent Execution Harness...")
    # 1. Spawn a dummy sleep process so the OS has a real PID to track
    harness = TUIExecutionHarness(agent_command=["sleep", "3600"])
    master_fd = harness.bootstrap_agent()
    
    # 2. Create a background thread for our manual test prompt
    def interactive_test():
        time.sleep(1)
        print("\n🎮 [TEST MODE] Agent PTY spawned. You can now inject spatial telemetry.")
        
        while harness.is_running:
            try:
                action = input("\nInject action ('click' or 'powershell') > ").strip().lower()
                if not harness.is_running:
                    break
                    
                if action == "click":
                    print("👉 Firing benign mouse click...")
                    harness.intercept_spatial_channel({
                        "action_type": "mouse_click",
                        "payload": {"x": 500, "y": 500},
                        "screenshot_ref": "none"
                    })
                elif action == "powershell":
                    print("☣️ Firing malicious payload...")
                    harness.intercept_spatial_channel({
                        "action_type": "keyboard_type",
                        "payload": {"text": "powershell.exe -ExecutionPolicy Bypass"},
                        "screenshot_ref": "none"
                    })
                else:
                    print("Unrecognized action. Type 'click' or 'powershell'.")
            except EOFError:
                break
                
    threading.Thread(target=interactive_test, daemon=True).start()
    
    # 3. Start the render loop to watch the output
    try:
        harness.tui_render_loop(master_fd)
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received. Exiting harness.")
    finally:
        harness.cleanup()
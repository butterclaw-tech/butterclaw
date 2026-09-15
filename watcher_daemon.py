"WatcherDaemon v0.8.0"

"""
The Watcher Daemon is the kinetic actuator of ButterClaw. 
Because it interacts directly with the host operating system, it requires extreme caution. 
If a rogue agent manages to spoof a PID in the SQLite topology, 
you do not want ButterClaw accidentally issuing a SIGKILL to systemd or your SSH daemon.

To safely execute these kills across both your Windows development environment and your Ubuntu VPS, 
we should use the psutil library. It bridges the gap between Windows TerminateProcess and POSIX SIGKILL, 
and more importantly, it allows us to hunt down OS-level orphaned children 
(e.g., if the agent spawned a naked bash or curl process that bypasses the ButterClaw SQLite registry).

"""

"""
Architectural Breakdown
The OS-Level Sweep (target_process.children(recursive=True)): While the TopologyManager identifies the ButterClaw agents (e.g., Python worker threads or Docker containers) that need to die, this psutil logic catches anything those agents spawned on the host. If an agent opened powershell.exe or /bin/bash to run a malicious script, this ensures the script dies with the agent.

Suspend Before Kill (.suspend()): A common evasion tactic for automated malware is to rapidly fork new processes the moment it detects termination signals. By issuing a suspend (which maps to SIGSTOP on Linux and NtSuspendProcess on Windows) before the kill sequence, you freeze the entire process tree in its tracks, stripping its ability to fork while you clean it up.

Zombie Reaping (psutil.wait_procs): Sending a kill() command is fire-and-forget, but sometimes the OS takes a moment to clean up the file descriptors and network sockets. Waiting ensures the system doesn't get clogged with zombie processes during a high-frequency attack.

Orchestrator Immunity: Caching os.getpid() at initialization guarantees the Watcher will never commit suicide, even if a flaw in the recursive CTE passes up the wrong parent ID.
"""

import psutil
import threading
import queue
import time
import os

class WatcherDaemon:
    def __init__(self):
        # Thread-safe queue for asynchronous kill requests
        self.kill_queue = queue.Queue()
        self.is_running = True
        
        # Protect the ButterClaw root process from ever being killed
        self.orchestrator_pid = os.getpid()
        
        # Start the background watcher loop
        self.worker_thread = threading.Thread(target=self._watcher_loop, daemon=True)
        self.worker_thread.start()
        print(f"[WATCHER] Daemon active. Orchestrator PID protected: {self.orchestrator_pid}")

    def submit_kill_request(self, pids_to_kill: list[int], reason: str = "Kinetic Policy Violation"):
        """
        Non-blocking ingestion of PIDs identified by the Topology Manager.
        """
        for pid in pids_to_kill:
            if pid:
                self.kill_queue.put_nowait((pid, reason))

    def _watcher_loop(self):
        """Background thread that safely dequeues and terminates processes."""
        while self.is_running:
            try:
                # Block until a kill request arrives
                target_pid, reason = self.kill_queue.get(timeout=1.0)
                self._execute_surgical_strike(target_pid, reason)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[WATCHER ERROR] Unhandled exception in kill loop: {e}")

    def _execute_surgical_strike(self, target_pid: int, reason: str):
        """
        Validates the target and aggressively terminates it along with any
        sub-processes it spawned on the host OS.
        """
        # 1. Critical Safety Checks
        if target_pid == self.orchestrator_pid:
            print(f"[WATCHER FATAL] Agent attempted to trick Watcher into killing orchestrator! (PID {target_pid})")
            return
            
        if target_pid in (0, 1):
            print(f"[WATCHER FATAL] Blocked attempt to kill system process (PID {target_pid})")
            return

        try:
            target_process = psutil.Process(target_pid)
            
            # 2. Gather OS-level children (recursive)
            # This catches processes the agent spawned directly via bash/cmd 
            # that aren't tracked in ButterClaw's SQLite topology.
            children = target_process.children(recursive=True)
            
            # 3. Freeze the processes first (SIGSTOP equivalent)
            # This prevents the malware/agent from spawning new children while we iterate
            target_process.suspend()
            for child in children:
                try:
                    child.suspend()
                except psutil.NoSuchProcess:
                    pass
                    
            print(f"[WATCHER] Suspended PID {target_pid} and {len(children)} OS-level children. Reason: {reason}")
            
            # 4. Execute the kill (SIGKILL equivalent)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
                    
            target_process.kill()
            
            # 5. Wait for the OS to reap the zombies (timeout 3 seconds)
            gone, alive = psutil.wait_procs([target_process] + children, timeout=3.0)
            
            if alive:
                print(f"[WATCHER WARN] {len(alive)} processes refused to die.")
            else:
                print(f"[WATCHER SUCCESS] Kinetic strike complete. Target {target_pid} neutralized.")

        except psutil.NoSuchProcess:
            print(f"[WATCHER INFO] PID {target_pid} no longer exists. Already dead.")
        except psutil.AccessDenied:
            print(f"[WATCHER ERROR] Permission denied to kill PID {target_pid}. Check Watcher privileges.")

    def shutdown(self):
        """Safely winds down the daemon."""
        self.is_running = False
        self.worker_thread.join()
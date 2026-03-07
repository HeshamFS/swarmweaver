"""
Process Registry for Autonomous Coding Agent
=============================================

Centralized tracking of background processes (servers, dev tools) to prevent:
- Port conflicts from multiple servers on the same port
- Process proliferation from spawning duplicate processes
- Orphaned processes that persist after session ends

The registry persists to disk in the project directory and tracks:
- Process ID (PID)
- Port number (if applicable)
- Command that started the process
- Start timestamp
- Process type (backend, frontend, dev-tool, etc.)
"""

import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

from core.paths import get_paths


@dataclass
class ProcessEntry:
    """Represents a tracked background process."""
    pid: int
    port: Optional[int]
    command: str
    process_type: str  # 'backend', 'frontend', 'dev-tool', 'test', etc.
    started_at: str
    cwd: str
    
    def is_alive(self) -> bool:
        """Check if the process is still running."""
        try:
            if sys.platform == "win32":
                # Windows: use tasklist
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {self.pid}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return str(self.pid) in result.stdout
            else:
                # Unix: send signal 0 to check if process exists
                os.kill(self.pid, 0)
                return True
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            return False


class ProcessRegistry:
    """
    Manages background process tracking across agent sessions.
    
    Usage:
        registry = ProcessRegistry(project_dir)
        registry.load()
        
        # Check before starting a server
        if registry.is_port_in_use(8000):
            existing = registry.get_process_on_port(8000)
            print(f"Port 8000 already used by PID {existing.pid}")
        else:
            # Start server and register
            pid = start_server(...)
            registry.register(pid, port=8000, command="uvicorn...", process_type="backend")
        
        # Cleanup dead processes
        registry.cleanup_dead_processes()
        
        # On shutdown
        registry.terminate_all()
    """
    
    REGISTRY_FILENAME = ".process_registry.json"
    
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.registry_file = get_paths(project_dir).process_registry
        self.processes: Dict[int, ProcessEntry] = {}
    
    def load(self) -> None:
        """Load registry from disk."""
        if not self.registry_file.exists():
            self.processes = {}
            return
        
        try:
            with open(self.registry_file, 'r') as f:
                data = json.load(f)
            
            self.processes = {}
            for pid_str, entry_data in data.get("processes", {}).items():
                pid = int(pid_str)
                self.processes[pid] = ProcessEntry(**entry_data)
                
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"[ProcessRegistry] Warning: Failed to load registry: {e}")
            self.processes = {}
    
    def save(self) -> None:
        """Persist registry to disk."""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "updated_at": datetime.now().isoformat(),
                "processes": {str(pid): asdict(entry) for pid, entry in self.processes.items()}
            }
            with open(self.registry_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ProcessRegistry] Warning: Failed to save registry: {e}")
    
    def register(
        self,
        pid: int,
        command: str,
        process_type: str,
        port: Optional[int] = None,
        cwd: Optional[str] = None
    ) -> ProcessEntry:
        """Register a new background process."""
        entry = ProcessEntry(
            pid=pid,
            port=port,
            command=command,
            process_type=process_type,
            started_at=datetime.now().isoformat(),
            cwd=cwd or str(self.project_dir)
        )
        self.processes[pid] = entry
        self.save()
        print(f"[ProcessRegistry] Registered PID {pid} ({process_type}) on port {port or 'N/A'}")
        return entry
    
    def unregister(self, pid: int) -> Optional[ProcessEntry]:
        """Remove a process from the registry."""
        entry = self.processes.pop(pid, None)
        if entry:
            self.save()
            print(f"[ProcessRegistry] Unregistered PID {pid}")
        return entry
    
    def get_process(self, pid: int) -> Optional[ProcessEntry]:
        """Get a process entry by PID."""
        return self.processes.get(pid)
    
    def get_process_on_port(self, port: int) -> Optional[ProcessEntry]:
        """Get the process registered on a specific port."""
        for entry in self.processes.values():
            if entry.port == port:
                return entry
        return None
    
    def get_processes_by_type(self, process_type: str) -> List[ProcessEntry]:
        """Get all processes of a specific type."""
        return [e for e in self.processes.values() if e.process_type == process_type]
    
    def is_port_in_use(self, port: int) -> bool:
        """
        Check if a port is in use (either by a registered process or system-wide).
        
        First checks the registry for a live registered process.
        Then checks if the port is actually bound by any process.
        """
        # Check registry first
        registered = self.get_process_on_port(port)
        if registered and registered.is_alive():
            return True
        
        # Check if port is actually bound
        return self._check_port_bound(port)
    
    def _check_port_bound(self, port: int) -> bool:
        """Check if a port is bound by attempting to connect."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result == 0  # 0 means connection succeeded (port is in use)
        except Exception:
            return False
    
    def find_available_port(self, preferred: int, max_offset: int = 10) -> int:
        """
        Find an available port starting from preferred.
        
        Args:
            preferred: The preferred port number
            max_offset: Maximum offset to try from preferred port
            
        Returns:
            Available port number
            
        Raises:
            RuntimeError: If no port is available in the range
        """
        for offset in range(max_offset + 1):
            port = preferred + offset
            if not self.is_port_in_use(port):
                return port
        
        raise RuntimeError(f"No available port found in range {preferred}-{preferred + max_offset}")
    
    def cleanup_dead_processes(self) -> List[int]:
        """
        Remove dead processes from the registry.
        
        Returns:
            List of PIDs that were removed
        """
        dead_pids = []
        for pid, entry in list(self.processes.items()):
            if not entry.is_alive():
                dead_pids.append(pid)
                del self.processes[pid]
        
        if dead_pids:
            self.save()
            print(f"[ProcessRegistry] Cleaned up {len(dead_pids)} dead processes: {dead_pids}")
        
        return dead_pids
    
    def terminate_process(self, pid: int, force: bool = False) -> bool:
        """
        Terminate a registered process.
        
        Args:
            pid: Process ID to terminate
            force: If True, use SIGKILL instead of SIGTERM
            
        Returns:
            True if process was terminated successfully
        """
        entry = self.processes.get(pid)
        if not entry:
            print(f"[ProcessRegistry] PID {pid} not in registry")
            return False
        
        if not entry.is_alive():
            self.unregister(pid)
            return True
        
        try:
            if sys.platform == "win32":
                # Windows: use taskkill
                args = ["taskkill", "/PID", str(pid)]
                if force:
                    args.append("/F")
                subprocess.run(args, capture_output=True, timeout=5)
            else:
                # Unix: send SIGTERM or SIGKILL
                import signal
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.kill(pid, sig)
            
            self.unregister(pid)
            print(f"[ProcessRegistry] Terminated PID {pid}")
            return True
            
        except Exception as e:
            print(f"[ProcessRegistry] Failed to terminate PID {pid}: {e}")
            return False
    
    def terminate_all(self, process_type: Optional[str] = None, force: bool = False) -> int:
        """
        Terminate all registered processes.
        
        Args:
            process_type: If specified, only terminate processes of this type
            force: If True, use SIGKILL instead of SIGTERM
            
        Returns:
            Number of processes terminated
        """
        count = 0
        for pid in list(self.processes.keys()):
            entry = self.processes.get(pid)
            if process_type and entry and entry.process_type != process_type:
                continue
            if self.terminate_process(pid, force):
                count += 1
        
        return count
    
    def get_status(self) -> Dict:
        """Get a status summary of all registered processes."""
        self.cleanup_dead_processes()
        
        status = {
            "total": len(self.processes),
            "by_type": {},
            "ports_in_use": [],
            "processes": []
        }
        
        for entry in self.processes.values():
            # Count by type
            status["by_type"][entry.process_type] = status["by_type"].get(entry.process_type, 0) + 1
            
            # Track ports
            if entry.port:
                status["ports_in_use"].append(entry.port)
            
            # Add process info
            status["processes"].append({
                "pid": entry.pid,
                "port": entry.port,
                "type": entry.process_type,
                "alive": entry.is_alive(),
                "command_preview": entry.command[:50] + "..." if len(entry.command) > 50 else entry.command
            })
        
        return status
    
    def __len__(self) -> int:
        return len(self.processes)
    
    def __repr__(self) -> str:
        return f"ProcessRegistry({len(self.processes)} processes, file={self.registry_file})"


# Port constants for common services
class StandardPorts:
    """Standard port numbers for common development services."""
    BACKEND_PRIMARY = 8000
    BACKEND_ALT = 8003
    FRONTEND_PRIMARY = 3000
    FRONTEND_ALT = 3001
    
    # Port ranges
    BACKEND_RANGE = range(8000, 8100)
    FRONTEND_RANGE = range(3000, 3100)


def detect_process_type(command: str) -> str:
    """
    Detect the process type from a command string.
    
    Returns one of: 'backend', 'frontend', 'dev-tool', 'test', 'other'
    """
    cmd_lower = command.lower()
    
    # Backend patterns
    if any(x in cmd_lower for x in ['uvicorn', 'gunicorn', 'flask', 'django', 'fastapi']):
        return 'backend'
    
    # Frontend patterns
    if any(x in cmd_lower for x in ['next', 'vite', 'react', 'webpack', 'npm run dev', 'pnpm dev']):
        return 'frontend'
    
    # Test patterns
    if any(x in cmd_lower for x in ['pytest', 'jest', 'test', 'playwright']):
        return 'test'
    
    # Dev tool patterns
    if any(x in cmd_lower for x in ['node', 'npm', 'npx', 'python']):
        return 'dev-tool'
    
    return 'other'


def extract_port_from_command(command: str) -> Optional[int]:
    """
    Extract port number from a command string.
    
    Looks for patterns like:
    - --port 8000
    - --port=8000
    - -p 3000
    - :8000 (for uvicorn host:port)
    """
    import re
    
    # Pattern: --port 8000 or --port=8000
    match = re.search(r'--port[=\s]+(\d+)', command)
    if match:
        return int(match.group(1))
    
    # Pattern: -p 3000
    match = re.search(r'-p\s+(\d+)', command)
    if match:
        return int(match.group(1))
    
    # Pattern: host:port (like 0.0.0.0:8000)
    match = re.search(r':\s*(\d{4,5})\b', command)
    if match:
        port = int(match.group(1))
        if 1024 < port < 65535:
            return port
    
    return None


# Global registry instance (set per-project)
_registry: Optional[ProcessRegistry] = None


def get_registry(project_dir: Optional[Path] = None) -> ProcessRegistry:
    """
    Get or create the global process registry.
    
    Args:
        project_dir: Project directory. Required on first call.
        
    Returns:
        ProcessRegistry instance
    """
    global _registry
    
    if project_dir:
        _registry = ProcessRegistry(project_dir)
        _registry.load()
    
    if _registry is None:
        raise RuntimeError("ProcessRegistry not initialized. Call get_registry(project_dir) first.")
    
    return _registry


def check_and_register_server(
    command: str,
    port: Optional[int] = None,
    process_type: Optional[str] = None,
    cwd: Optional[str] = None
) -> tuple[bool, str, Optional[int]]:
    """
    Check if a server can be started and suggest alternatives if port is taken.
    
    Args:
        command: The command to run
        port: Explicit port, or None to auto-detect from command
        process_type: Process type, or None to auto-detect
        cwd: Current working directory
        
    Returns:
        Tuple of (can_start, message, suggested_port)
        - can_start: True if the original port is available
        - message: Human-readable status message
        - suggested_port: Alternative port if original is taken, or original if available
    """
    registry = get_registry()
    
    # Auto-detect port and type if not provided
    if port is None:
        port = extract_port_from_command(command)
    
    if process_type is None:
        process_type = detect_process_type(command)
    
    if port is None:
        return True, "No port detected, proceeding without port tracking", None
    
    # Check if port is in use
    existing = registry.get_process_on_port(port)
    if existing:
        if existing.is_alive():
            # Port is genuinely in use
            try:
                suggested = registry.find_available_port(port)
                return False, f"Port {port} in use by PID {existing.pid} ({existing.process_type}). Suggested: {suggested}", suggested
            except RuntimeError:
                return False, f"Port {port} in use and no alternatives available", None
        else:
            # Process is dead, clean up
            registry.unregister(existing.pid)
    
    # Check if port is bound but not in registry
    if registry._check_port_bound(port):
        try:
            suggested = registry.find_available_port(port)
            return False, f"Port {port} is bound by an untracked process. Suggested: {suggested}", suggested
        except RuntimeError:
            return False, f"Port {port} is bound and no alternatives available", None
    
    return True, f"Port {port} is available", port

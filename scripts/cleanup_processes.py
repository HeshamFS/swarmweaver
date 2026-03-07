#!/usr/bin/env python
"""
Process Cleanup Utility for Autonomous Coding Agent
====================================================

Utility script to manage and cleanup background processes started by the agent.

Usage:
    python cleanup_processes.py [project_dir] [--status] [--cleanup] [--force] [--kill-port PORT]

Examples:
    # Show status of all tracked processes
    python cleanup_processes.py ./generations/my_project --status
    
    # Cleanup dead processes from registry
    python cleanup_processes.py ./generations/my_project --cleanup
    
    # Terminate all tracked processes
    python cleanup_processes.py ./generations/my_project --terminate
    
    # Force kill all tracked processes
    python cleanup_processes.py ./generations/my_project --terminate --force
    
    # Kill process on specific port
    python cleanup_processes.py ./generations/my_project --kill-port 8000
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from state.process_registry import ProcessRegistry, get_registry


def print_status(registry: ProcessRegistry) -> None:
    """Print status of all tracked processes."""
    status = registry.get_status()
    
    print("\n" + "=" * 60)
    print("  PROCESS REGISTRY STATUS")
    print("=" * 60)
    
    if status["total"] == 0:
        print("\nNo tracked processes.")
        return
    
    print(f"\nTotal processes: {status['total']}")
    print(f"Ports in use: {status['ports_in_use']}")
    
    print("\nBy type:")
    for ptype, count in status["by_type"].items():
        print(f"  - {ptype}: {count}")
    
    print("\nProcesses:")
    print("-" * 60)
    for proc in status["processes"]:
        alive_str = "✓ ALIVE" if proc["alive"] else "✗ DEAD"
        port_str = f"port {proc['port']}" if proc['port'] else "no port"
        print(f"  PID {proc['pid']:6} | {proc['type']:10} | {port_str:10} | {alive_str}")
        print(f"         Command: {proc['command_preview']}")
    print("-" * 60)


def cleanup_dead(registry: ProcessRegistry) -> int:
    """Cleanup dead processes from registry."""
    dead = registry.cleanup_dead_processes()
    if dead:
        print(f"Cleaned up {len(dead)} dead processes: {dead}")
    else:
        print("No dead processes to cleanup.")
    return len(dead)


def terminate_all(registry: ProcessRegistry, force: bool = False) -> int:
    """Terminate all tracked processes."""
    status = registry.get_status()
    if status["total"] == 0:
        print("No processes to terminate.")
        return 0
    
    print(f"Terminating {status['total']} processes...")
    if force:
        print("Using force kill (SIGKILL)")
    
    terminated = registry.terminate_all(force=force)
    print(f"Terminated {terminated} processes.")
    return terminated


def kill_port(registry: ProcessRegistry, port: int, force: bool = False) -> bool:
    """Kill process on specific port."""
    entry = registry.get_process_on_port(port)
    if not entry:
        print(f"No tracked process on port {port}.")
        
        # Check if port is bound by untracked process
        if registry._check_port_bound(port):
            print(f"Port {port} is bound by an untracked process.")
            print("You may need to manually find and kill the process:")
            print(f"  Windows: netstat -ano | findstr :{port}")
            print(f"  Linux/Mac: lsof -i :{port}")
        return False
    
    print(f"Killing process on port {port}: PID {entry.pid} ({entry.process_type})")
    success = registry.terminate_process(entry.pid, force=force)
    if success:
        print("Process terminated successfully.")
    else:
        print("Failed to terminate process.")
    return success


def main():
    parser = argparse.ArgumentParser(
        description="Manage background processes for the autonomous coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "project_dir",
        type=Path,
        nargs="?",
        default=Path("./generations/my_project"),
        help="Project directory containing the process registry (default: ./generations/my_project)"
    )
    
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show status of all tracked processes"
    )
    
    parser.add_argument(
        "--cleanup", "-c",
        action="store_true",
        help="Cleanup dead processes from registry"
    )
    
    parser.add_argument(
        "--terminate", "-t",
        action="store_true",
        help="Terminate all tracked processes"
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force kill processes (SIGKILL instead of SIGTERM)"
    )
    
    parser.add_argument(
        "--kill-port", "-k",
        type=int,
        metavar="PORT",
        help="Kill process on specific port"
    )
    
    args = parser.parse_args()
    
    # Resolve project directory
    project_dir = args.project_dir.resolve()
    
    if not project_dir.exists():
        print(f"Error: Project directory does not exist: {project_dir}")
        sys.exit(1)
    
    # Initialize registry
    registry = ProcessRegistry(project_dir)
    registry.load()
    
    # Default to status if no action specified
    if not any([args.status, args.cleanup, args.terminate, args.kill_port]):
        args.status = True
    
    # Execute actions
    if args.status:
        print_status(registry)
    
    if args.cleanup:
        cleanup_dead(registry)
    
    if args.kill_port:
        kill_port(registry, args.kill_port, args.force)
    
    if args.terminate:
        terminate_all(registry, args.force)


if __name__ == "__main__":
    main()

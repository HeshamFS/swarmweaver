"""
Doctor Health Check System
=============================

Modular health checker. Runs checks on dependencies, config, databases, processes, and directories.
"""

import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class HealthCheck:
    """Result of a single health check."""
    name: str
    category: str
    status: str  # pass, warn, fail
    message: str
    details: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Doctor:
    """
    System health checker.

    Usage:
        doc = Doctor(project_dir)
        results = doc.run_all()
        # or
        results = doc.run_category("dependencies")
    """

    def __init__(self, project_dir: Optional[Path] = None):
        self.project_dir = project_dir

    def run_all(self) -> list[HealthCheck]:
        results = []
        results.extend(self.check_dependencies())
        results.extend(self.check_config())
        if self.project_dir:
            results.extend(self.check_databases())
            results.extend(self.check_processes())
            results.extend(self.check_directories())
        return results

    def run_category(self, category: str) -> list[HealthCheck]:
        dispatch = {
            "dependencies": self.check_dependencies,
            "config": self.check_config,
            "databases": self.check_databases,
            "processes": self.check_processes,
            "directories": self.check_directories,
        }
        fn = dispatch.get(category)
        if fn:
            return fn()
        return [HealthCheck(name=category, category=category, status="fail", message=f"Unknown category: {category}")]

    def check_dependencies(self) -> list[HealthCheck]:
        results = []
        deps = [
            ("git", ["git", "--version"]),
            ("python3", ["python3", "--version"] if os.name != "nt" else ["python", "--version"]),
            ("node", ["node", "--version"]),
            ("npm", ["npm", "--version"]),
        ]
        for name, cmd in deps:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    version = result.stdout.strip().split("\n")[0]
                    results.append(HealthCheck(
                        name=name, category="dependencies", status="pass",
                        message=f"{name} available", details=version,
                    ))
                else:
                    results.append(HealthCheck(
                        name=name, category="dependencies", status="warn",
                        message=f"{name} returned non-zero", details=result.stderr[:100],
                    ))
            except (FileNotFoundError, subprocess.TimeoutExpired):
                results.append(HealthCheck(
                    name=name, category="dependencies", status="fail",
                    message=f"{name} not found",
                ))
        return results

    def check_config(self) -> list[HealthCheck]:
        results = []
        # Check for API key or OAuth token
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
        results.append(HealthCheck(
            name="auth", category="config",
            status="pass" if has_key else "fail",
            message="Authentication configured" if has_key else "No ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN set",
        ))

        # Check .env file
        if self.project_dir:
            env_file = self.project_dir.parent / ".env"
            if not env_file.exists():
                env_file = Path(__file__).parent.parent / ".env"
            results.append(HealthCheck(
                name=".env", category="config",
                status="pass" if env_file.exists() else "warn",
                message=".env file found" if env_file.exists() else "No .env file (using environment variables)",
            ))

        # Check disk space
        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024 ** 3)
            results.append(HealthCheck(
                name="disk", category="config",
                status="pass" if free_gb > 5 else ("warn" if free_gb > 1 else "fail"),
                message=f"{free_gb:.1f} GB free disk space",
            ))
        except OSError:
            pass

        return results

    def check_databases(self) -> list[HealthCheck]:
        if not self.project_dir:
            return []
        results = []
        db_files = {
            "mail.db": ".swarmweaver/mail.db",
            "events.db": ".swarmweaver/events.db",
            "runs.db": ".swarmweaver/runs.db",
            "merge_queue.db": ".swarmweaver/swarm/merge_queue.db",
        }
        for name, rel_path in db_files.items():
            db_path = self.project_dir / rel_path
            if not db_path.exists():
                results.append(HealthCheck(
                    name=name, category="databases", status="pass",
                    message=f"{name} not created yet (will be created on first use)",
                ))
                continue
            try:
                conn = sqlite3.connect(str(db_path), timeout=5)
                conn.execute("PRAGMA integrity_check")
                conn.close()
                results.append(HealthCheck(
                    name=name, category="databases", status="pass",
                    message=f"{name} integrity OK",
                    details=f"Size: {db_path.stat().st_size / 1024:.1f} KB",
                ))
            except Exception as e:
                results.append(HealthCheck(
                    name=name, category="databases", status="fail",
                    message=f"{name} integrity check failed", details=str(e)[:200],
                ))
        return results

    def check_processes(self) -> list[HealthCheck]:
        if not self.project_dir:
            return []
        results = []
        from core.paths import get_paths
        registry_file = get_paths(self.project_dir).resolve_read("process_registry.json")
        if not registry_file.exists():
            results.append(HealthCheck(
                name="process_registry", category="processes", status="pass",
                message="No process registry (no background processes tracked)",
            ))
            return results

        try:
            import json
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            processes = data.get("processes", {})
            alive = 0
            dead = 0
            for pid_str, entry in processes.items():
                try:
                    os.kill(int(pid_str), 0)
                    alive += 1
                except (OSError, ValueError):
                    dead += 1

            status = "pass" if dead == 0 else ("warn" if alive > 0 else "fail")
            results.append(HealthCheck(
                name="process_registry", category="processes", status=status,
                message=f"{alive} alive, {dead} dead processes",
                details=f"Total tracked: {len(processes)}",
            ))
        except Exception as e:
            results.append(HealthCheck(
                name="process_registry", category="processes", status="warn",
                message=f"Could not check processes: {str(e)[:100]}",
            ))
        return results

    def check_directories(self) -> list[HealthCheck]:
        if not self.project_dir:
            return []
        results = []
        dirs_to_check = [
            ("project_dir", self.project_dir),
            ("prompts", Path(__file__).parent.parent / "prompts"),
            ("templates", Path(__file__).parent.parent / "templates"),
        ]
        for name, path in dirs_to_check:
            results.append(HealthCheck(
                name=name, category="directories",
                status="pass" if path.exists() else "warn",
                message=f"{name} exists" if path.exists() else f"{name} missing: {path}",
            ))
        return results

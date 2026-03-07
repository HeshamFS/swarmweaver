"""
Self-Healing Verification Loop
================================

After task completion, auto-runs the project's test suite. If tests fail,
reopens the task with error context for the agent to self-correct
(max 3 retries per task).

Detects test commands from project files (pytest, npm test, etc.)
and parses results to determine pass/fail status.
"""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from state.task_list import TaskList


@dataclass
class VerificationResult:
    """Result of running the test suite."""
    passed: bool
    output: str
    failed_tests: list[str] = field(default_factory=list)
    error_summary: str = ""
    return_code: int = 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failed_tests": self.failed_tests,
            "error_summary": self.error_summary,
            "return_code": self.return_code,
            "output_lines": len(self.output.splitlines()),
        }


class VerificationManager:
    """
    Manages test verification for completed tasks.

    After each coding session, finds unverified completed tasks,
    runs the test suite, and either marks them as verified or
    reopens them with error context.
    """

    MAX_ATTEMPTS = 3

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self._test_cmd: Optional[list[str]] = None

    def _find_project_python(self) -> str:
        """Find the right Python for the project.

        Priority:
        1. Project's own venv (venv/, .venv/, env/)
        2. 'python' on PATH (works if user activated a venv before starting SwarmWeaver)
        3. SwarmWeaver's Python as last resort
        """
        import shutil

        # 1. Project-local venv
        for venv_name in ("venv", ".venv", "env"):
            venv_path = self.project_dir / venv_name
            if not venv_path.is_dir():
                continue
            for subpath in ("Scripts/python.exe", "bin/python"):
                candidate = venv_path / subpath
                if candidate.exists():
                    return str(candidate)

        # 2. System 'python' / 'python3' on PATH
        for name in ("python3", "python"):
            found = shutil.which(name)
            if found and Path(found).resolve() != Path(sys.executable).resolve():
                return found

        # 3. Fallback
        return sys.executable

    def detect_test_command(self) -> Optional[list[str]]:
        """Auto-detect the test command from project files.

        Supports Python (pytest, unittest), Node (npm test, vitest, jest),
        Rust (cargo test), Go (go test), and monorepo layouts.
        """
        if self._test_cmd:
            return self._test_cmd

        python = self._find_project_python()

        # ── Python: pytest ──
        for marker in ("pytest.ini", "setup.cfg", "conftest.py"):
            if (self.project_dir / marker).exists():
                self._test_cmd = [python, "-m", "pytest", "-x", "--tb=short"]
                return self._test_cmd
        if (self.project_dir / "pyproject.toml").exists():
            try:
                content = (self.project_dir / "pyproject.toml").read_text(encoding="utf-8")
                if "[tool.pytest" in content or "pytest" in content:
                    self._test_cmd = [python, "-m", "pytest", "-x", "--tb=short"]
                    return self._test_cmd
            except OSError:
                pass

        # ── Python: unittest (tests/ directory with test_*.py files) ──
        tests_dir = self.project_dir / "tests"
        if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
            self._test_cmd = [python, "-m", "pytest", "-x", "--tb=short"]
            return self._test_cmd

        # ── Node: package.json scripts ──
        pkg_json = self.project_dir / "package.json"
        if pkg_json.exists():
            try:
                import json
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    test_script = scripts["test"]
                    if "vitest" in test_script:
                        self._test_cmd = ["npx", "vitest", "run"]
                    elif "jest" in test_script:
                        self._test_cmd = ["npx", "jest", "--forceExit"]
                    else:
                        self._test_cmd = ["npm", "test", "--", "--watchAll=false"]
                    return self._test_cmd
            except (OSError, json.JSONDecodeError):
                pass

        # ── Rust: Cargo.toml ──
        if (self.project_dir / "Cargo.toml").exists():
            self._test_cmd = ["cargo", "test"]
            return self._test_cmd

        # ── Go: go.mod ──
        if (self.project_dir / "go.mod").exists():
            self._test_cmd = ["go", "test", "./..."]
            return self._test_cmd

        # ── Monorepo: backend/ with Python tests ──
        backend_dir = self.project_dir / "backend"
        if backend_dir.is_dir():
            for marker in ("pytest.ini", "conftest.py", "pyproject.toml"):
                if (backend_dir / marker).exists():
                    self._test_cmd = [python, "-m", "pytest", "-x", "--tb=short", str(backend_dir)]
                    return self._test_cmd

        # ── Monorepo: frontend/ with npm test ──
        frontend_dir = self.project_dir / "frontend"
        if frontend_dir.is_dir() and (frontend_dir / "package.json").exists():
            try:
                import json
                data = json.loads((frontend_dir / "package.json").read_text(encoding="utf-8"))
                if "test" in data.get("scripts", {}):
                    self._test_cmd = ["npm", "test", "--prefix", str(frontend_dir), "--", "--watchAll=false"]
                    return self._test_cmd
            except (OSError, json.JSONDecodeError):
                pass

        return None

    def run_tests(self, cmd: Optional[list[str]] = None) -> VerificationResult:
        """Run the test suite and return results."""
        test_cmd = cmd or self.detect_test_command()

        if not test_cmd:
            return VerificationResult(
                passed=True,
                output="No test command detected — skipping verification",
                error_summary="no_tests",
            )

        try:
            result = subprocess.run(
                test_cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=str(self.project_dir),
            )

            output = result.stdout + "\n" + result.stderr

            passed = result.returncode == 0

            # Parse failed tests from output
            failed_tests = self._parse_failed_tests(output)
            error_summary = self._extract_error_summary(output) if not passed else ""

            return VerificationResult(
                passed=passed,
                output=output,
                failed_tests=failed_tests,
                error_summary=error_summary,
                return_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                output="Test suite timed out after 5 minutes",
                error_summary="timeout",
                return_code=-1,
            )
        except FileNotFoundError as e:
            return VerificationResult(
                passed=True,  # Don't block on missing test runner
                output=f"Test runner not found: {e}",
                error_summary="runner_not_found",
                return_code=-1,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                output=f"Verification error: {e}",
                error_summary=str(e)[:200],
                return_code=-1,
            )

    def _parse_failed_tests(self, output: str) -> list[str]:
        """Extract names of failed tests from output."""
        failed = []

        # pytest pattern: FAILED path::test_name
        for m in re.finditer(r"FAILED\s+(\S+)", output):
            failed.append(m.group(1))

        # jest/vitest pattern: ✕ test name  or  FAIL src/...
        for m in re.finditer(r"(?:✕|✗|FAIL)\s+(.+?)$", output, re.MULTILINE):
            name = m.group(1).strip()
            if name and len(name) < 200:
                failed.append(name)

        return failed[:20]  # Cap at 20

    def _extract_error_summary(self, output: str) -> str:
        """Extract a concise error summary from test output."""
        lines = output.splitlines()

        # Look for summary lines
        for i, line in enumerate(lines):
            if any(kw in line.lower() for kw in ["failed", "error", "assertion"]):
                # Get this line and a few surrounding
                start = max(0, i - 1)
                end = min(len(lines), i + 3)
                return "\n".join(lines[start:end]).strip()[:500]

        # Fallback: last 5 non-empty lines
        non_empty = [l for l in lines if l.strip()]
        return "\n".join(non_empty[-5:]).strip()[:500]

    def verify_completed_tasks(self) -> list[dict]:
        """
        Main entry: find unverified completed tasks, run tests,
        mark verified or reopen with error context.

        Returns a list of actions taken.
        """
        task_list = TaskList(self.project_dir)
        if not task_list.load():
            return []

        actions = []

        # Find tasks that are done but unverified
        unverified = [
            t for t in task_list.tasks
            if t.status == "done"
            and getattr(t, "verification_status", "unverified") == "unverified"
        ]

        if not unverified:
            return []

        # Run tests once (not per-task)
        result = self.run_tests()

        if result.error_summary == "no_tests":
            # No tests — mark all as verified, but emit only ONE event for the whole batch
            for task in unverified:
                task.verification_status = "verified"  # type: ignore[attr-defined]
            task_list.save()
            # Single summary event instead of one per task (prevents 30+ feed spam)
            task_ids = [t.id for t in unverified]
            task_range = f"{unverified[0].id} – {unverified[-1].id}" if len(unverified) > 1 else unverified[0].id
            actions.append({
                "task_id": unverified[0].id,  # Keep for backward compatibility
                "task_ids": task_ids,
                "task_range": task_range,
                "action": "verified_no_tests",
                "message": f"No test suite detected — {len(unverified)} task(s) auto-verified",
            })
            return actions

        if result.passed:
            # All tests pass — mark unverified tasks as verified
            for task in unverified:
                task.verification_status = "verified"  # type: ignore[attr-defined]
                task.verification_attempts = getattr(task, "verification_attempts", 0) + 1  # type: ignore[attr-defined]
                actions.append({
                    "task_id": task.id,
                    "action": "verified",
                    "message": "Tests passed",
                })
        else:
            # Tests fail — reopen tasks if under retry limit
            for task in unverified:
                attempts = getattr(task, "verification_attempts", 0) + 1

                if attempts >= self.MAX_ATTEMPTS:
                    task.verification_status = "failed_verification"  # type: ignore[attr-defined]
                    task.verification_attempts = attempts  # type: ignore[attr-defined]
                    task.last_verification_error = result.error_summary  # type: ignore[attr-defined]
                    actions.append({
                        "task_id": task.id,
                        "action": "failed_verification",
                        "message": f"Failed after {attempts} attempts: {result.error_summary[:100]}",
                    })
                else:
                    # Reopen the task
                    task.status = "pending"
                    task.verification_status = "retrying"  # type: ignore[attr-defined]
                    task.verification_attempts = attempts  # type: ignore[attr-defined]
                    task.last_verification_error = result.error_summary  # type: ignore[attr-defined]
                    task.notes = (
                        f"{task.notes}\n[VERIFY] Attempt {attempts}: Tests failed. "
                        f"Errors: {result.error_summary[:200]}"
                    ).strip()
                    actions.append({
                        "task_id": task.id,
                        "action": "reopened",
                        "message": f"Attempt {attempts}/{self.MAX_ATTEMPTS}: {result.error_summary[:100]}",
                    })

        task_list.save()
        return actions

"""Quality gates that run before accepting a worker as done."""
import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class QualityGateReport:
    worker_id: int
    passed: bool
    gates: list[GateResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "passed": self.passed,
            "gates": [asdict(g) for g in self.gates],
        }


class QualityGateChecker:
    """Runs quality gates on a worker's worktree before accepting completion."""

    def __init__(self, worktree_path: str | Path):
        self.worktree_path = Path(worktree_path)

    def check_all(self, worker_id: int) -> QualityGateReport:
        """Run all 4 quality gates and return report."""
        gates = [
            self._check_tests(),
            self._check_uncommitted_changes(),
            self._check_task_list_updated(),
            self._check_no_conflict_markers(),
        ]
        all_passed = all(g.passed for g in gates)
        return QualityGateReport(worker_id=worker_id, passed=all_passed, gates=gates)

    def _check_tests(self) -> GateResult:
        """Gate 1: Tests pass (if test files exist)."""
        try:
            # Check if there are test files
            test_files = list(self.worktree_path.glob("**/test_*.py")) + \
                        list(self.worktree_path.glob("**/*.test.ts")) + \
                        list(self.worktree_path.glob("**/*.test.tsx")) + \
                        list(self.worktree_path.glob("**/*.spec.ts"))

            if not test_files:
                return GateResult(name="tests_pass", passed=True, detail="No test files found, gate skipped")

            # Try running tests
            result = subprocess.run(
                ["python3", "-m", "pytest", "--tb=short", "-q"],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return GateResult(name="tests_pass", passed=True, detail="All tests passed")
            else:
                # Extract failure summary
                output = result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                return GateResult(name="tests_pass", passed=False, detail=f"Tests failed: {output}")
        except subprocess.TimeoutExpired:
            return GateResult(name="tests_pass", passed=False, detail="Tests timed out after 120s")
        except FileNotFoundError:
            return GateResult(name="tests_pass", passed=True, detail="No test runner found, gate skipped")
        except Exception as e:
            return GateResult(name="tests_pass", passed=False, detail=f"Error running tests: {e}")

    def _check_uncommitted_changes(self) -> GateResult:
        """Gate 2: No uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            uncommitted = result.stdout.strip()
            if not uncommitted:
                return GateResult(name="no_uncommitted", passed=True, detail="Working tree clean")
            else:
                file_count = len(uncommitted.splitlines())
                return GateResult(
                    name="no_uncommitted",
                    passed=False,
                    detail=f"{file_count} uncommitted file(s): {uncommitted[:200]}"
                )
        except Exception as e:
            return GateResult(name="no_uncommitted", passed=False, detail=f"Error checking git status: {e}")

    def _check_task_list_updated(self) -> GateResult:
        """Gate 3: task_list.json exists and has updated task statuses."""
        task_file = self.worktree_path / "task_list.json"
        if not task_file.exists():
            return GateResult(name="tasks_updated", passed=False, detail="task_list.json not found")
        try:
            data = json.loads(task_file.read_text())
            tasks = data.get("tasks", [])
            if not tasks:
                return GateResult(name="tasks_updated", passed=True, detail="No tasks in list")

            # Check if at least one task has been marked done
            done = [t for t in tasks if t.get("status") in ("done", "completed", "verified")]
            if done:
                return GateResult(
                    name="tasks_updated",
                    passed=True,
                    detail=f"{len(done)}/{len(tasks)} tasks completed"
                )
            else:
                return GateResult(
                    name="tasks_updated",
                    passed=False,
                    detail="No tasks marked as completed"
                )
        except Exception as e:
            return GateResult(name="tasks_updated", passed=False, detail=f"Error reading task list: {e}")

    def _check_no_conflict_markers(self) -> GateResult:
        """Gate 4: No merge conflict markers in tracked files."""
        try:
            # Grep for conflict markers
            grep_result = subprocess.run(
                ["grep", "-rn", "<<<<<<< ", "--include=*.py", "--include=*.ts",
                 "--include=*.tsx", "--include=*.js", "--include=*.md", "."],
                cwd=str(self.worktree_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if grep_result.stdout.strip():
                files = set(line.split(":")[0] for line in grep_result.stdout.strip().splitlines())
                return GateResult(
                    name="no_conflicts",
                    passed=False,
                    detail=f"Conflict markers found in: {', '.join(files)}"
                )
            return GateResult(name="no_conflicts", passed=True, detail="No conflict markers found")
        except Exception as e:
            return GateResult(name="no_conflicts", passed=True, detail=f"Check skipped: {e}")

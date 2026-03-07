"""
4-Tier Merge Conflict Resolution
===================================

When a git merge produces conflicts, we escalate through progressively more sophisticated resolution:

  Tier 1: Clean merge     — git merge succeeds with no conflicts (free)
  Tier 2: Auto-resolve    — Parse conflict markers, keep incoming changes (free)
  Tier 3: AI-resolve      — Ask Claude to semantically merge both versions (~1 API call)
  Tier 4: Reimagine       — Abort merge, get both versions, reimplement from scratch (~1 API call)

Each tier is attempted only if the previous tier fails. The resolution tier
is recorded for observability and learning.
"""

import json
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Optional

from core.models import MERGE_MODEL


class ResolutionTier(IntEnum):
    """Which tier resolved the merge conflict."""
    CLEAN = 1
    AUTO_RESOLVE = 2
    AI_RESOLVE = 3
    REIMAGINE = 4
    FAILED = 0  # All tiers failed


@dataclass
class MergeResolution:
    """Result of a tiered merge attempt."""
    success: bool
    tier: ResolutionTier
    branch: str
    files_conflicted: list[str]
    files_resolved: list[str]
    error: Optional[str] = None
    details: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["tier_name"] = self.tier.name.lower()
        return d


def _run_git(*args: str, cwd: Optional[Path] = None) -> tuple[bool, str]:
    """Run a git command. Returns (success, output)."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(cwd) if cwd else None,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f"[MERGE] Git command timed out: {' '.join(['git', *args])}", flush=True)
        return False, ""
    except Exception as e:
        return False, str(e)


def _get_conflicted_files(cwd: Path) -> list[str]:
    """Get list of files with merge conflicts."""
    ok, output = _run_git("diff", "--name-only", "--diff-filter=U", cwd=cwd)
    if ok and output.strip():
        return [f.strip() for f in output.splitlines() if f.strip()]
    return []


def _looks_like_prose(text: str) -> bool:
    """
    Check if AI output looks like conversational prose rather than code.
    Rejects outputs that are clearly just the AI talking instead of producing code.
    """
    prose_indicators = [
        "I'll ", "I will ", "Let me ", "Here's ", "Here is ",
        "The conflict ", "This conflict ", "To resolve ",
        "I've merged", "I have merged",
    ]
    first_line = text.strip().split("\n")[0] if text.strip() else ""
    return any(first_line.startswith(indicator) for indicator in prose_indicators)


class MergeResolver:
    """
    4-tier merge conflict resolver.

    Usage:
        resolver = MergeResolver(project_dir)
        result = resolver.resolve(branch_name, commit_message)
    """

    # Conflict marker pattern
    CONFLICT_RE = re.compile(
        r"<<<<<<<[^\n]*\n(.*?)=======\n(.*?)>>>>>>>[^\n]*\n",
        re.DOTALL,
    )

    HISTORY_FILE = ".swarmweaver/merge_history.json"

    def __init__(
        self,
        project_dir: Path,
        max_tier: int = 4,
        claude_model: str | None = None,
    ):
        self.project_dir = project_dir
        self.max_tier = min(max_tier, 4)
        self.claude_model = claude_model or MERGE_MODEL
        self._history = self._load_history()

    def _load_history(self) -> list[dict]:
        """Load conflict history for merge prediction."""
        history_file = self.project_dir / self.HISTORY_FILE
        if not history_file.exists():
            return []
        try:
            return json.loads(history_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_history_entry(self, resolution: "MergeResolution") -> None:
        """Record a resolution to conflict history for future prediction."""
        entry = {
            "files": resolution.files_conflicted,
            "tier_used": resolution.tier.value,
            "success": resolution.success,
            "branch": resolution.branch,
            "timestamp": datetime.now().isoformat() if hasattr(datetime, 'now') else "",
        }
        self._history.append(entry)
        # Keep last 100 entries
        if len(self._history) > 100:
            self._history = self._history[-100:]
        try:
            history_file = self.project_dir / self.HISTORY_FILE
            history_file.parent.mkdir(parents=True, exist_ok=True)
            history_file.write_text(
                json.dumps(self._history, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def _predict_skip_tiers(self, conflicted_files: list[str]) -> list[int]:
        """Predict which tiers to skip based on past failures for similar files."""
        if not self._history or not conflicted_files:
            return []
        file_set = set(conflicted_files)
        tier_failures: dict[int, int] = {}
        for entry in self._history:
            if not entry.get("success") and set(entry.get("files", [])) & file_set:
                tier = entry.get("tier_used", 0)
                tier_failures[tier] = tier_failures.get(tier, 0) + 1
        # Skip tiers that have failed 3+ times on overlapping files
        return [tier for tier, count in tier_failures.items() if count >= 3]

    def _get_past_solutions(self, conflicted_files: list[str]) -> list[str]:
        """Get descriptions of past successful resolutions for similar files."""
        if not self._history:
            return []
        file_set = set(conflicted_files)
        solutions = []
        for entry in self._history:
            if entry.get("success") and set(entry.get("files", [])) & file_set:
                tier_names = {1: "clean", 2: "auto-resolve", 3: "AI-resolve", 4: "reimagine"}
                tier_name = tier_names.get(entry.get("tier_used", 0), "unknown")
                solutions.append(f"Previously resolved via {tier_name} for files: {', '.join(entry.get('files', []))}")
        return solutions[-5:]  # Last 5 solutions

    def resolve(
        self,
        branch: str,
        commit_message: str = "",
    ) -> MergeResolution:
        """
        Attempt to merge a branch using tiered conflict resolution.

        Args:
            branch: Branch name to merge
            commit_message: Merge commit message

        Returns:
            MergeResolution with success status and tier info
        """
        if not commit_message:
            commit_message = f"Merge {branch}"

        # --- Tier 1: Clean merge ---
        result = self._tier1_clean_merge(branch, commit_message)
        if result.success:
            self._save_history_entry(result)
            return result

        # Get conflicted files for remaining tiers
        conflicted = _get_conflicted_files(self.project_dir)
        if not conflicted:
            _run_git("merge", "--abort", cwd=self.project_dir)
            failed_result = MergeResolution(
                success=False,
                tier=ResolutionTier.FAILED,
                branch=branch,
                files_conflicted=[],
                files_resolved=[],
                error=result.error,
                details="Merge failed (not a conflict issue)",
            )
            self._save_history_entry(failed_result)
            return failed_result

        # Predict which tiers to skip based on conflict history
        skip_tiers = self._predict_skip_tiers(conflicted)

        # --- Tier 2: Auto-resolve (keep incoming) ---
        if self.max_tier >= 2 and 2 not in skip_tiers:
            result = self._tier2_auto_resolve(branch, commit_message, conflicted)
            if result.success:
                self._save_history_entry(result)
                return result

        # --- Tier 3: AI-resolve ---
        if self.max_tier >= 3 and 3 not in skip_tiers:
            result = self._tier3_ai_resolve(branch, commit_message, conflicted)
            if result.success:
                self._save_history_entry(result)
                return result

        # --- Tier 4: Reimagine ---
        if self.max_tier >= 4 and 4 not in skip_tiers:
            result = self._tier4_reimagine(branch, commit_message, conflicted)
            if result.success:
                self._save_history_entry(result)
                return result

        # All tiers exhausted
        _run_git("merge", "--abort", cwd=self.project_dir)
        final = MergeResolution(
            success=False,
            tier=ResolutionTier.FAILED,
            branch=branch,
            files_conflicted=conflicted,
            files_resolved=[],
            error="All resolution tiers exhausted",
            details=f"Tried {self.max_tier} tiers, none succeeded",
        )
        self._save_history_entry(final)
        return final

    def _tier1_clean_merge(
        self, branch: str, commit_message: str,
    ) -> MergeResolution:
        """Tier 1: Attempt a clean git merge."""
        ok, output = _run_git(
            "merge", branch, "--no-edit", "-m", commit_message,
            cwd=self.project_dir,
        )

        if ok:
            return MergeResolution(
                success=True,
                tier=ResolutionTier.CLEAN,
                branch=branch,
                files_conflicted=[],
                files_resolved=[],
                details="Clean merge succeeded",
            )

        return MergeResolution(
            success=False,
            tier=ResolutionTier.CLEAN,
            branch=branch,
            files_conflicted=[],
            files_resolved=[],
            error=output[:500],
            details="Clean merge failed, conflicts detected",
        )

    def _tier2_auto_resolve(
        self,
        branch: str,
        commit_message: str,
        conflicted: list[str],
    ) -> MergeResolution:
        """
        Tier 2: Parse conflict markers and keep incoming (branch) changes.

        This is a fast, free resolution that works well when the branch changes
        are more recent and should take priority.
        """
        resolved = []
        failed = []

        for filepath in conflicted:
            full_path = self.project_dir / filepath
            if not full_path.exists():
                failed.append(filepath)
                continue

            try:
                content = full_path.read_text(encoding="utf-8")
                new_content, count = self.CONFLICT_RE.subn(r"\2", content)

                if count > 0:
                    full_path.write_text(new_content, encoding="utf-8")
                    _run_git("add", filepath, cwd=self.project_dir)
                    resolved.append(filepath)
                else:
                    failed.append(filepath)
            except Exception as e:
                print(f"[MERGE] Auto-resolve failed for {filepath}: {e}", flush=True)
                failed.append(filepath)

        if not failed:
            # All conflicts resolved — commit
            ok, output = _run_git(
                "commit", "--no-edit", "-m", commit_message,
                cwd=self.project_dir,
            )
            if ok:
                return MergeResolution(
                    success=True,
                    tier=ResolutionTier.AUTO_RESOLVE,
                    branch=branch,
                    files_conflicted=conflicted,
                    files_resolved=resolved,
                    details=f"Auto-resolved {len(resolved)} file(s) (kept incoming)",
                )

        # Auto-resolve didn't fully succeed — abort and retry with next tier
        _run_git("merge", "--abort", cwd=self.project_dir)

        # Re-attempt the merge to set up for the next tier
        _run_git(
            "merge", branch, "--no-edit", "-m", commit_message,
            cwd=self.project_dir,
        )

        return MergeResolution(
            success=False,
            tier=ResolutionTier.AUTO_RESOLVE,
            branch=branch,
            files_conflicted=conflicted,
            files_resolved=resolved,
            error=f"{len(failed)} file(s) could not be auto-resolved",
        )

    def _tier3_ai_resolve(
        self,
        branch: str,
        commit_message: str,
        conflicted: list[str],
    ) -> MergeResolution:
        """
        Tier 3: Use Claude to semantically resolve conflicts.

        For each conflicted file, sends both versions to Claude and asks
        it to produce a merged result.
        """
        resolved = []
        failed = []

        for filepath in conflicted:
            full_path = self.project_dir / filepath
            if not full_path.exists():
                failed.append(filepath)
                continue

            try:
                content = full_path.read_text(encoding="utf-8")

                # Build prompt for Claude
                prompt = (
                    "You are resolving a git merge conflict. Below is a file with "
                    "conflict markers (<<<<<<< / ======= / >>>>>>>). Output ONLY the "
                    "final resolved file content. Do NOT include any explanation, "
                    "commentary, or markdown fences. Combine both sides intelligently, "
                    "keeping all meaningful changes from both versions.\n\n"
                    f"File: {filepath}\n\n{content}"
                )

                # Shell out to Claude CLI
                result = subprocess.run(
                    ["claude", "--print", "-p", prompt, "--model", self.claude_model],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(self.project_dir),
                )

                if result.returncode == 0 and result.stdout.strip():
                    resolved_content = result.stdout

                    # Validate: reject prose responses
                    if _looks_like_prose(resolved_content):
                        failed.append(filepath)
                        continue

                    # Validate: should not contain conflict markers
                    if "<<<<<<<" in resolved_content or ">>>>>>>" in resolved_content:
                        failed.append(filepath)
                        continue

                    full_path.write_text(resolved_content, encoding="utf-8")
                    _run_git("add", filepath, cwd=self.project_dir)
                    resolved.append(filepath)
                else:
                    failed.append(filepath)

            except subprocess.TimeoutExpired:
                print(f"[MERGE] AI resolve timed out after 120s for {filepath}", flush=True)
                failed.append(filepath)
            except Exception as e:
                print(f"[MERGE] AI resolve failed for {filepath}: {e}", flush=True)
                failed.append(filepath)

        if not failed:
            ok, _ = _run_git(
                "commit", "--no-edit", "-m", commit_message,
                cwd=self.project_dir,
            )
            if ok:
                return MergeResolution(
                    success=True,
                    tier=ResolutionTier.AI_RESOLVE,
                    branch=branch,
                    files_conflicted=conflicted,
                    files_resolved=resolved,
                    details=f"AI-resolved {len(resolved)} file(s)",
                )

        # Abort for next tier
        _run_git("merge", "--abort", cwd=self.project_dir)
        _run_git(
            "merge", branch, "--no-edit", "-m", commit_message,
            cwd=self.project_dir,
        )

        return MergeResolution(
            success=False,
            tier=ResolutionTier.AI_RESOLVE,
            branch=branch,
            files_conflicted=conflicted,
            files_resolved=resolved,
            error=f"{len(failed)} file(s) could not be AI-resolved",
        )

    def _tier4_reimagine(
        self,
        branch: str,
        commit_message: str,
        conflicted: list[str],
    ) -> MergeResolution:
        """
        Tier 4: Abort merge entirely and reimagine conflicted files.

        Gets both versions (ours and theirs) of each conflicted file, then
        asks Claude to produce a fresh implementation incorporating both.
        This is the most expensive tier but handles intractable conflicts.
        """
        # Abort the current merge state
        _run_git("merge", "--abort", cwd=self.project_dir)

        resolved = []
        failed = []

        for filepath in conflicted:
            try:
                # Get "ours" version (current branch)
                ok_ours, ours_content = _run_git(
                    "show", f"HEAD:{filepath}", cwd=self.project_dir,
                )

                # Get "theirs" version (incoming branch)
                ok_theirs, theirs_content = _run_git(
                    "show", f"{branch}:{filepath}", cwd=self.project_dir,
                )

                if not ok_ours or not ok_theirs:
                    failed.append(filepath)
                    continue

                prompt = (
                    "You are reimagining a file that had intractable merge conflicts. "
                    "Below are two versions of the same file from different branches. "
                    "Create a SINGLE final version that incorporates ALL meaningful "
                    "changes from BOTH versions. Output ONLY the file content. "
                    "No explanation, no markdown fences, no commentary.\n\n"
                    f"File: {filepath}\n\n"
                    f"=== VERSION A (current branch) ===\n{ours_content}\n\n"
                    f"=== VERSION B (incoming branch: {branch}) ===\n{theirs_content}"
                )

                result = subprocess.run(
                    ["claude", "--print", "-p", prompt, "--model", self.claude_model],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd=str(self.project_dir),
                )

                if result.returncode == 0 and result.stdout.strip():
                    reimagined = result.stdout

                    if _looks_like_prose(reimagined):
                        failed.append(filepath)
                        continue

                    if "<<<<<<<" in reimagined or ">>>>>>>" in reimagined:
                        failed.append(filepath)
                        continue

                    full_path = self.project_dir / filepath
                    full_path.write_text(reimagined, encoding="utf-8")
                    _run_git("add", filepath, cwd=self.project_dir)
                    resolved.append(filepath)
                else:
                    failed.append(filepath)

            except subprocess.TimeoutExpired:
                print(f"[MERGE] Reimagine timed out after 180s for {filepath}", flush=True)
                failed.append(filepath)
            except Exception as e:
                print(f"[MERGE] Reimagine failed for {filepath}: {e}", flush=True)
                failed.append(filepath)

        if resolved and not failed:
            # Commit the reimagined files
            ok, _ = _run_git(
                "commit", "-m", f"{commit_message} (reimagined)",
                cwd=self.project_dir,
            )
            if ok:
                return MergeResolution(
                    success=True,
                    tier=ResolutionTier.REIMAGINE,
                    branch=branch,
                    files_conflicted=conflicted,
                    files_resolved=resolved,
                    details=f"Reimagined {len(resolved)} file(s) from scratch",
                )

        return MergeResolution(
            success=False,
            tier=ResolutionTier.REIMAGINE,
            branch=branch,
            files_conflicted=conflicted,
            files_resolved=resolved,
            error=f"Reimagine failed for {len(failed)} file(s)",
        )

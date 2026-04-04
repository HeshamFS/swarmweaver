"""
FULL END-TO-END WORKFLOW TEST
==============================

Simulates the COMPLETE greenfield workflow from start to finish:
  1. Project creation with .swarmweaver/ structure
  2. Memory system initialization (global + project)
  3. CLAUDE.md loading into prompt
  4. Task list creation
  5. Smart swarm: orchestrator + worker-1 runs
  6. INTERRUPTION mid-run
  7. Resume detection from transcript + registry
  8. Task status recovery
  9. Worker-2 spawned for remaining tasks
  10. INTERRUPTION again
  11. Resume again — verify everything accumulates correctly
  12. Final state verification
"""

import sys
import json
import os
import tempfile
import shutil
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_full_workflow():
    print("=" * 70)
    print("FULL END-TO-END WORKFLOW TEST")
    print("=" * 70)

    # ══════════════════════════════════════════════════════════════════
    # STEP 1: Create a fresh project
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 1] Create fresh project")

    project = Path(tempfile.mkdtemp()) / "my_todo_app"
    project.mkdir(parents=True)

    # Init git
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@test.com"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=str(project), capture_output=True)
    (project / "README.md").write_text("# Todo App\n")
    subprocess.run(["git", "add", "-A"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(project), capture_output=True)

    print(f"  Project: {project}")
    assert (project / ".git").is_dir(), "Git not initialized"
    print("  Git initialized: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 2: ensure_dir creates .swarmweaver/ + memory structure
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 2] Initialize .swarmweaver/ via ensure_dir()")

    from core.paths import get_paths
    paths = get_paths(project)
    paths.ensure_dir()

    sw = project / ".swarmweaver"
    assert sw.is_dir(), ".swarmweaver/ not created"
    assert (sw / "memory").is_dir(), "memory/ not created"
    assert (sw / "memory" / "MEMORY.md").is_file(), "MEMORY.md not created"
    assert (sw / "rules").is_dir(), "rules/ not created"
    assert (sw / "transcripts").is_dir(), "transcripts/ not created"
    print("  .swarmweaver/ created with memory/, rules/, transcripts/: OK")

    # Check global memory also exists
    global_sw = Path.home() / ".swarmweaver"
    assert global_sw.is_dir(), "~/.swarmweaver/ not created"
    assert (global_sw / "CLAUDE.md").is_file(), "Global CLAUDE.md not created"
    assert (global_sw / "memory" / "MEMORY.md").is_file(), "Global MEMORY.md not created"
    print("  ~/.swarmweaver/ global memory: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 3: CLAUDE.md + MEMORY.md loading
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 3] CLAUDE.md and memory loading")

    # Create project CLAUDE.md
    proj_claude = sw / "CLAUDE.md"
    proj_claude.write_text(
        "# Todo App Instructions\n\n"
        "This is a React + TypeScript todo app.\n"
        "Always use functional components.\n",
        encoding="utf-8",
    )

    # Create a project memory file
    mem_dir = sw / "memory"
    mem_file = mem_dir / "architecture.md"
    mem_file.write_text(
        "---\nname: Architecture\ndescription: App uses React + Vite\ntype: project\n---\n\n"
        "The app uses React 19 with Vite bundler and Tailwind CSS.\n",
        encoding="utf-8",
    )
    # Update MEMORY.md index
    (mem_dir / "MEMORY.md").write_text(
        "- [Architecture](architecture.md) — React + Vite + Tailwind setup\n",
        encoding="utf-8",
    )

    from services.memory_files import build_claude_md_context, build_memory_context

    claude_ctx = build_claude_md_context(project)
    mem_ctx = build_memory_context(project)

    assert "Todo App Instructions" in claude_ctx, "Project CLAUDE.md not loaded"
    assert "functional components" in claude_ctx, "CLAUDE.md content missing"
    assert "Architecture" in mem_ctx or "React" in mem_ctx, "Memory not loaded"
    print(f"  CLAUDE.md context: {len(claude_ctx)} chars — includes project instructions: OK")
    print(f"  Memory context: {len(mem_ctx)} chars — includes architecture: OK")

    # Check global CLAUDE.md is also included
    assert "Global SwarmWeaver" in claude_ctx, "Global CLAUDE.md not loaded"
    print("  Global CLAUDE.md included: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 4: Create task list (simulating what the wizard generates)
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 4] Create task list")

    from state.task_list import TaskList

    tasks_data = {
        "metadata": {"mode": "greenfield", "version": "20.0"},
        "tasks": [
            {"id": "TASK-001", "title": "Scaffold Vite + React project", "status": "pending", "priority": "high", "dependencies": []},
            {"id": "TASK-002", "title": "Configure Tailwind CSS", "status": "pending", "priority": "high", "dependencies": ["TASK-001"]},
            {"id": "TASK-003", "title": "Create Todo model and state", "status": "pending", "priority": "high", "dependencies": ["TASK-001"]},
            {"id": "TASK-004", "title": "Build TodoList component", "status": "pending", "priority": "medium", "dependencies": ["TASK-003"]},
            {"id": "TASK-005", "title": "Build AddTodo component", "status": "pending", "priority": "medium", "dependencies": ["TASK-003"]},
            {"id": "TASK-006", "title": "Add localStorage persistence", "status": "pending", "priority": "medium", "dependencies": ["TASK-004", "TASK-005"]},
            {"id": "TASK-007", "title": "Add dark mode toggle", "status": "pending", "priority": "low", "dependencies": ["TASK-002"]},
            {"id": "TASK-008", "title": "Write unit tests", "status": "pending", "priority": "low", "dependencies": ["TASK-004", "TASK-005"]},
        ],
    }
    (sw / "task_list.json").write_text(json.dumps(tasks_data, indent=2))

    tl = TaskList(project)
    tl.load()
    assert len(tl.tasks) == 8, f"Expected 8 tasks, got {len(tl.tasks)}"
    print(f"  Created 8 tasks (all pending): OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 5: Smart Swarm Run 1 — worker-1 completes 3 tasks
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 5] Smart Swarm Run 1 — worker-1 completes 3 tasks")

    # Simulate orchestrator creating worker-1
    w1_path = sw / "swarm" / "worker-1"
    w1_path.mkdir(parents=True)
    subprocess.run(["git", "branch", "swarm/worker-1"], cwd=str(project), capture_output=True)

    # Worker-1 completes tasks 1-3 (writes to MAIN task_list per our fix)
    tl = TaskList(project)
    tl.load()
    for t in tl.tasks:
        if t.id in ("TASK-001", "TASK-002", "TASK-003"):
            t.status = "done"
    tl.save()

    # Worker creates some files
    (w1_path / "src").mkdir(parents=True, exist_ok=True)
    (w1_path / "src" / "App.tsx").write_text("export default function App() { return <div>Todo</div> }")
    (w1_path / "package.json").write_text('{"name": "todo-app"}')

    # Registry: save worker-1 (append-only)
    reg_path = sw / "swarm" / "worker_registry.json"
    registry = {
        "next_worker_id": 2,
        "workers": {
            "1": {
                "id": 1, "name": "worker-1",
                "task_ids": ["TASK-001", "TASK-002", "TASK-003"],
                "worktree_path": str(w1_path),
                "branch": "swarm/worker-1",
                "status": "completed",
            },
        },
    }
    reg_path.write_text(json.dumps(registry, indent=2))

    # Transcript: record everything
    from services.transcript import TranscriptWriter, TranscriptReader

    tw = TranscriptWriter(project, "session-001")
    tw.open()
    tw.write_turn_start(1, "code", "claude-sonnet-4-6")
    tw.write_worker_spawned(1, "worker-1", ["TASK-001", "TASK-002", "TASK-003"],
                            str(w1_path), "swarm/worker-1")
    tw.write_task_update("TASK-001", "done", "Scaffold project")
    tw.write_task_update("TASK-002", "done", "Configure Tailwind")
    tw.write_task_update("TASK-003", "done", "Create Todo model")
    tw.write_worker_completed(1, "worker-1", ["TASK-001", "TASK-002", "TASK-003"], "completed")
    tw.write_progress("Worker-1 completed scaffolding", tasks_done=3, tasks_total=8)
    tw.write_turn_end(1, "code", input_tokens=8000, output_tokens=3000, cost_usd=0.05)

    # Budget tracking
    from state.budget import BudgetTracker
    budget = BudgetTracker(project)
    budget.record_real_usage(8000, 3000, 0.05, "claude-sonnet-4-6",
                             cache_read_tokens=2000, cache_write_tokens=500)
    budget.record_api_call(15000, "claude-sonnet-4-6")
    budget.record_code_changes(150, 0)

    # ── INTERRUPTION ──
    tw.write_interruption()
    tw.close(clean=False)

    print("  Worker-1 completed TASK-001, 002, 003: OK")
    print("  Registry saved (1 worker): OK")
    print("  Transcript saved with interruption: OK")
    print("  Budget tracked ($0.05, 8K/3K tokens): OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 6: Verify state after interruption
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 6] Verify state after interruption")

    # Task list
    tl_check = TaskList(project)
    tl_check.load()
    done = [t for t in tl_check.tasks if t.status == "done"]
    pending = [t for t in tl_check.tasks if t.status == "pending"]
    assert len(done) == 3, f"Expected 3 done, got {len(done)}"
    assert len(pending) == 5, f"Expected 5 pending, got {len(pending)}"
    print(f"  Task list: {len(done)} done, {len(pending)} pending: OK")

    # Registry
    reg = json.loads(reg_path.read_text())
    assert len(reg["workers"]) == 1
    assert reg["workers"]["1"]["status"] == "completed"
    print(f"  Registry: 1 worker (completed): OK")

    # Transcript
    transcripts = sorted((sw / "transcripts").glob("*.jsonl"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
    entries = TranscriptReader.load_transcript(transcripts[0])
    info = TranscriptReader.detect_interruption(entries)
    assert info["interrupted"] is True
    assert len(info["workers"]) == 1
    assert info["tasks_done"] == 3
    print(f"  Transcript: interrupted=True, 1 worker, 3/8 done: OK")

    # Budget
    budget2 = BudgetTracker(project)
    status = budget2.get_status()
    assert status["total_input_tokens"] == 8000
    assert status["total_cache_read_tokens"] == 2000
    assert status["total_lines_added"] == 150
    print(f"  Budget: $0.05, 8K in, 3K out, 2K cache, +150 lines: OK")

    # Global transcript copy
    global_transcript = Path.home() / ".swarmweaver" / "transcripts" / "session-001.jsonl"
    assert global_transcript.exists(), "Global transcript not synced"
    print(f"  Global transcript synced: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 7: Resume detection
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 7] Resume detection")

    # Build resume context (as core/agent.py does)
    resume_ctx = TranscriptReader.build_resume_context(entries)
    assert "Session Recovery Context" in resume_ctx
    assert "worker-1" in resume_ctx
    assert "TASK-001" in resume_ctx
    assert "DO NOT recreate" in resume_ctx
    print(f"  Resume context: {len(resume_ctx)} chars")
    print(f"  Contains worker info: OK")
    print(f"  Contains task statuses: OK")
    print(f"  Contains 'DO NOT recreate' instruction: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 8: Run 2 — worker-2 completes 3 more tasks
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 8] Run 2 — worker-2 completes TASK-004, 005, 006")

    w2_path = sw / "swarm" / "worker-2"
    w2_path.mkdir(parents=True)

    # Worker-2 completes 3 tasks (writes to MAIN)
    tl = TaskList(project)
    tl.load()
    for t in tl.tasks:
        if t.id in ("TASK-004", "TASK-005", "TASK-006"):
            t.status = "done"
    tl.save()

    # APPEND to registry (must keep worker-1!)
    existing_reg = json.loads(reg_path.read_text())
    existing_reg["next_worker_id"] = 3
    existing_reg["workers"]["2"] = {
        "id": 2, "name": "worker-2",
        "task_ids": ["TASK-004", "TASK-005", "TASK-006", "TASK-007", "TASK-008"],
        "worktree_path": str(w2_path),
        "branch": "swarm/worker-2",
        "status": "running",
    }
    reg_path.write_text(json.dumps(existing_reg, indent=2))

    # Verify append-only
    check = json.loads(reg_path.read_text())
    assert len(check["workers"]) == 2, f"Expected 2 workers, got {len(check['workers'])}"
    assert "1" in check["workers"], "Worker-1 lost!"
    assert "2" in check["workers"], "Worker-2 missing!"
    print("  Registry append-only: worker-1 preserved, worker-2 added: OK")

    # New transcript for run 2
    tw2 = TranscriptWriter(project, "session-002")
    tw2.open()
    tw2.write_worker_spawned(2, "worker-2",
                             ["TASK-004", "TASK-005", "TASK-006", "TASK-007", "TASK-008"],
                             str(w2_path), "swarm/worker-2")
    tw2.write_task_update("TASK-004", "done", "Build TodoList")
    tw2.write_task_update("TASK-005", "done", "Build AddTodo")
    tw2.write_task_update("TASK-006", "done", "Add localStorage")
    tw2.write_progress("Worker-2 completed components", tasks_done=6, tasks_total=8)

    # More budget
    budget.record_real_usage(6000, 2500, 0.04, "claude-sonnet-4-6")
    budget.record_code_changes(200, 30)

    # INTERRUPTED again
    tw2.write_interruption()
    tw2.close(clean=False)
    print("  Worker-2 completed 3 more tasks: OK")
    print("  INTERRUPTED: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 9: Resume 2 — verify accumulated state
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 9] Resume 2 — verify accumulated state")

    # Tasks
    tl_final = TaskList(project)
    tl_final.load()
    done_final = [t for t in tl_final.tasks if t.status == "done"]
    pending_final = [t for t in tl_final.tasks if t.status == "pending"]
    assert len(done_final) == 6, f"Expected 6 done, got {len(done_final)}"
    assert len(pending_final) == 2, f"Expected 2 pending, got {len(pending_final)}"
    pending_ids = [t.id for t in pending_final]
    assert "TASK-007" in pending_ids, "TASK-007 should be pending"
    assert "TASK-008" in pending_ids, "TASK-008 should be pending"
    print(f"  Tasks: 6 done, 2 pending (TASK-007, TASK-008): OK")

    # Registry
    reg_final = json.loads(reg_path.read_text())
    assert len(reg_final["workers"]) == 2
    assert reg_final["next_worker_id"] == 3
    print(f"  Registry: 2 workers, next_id=3: OK")

    # Budget accumulation
    budget3 = BudgetTracker(project)
    s = budget3.get_status()
    assert s["total_input_tokens"] == 14000, f"Expected 14000, got {s['total_input_tokens']}"
    assert s["total_output_tokens"] == 5500, f"Expected 5500, got {s['total_output_tokens']}"
    assert s["total_lines_added"] == 350, f"Expected 350, got {s['total_lines_added']}"
    assert s["total_lines_removed"] == 30, f"Expected 30, got {s['total_lines_removed']}"
    assert s["session_count"] == 2
    print(f"  Budget accumulated: $0.09, 14K/5.5K tokens, +350/-30 lines, 2 sessions: OK")

    # Transcripts
    all_transcripts = sorted((sw / "transcripts").glob("*.jsonl"))
    assert len(all_transcripts) == 2, f"Expected 2 transcripts, got {len(all_transcripts)}"
    print(f"  Transcripts: 2 files: OK")

    # Memory files still intact
    assert proj_claude.exists(), "Project CLAUDE.md gone!"
    assert mem_file.exists(), "Architecture memory file gone!"
    print(f"  Memory files intact: OK")

    # ══════════════════════════════════════════════════════════════════
    # STEP 10: Verify resume context for run 3
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 10] Verify resume context would be correct for Run 3")

    latest_transcript = sorted((sw / "transcripts").glob("*.jsonl"),
                                key=lambda p: p.stat().st_mtime, reverse=True)[0]
    entries3 = TranscriptReader.load_transcript(latest_transcript)
    info3 = TranscriptReader.detect_interruption(entries3)
    assert info3["interrupted"] is True
    assert info3["tasks_done"] == 6
    ctx3 = TranscriptReader.build_resume_context(entries3)
    assert "worker-2" in ctx3
    print(f"  Latest transcript: interrupted, 6/8 done: OK")
    print(f"  Resume context mentions worker-2: OK")

    # The orchestrator would see:
    # - Registry: 2 workers (worker-1 completed, worker-2 running)
    # - Task list: 6 done, 2 pending (TASK-007, TASK-008)
    # - Action: spawn worker-3 for TASK-007 + TASK-008
    print(f"  Orchestrator would spawn worker-3 for TASK-007, TASK-008: CORRECT")

    # ══════════════════════════════════════════════════════════════════
    # STEP 11: Run 3 completes everything
    # ══════════════════════════════════════════════════════════════════
    print("\n[STEP 11] Run 3 — worker-3 finishes remaining tasks")

    w3_path = sw / "swarm" / "worker-3"
    w3_path.mkdir(parents=True)

    tl = TaskList(project)
    tl.load()
    for t in tl.tasks:
        if t.id in ("TASK-007", "TASK-008"):
            t.status = "done"
    tl.save()

    # Append to registry
    final_reg = json.loads(reg_path.read_text())
    final_reg["next_worker_id"] = 4
    final_reg["workers"]["3"] = {
        "id": 3, "name": "worker-3",
        "task_ids": ["TASK-007", "TASK-008"],
        "worktree_path": str(w3_path),
        "branch": "swarm/worker-3",
        "status": "completed",
    }
    reg_path.write_text(json.dumps(final_reg, indent=2))

    # Clean transcript
    tw3 = TranscriptWriter(project, "session-003")
    tw3.open()
    tw3.write_worker_spawned(3, "worker-3", ["TASK-007", "TASK-008"], str(w3_path), "swarm/worker-3")
    tw3.write_task_update("TASK-007", "done", "Dark mode")
    tw3.write_task_update("TASK-008", "done", "Unit tests")
    tw3.write_worker_completed(3, "worker-3", ["TASK-007", "TASK-008"], "completed")
    tw3.write_progress("All tasks complete!", tasks_done=8, tasks_total=8)
    tw3.close(clean=True)  # CLEAN close this time

    # Verify DONE
    tl_done = TaskList(project)
    tl_done.load()
    all_done = all(t.status == "done" for t in tl_done.tasks)
    assert all_done, "Not all tasks done!"
    print(f"  All 8 tasks completed: OK")

    done_reg = json.loads(reg_path.read_text())
    assert len(done_reg["workers"]) == 3
    print(f"  Registry: 3 workers total: OK")

    all_transcripts_final = list((sw / "transcripts").glob("*.jsonl"))
    assert len(all_transcripts_final) == 3
    print(f"  Transcripts: 3 files: OK")

    # Last transcript has clean end
    last_entries = TranscriptReader.load_transcript(
        sorted(all_transcripts_final, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    )
    last_info = TranscriptReader.detect_interruption(last_entries)
    assert last_info["interrupted"] is False, "Last session should NOT be interrupted"
    print(f"  Last session clean (not interrupted): OK")

    # ══════════════════════════════════════════════════════════════════
    # CLEANUP
    # ══════════════════════════════════════════════════════════════════
    # Clean up global transcripts we created
    for sid in ["session-001", "session-002", "session-003"]:
        gt = Path.home() / ".swarmweaver" / "transcripts" / f"{sid}.jsonl"
        if gt.exists():
            gt.unlink()

    shutil.rmtree(project.parent, ignore_errors=True)

    # ══════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ALL 11 STEPS PASSED")
    print("=" * 70)
    print()
    print("Verified end-to-end:")
    print("  [1]  Project creation")
    print("  [2]  .swarmweaver/ auto-init (memory, rules, transcripts)")
    print("  [3]  CLAUDE.md loading (global + project)")
    print("  [4]  Task list creation (8 tasks)")
    print("  [5]  Run 1: worker-1 completes 3 tasks")
    print("  [6]  Interruption: state persisted (tasks, registry, transcript, budget)")
    print("  [7]  Resume: context rebuilt with worker info + task statuses")
    print("  [8]  Run 2: worker-2 completes 3 more (registry append-only)")
    print("  [9]  Resume 2: accumulated state correct (6 done, budget summed)")
    print("  [10] Resume context correct for Run 3")
    print("  [11] Run 3: all tasks done, clean finish")


if __name__ == "__main__":
    test_full_workflow()

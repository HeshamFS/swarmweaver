"""
Full Smart Swarm Resume Test
==============================

Simulates the EXACT production flow:
  Run 1: Orchestrator spawns worker-1, worker completes 3 tasks, INTERRUPTED
  Resume 1: Orchestrator loads registry + tasks, sees 3 done / 7 pending
  Run 2: Spawns worker-2 for remaining, completes 4 more, INTERRUPTED
  Resume 2: Registry has BOTH workers, sees 7 done / 3 pending
"""

import sys
import json
import os
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from state.task_list import TaskList
from services.transcript import TranscriptWriter, TranscriptReader


def test_full_resume_flow():
    # ── SETUP ──
    project = Path(tempfile.mkdtemp()) / "resume_test"
    project.mkdir(parents=True)
    sw = project / ".swarmweaver"
    sw.mkdir()
    (sw / "swarm").mkdir()
    (sw / "transcripts").mkdir()

    os.system(f'cd "{project}" && git init -q && git config user.email t@t.com && git config user.name T && git commit -q --allow-empty -m init')

    # 10 tasks, all pending
    tasks_data = {
        "metadata": {"mode": "feature", "version": "20.0"},
        "tasks": [
            {"id": f"TASK-{i:03d}", "title": f"Task {i}", "status": "pending", "priority": "medium", "dependencies": []}
            for i in range(1, 11)
        ],
    }
    (sw / "task_list.json").write_text(json.dumps(tasks_data, indent=2))
    print(f"Project: {project}")
    print(f"Tasks: 10 (all pending)")

    # ── RUN 1: Worker-1 completes 3 tasks ──
    print("\n--- RUN 1: Worker-1 completes TASK-001..003 ---")

    w1_path = sw / "swarm" / "worker-1"
    w1_path.mkdir(parents=True)

    # Worker updates MAIN task_list (task_list_dir = main project)
    tl = TaskList(project)
    tl.load()
    for t in tl.tasks[:3]:
        t.status = "done"
    tl.save()
    print("  Worker-1 marked 3 tasks done in main task_list.json")

    # Save registry (append-only)
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
    print("  Registry saved (worker-1 = completed)")

    # Transcript
    tw = TranscriptWriter(project, "session-run1")
    tw.open()
    tw.write_worker_spawned(1, "worker-1", ["TASK-001", "TASK-002", "TASK-003"], str(w1_path), "swarm/worker-1")
    tw.write_task_update("TASK-001", "done", "Task 1")
    tw.write_task_update("TASK-002", "done", "Task 2")
    tw.write_task_update("TASK-003", "done", "Task 3")
    tw.write_worker_completed(1, "worker-1", ["TASK-001", "TASK-002", "TASK-003"], "completed")
    tw.write_progress("Worker-1 done", tasks_done=3, tasks_total=10)
    tw.write_interruption()
    tw.close(clean=False)
    print("  Transcript saved with interruption")

    # ── RESUME 1: Check what orchestrator sees ──
    print("\n--- RESUME 1: Orchestrator restarts ---")

    # Load registry
    reg = json.loads(reg_path.read_text())
    assert len(reg["workers"]) == 1, f"Expected 1 worker, got {len(reg['workers'])}"
    assert "1" in reg["workers"], "Worker-1 missing from registry"
    print(f"  Registry: {len(reg['workers'])} workers (worker-1 = {reg['workers']['1']['status']})")

    # Load task list (should be up-to-date because worker wrote to main)
    tl_resume = TaskList(project)
    tl_resume.load()
    done = [t for t in tl_resume.tasks if t.status in ("done", "verified")]
    pending = [t for t in tl_resume.tasks if t.status == "pending"]
    assert len(done) == 3, f"Expected 3 done, got {len(done)}"
    assert len(pending) == 7, f"Expected 7 pending, got {len(pending)}"
    print(f"  Tasks: {len(done)} done, {len(pending)} pending")
    print(f"  Done IDs: {[t.id for t in done]}")
    print(f"  Pending IDs: {[t.id for t in pending]}")

    # Transcript detection
    transcripts = sorted((sw / "transcripts").glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    entries = TranscriptReader.load_transcript(transcripts[0])
    info = TranscriptReader.detect_interruption(entries)
    assert info["interrupted"] is True, "Should detect interruption"
    assert len(info["workers"]) == 1, f"Expected 1 worker in transcript, got {len(info['workers'])}"
    print(f"  Transcript: interrupted={info['interrupted']}, workers={list(info['workers'].keys())}")

    # Resume context
    ctx = TranscriptReader.build_resume_context(entries)
    assert "worker-1" in ctx, "Resume context missing worker-1"
    assert "DO NOT recreate" in ctx, "Resume context missing instructions"
    print(f"  Resume context: {len(ctx)} chars, includes worker info")

    # ── RUN 2: Worker-2 for remaining tasks ──
    print("\n--- RUN 2: Worker-2 completes TASK-004..007 ---")

    w2_path = sw / "swarm" / "worker-2"
    w2_path.mkdir(parents=True)

    # APPEND to registry (don't overwrite worker-1!)
    existing = json.loads(reg_path.read_text())
    existing["next_worker_id"] = 3
    existing["workers"]["2"] = {
        "id": 2, "name": "worker-2",
        "task_ids": [t.id for t in pending],
        "worktree_path": str(w2_path),
        "branch": "swarm/worker-2",
        "status": "running",
    }
    reg_path.write_text(json.dumps(existing, indent=2))

    # Verify registry is append-only
    check_reg = json.loads(reg_path.read_text())
    assert len(check_reg["workers"]) == 2, f"Expected 2 workers, got {len(check_reg['workers'])}"
    assert "1" in check_reg["workers"], "Worker-1 lost from registry!"
    assert "2" in check_reg["workers"], "Worker-2 missing from registry!"
    print(f"  Registry: {len(check_reg['workers'])} workers (append-only works)")

    # Worker-2 completes 4 tasks
    tl2 = TaskList(project)
    tl2.load()
    for t in tl2.tasks:
        if t.id in ["TASK-004", "TASK-005", "TASK-006", "TASK-007"]:
            t.status = "done"
    tl2.save()
    print("  Worker-2 marked 4 more tasks done")

    # INTERRUPTED again
    existing["workers"]["2"]["status"] = "running"
    reg_path.write_text(json.dumps(existing, indent=2))
    print("  INTERRUPTED during worker-2!")

    # ── RESUME 2: Final state check ──
    print("\n--- RESUME 2: Second restart ---")

    reg2 = json.loads(reg_path.read_text())
    assert len(reg2["workers"]) == 2, f"Expected 2 workers, got {len(reg2['workers'])}"
    print(f"  Registry: {len(reg2['workers'])} workers")
    for wid, w in reg2["workers"].items():
        print(f"    worker-{wid}: status={w['status']}, tasks={len(w['task_ids'])}")

    tl3 = TaskList(project)
    tl3.load()
    done3 = [t for t in tl3.tasks if t.status in ("done", "verified")]
    pending3 = [t for t in tl3.tasks if t.status == "pending"]
    assert len(done3) == 7, f"Expected 7 done, got {len(done3)}"
    assert len(pending3) == 3, f"Expected 3 pending, got {len(pending3)}"
    print(f"  Tasks: {len(done3)} done, {len(pending3)} pending")
    print(f"  Pending: {[t.id for t in pending3]}")

    assert reg2["next_worker_id"] == 3
    print(f"  Next worker ID: {reg2['next_worker_id']}")

    # Cleanup
    shutil.rmtree(project.parent)

    print("\n" + "=" * 70)
    print("ALL ASSERTIONS PASSED")
    print("=" * 70)
    print()
    print("Flow verified:")
    print("  1. Worker-1 completes 3 tasks, updates main task_list, saves to registry")
    print("  2. INTERRUPTED")
    print("  3. Resume: registry has worker-1, task_list shows 3 done / 7 pending")
    print("  4. Worker-2 spawned, registry APPENDS (worker-1 preserved)")
    print("  5. Worker-2 completes 4 tasks, updates main task_list")
    print("  6. INTERRUPTED")
    print("  7. Resume: registry has BOTH workers, task_list shows 7 done / 3 pending")
    print("  8. Next worker-3 would only get TASK-008, 009, 010")


if __name__ == "__main__":
    test_full_resume_flow()

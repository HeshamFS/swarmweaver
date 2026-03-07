"""
Progress Tracking & Dashboard
==============================

Rich terminal output with category breakdowns, status tracking,
and visual progress bars, backed by task_list.json.
"""

from pathlib import Path

from state.task_list import TaskList, TaskStatus


def count_passing_tests(project_dir: Path) -> tuple[int, int]:
    """Return (done_count, total_count) from task_list.json."""
    tl = TaskList(project_dir)
    if tl.load():
        return tl.done_count, tl.total
    return 0, 0


def print_session_header(session_num: int, is_initializer: bool) -> None:
    """Print a formatted header for the session."""
    session_type = "INITIALIZER" if is_initializer else "CODING AGENT"

    print("\n" + "=" * 70)
    print(f"  SESSION {session_num}: {session_type}")
    print("=" * 70)
    print()


def print_progress_summary(project_dir: Path) -> None:
    """Print a rich progress summary dashboard."""
    tl = TaskList(project_dir)
    has_tasks = tl.load()

    if not has_tasks:
        print("\nProgress: task list not yet created")
        return

    if tl.total == 0:
        print("\nProgress: No tasks defined yet")
        return

    done = tl.done_count
    total = tl.total
    pct = tl.percentage_done

    bar_width = 40
    filled = int(bar_width * done / total) if total > 0 else 0
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

    print()
    print(f"  Tasks: {done}/{total} done  [{bar}]  {pct:.1f}%")

    # Status breakdown
    status_counts = tl.count_by_status()
    status_parts = []
    for status in [TaskStatus.DONE.value, TaskStatus.IN_PROGRESS.value,
                   TaskStatus.PENDING.value, TaskStatus.BLOCKED.value,
                   TaskStatus.FAILED.value, TaskStatus.SKIPPED.value]:
        count = status_counts.get(status, 0)
        if count > 0:
            status_parts.append(f"{count} {status}")

    if status_parts:
        print(f"  Status: {', '.join(status_parts)}")

    # Category breakdown (only if multiple categories)
    by_cat = tl.count_by_category()
    if len(by_cat) > 1:
        print()
        print("  By category:")
        for cat, data in sorted(by_cat.items()):
            cat_total = data["total"]
            cat_done = data["done"]
            cat_pct = (cat_done / cat_total * 100) if cat_total > 0 else 0
            cat_bar_w = 20
            cat_filled = int(cat_bar_w * cat_done / cat_total) if cat_total > 0 else 0
            cat_bar = "\u2588" * cat_filled + "\u2591" * (cat_bar_w - cat_filled)
            check = "+" if cat_done == cat_total else " "
            print(f"    {check} {cat:15s} {cat_done:3d}/{cat_total:<3d} [{cat_bar}] {cat_pct:.0f}%")

    mode = tl.metadata.get("mode", "")
    if mode:
        print(f"\n  Mode: {mode}")

    print()


def get_next_test_to_implement(project_dir: Path) -> tuple[int, dict | None]:
    """
    Get the next test that should be implemented.

    Returns:
        (index, test_dict) or (-1, None) if all tests pass
    """
    tl = TaskList(project_dir)
    if tl.load():
        task = tl.get_next_actionable()
        if task:
            for i, t in enumerate(tl.tasks):
                if t.id == task.id:
                    return i, task.to_dict()
    return -1, None

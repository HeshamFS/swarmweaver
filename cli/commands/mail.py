"""CLI commands for inter-agent mail system."""

from pathlib import Path
from typing import Annotated, Optional

import typer

mail_app = typer.Typer(help="Inter-agent mail system")


def _get_store(project_dir: Path):
    from state.mail import MailStore
    store = MailStore(project_dir)
    if not store.db_path.exists():
        print("No mail database found. Run a swarm session first.")
        raise typer.Exit(1)
    store.initialize()
    return store


@mail_app.command("list")
def mail_list(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    recipient: Annotated[Optional[str], typer.Option("--recipient", "-r", help="Filter by recipient")] = None,
    msg_type: Annotated[Optional[str], typer.Option("--type", "-t", help="Filter by message type")] = None,
    unread: Annotated[bool, typer.Option("--unread", help="Only show unread messages")] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max messages to return")] = 30,
):
    """List inter-agent mail messages."""
    store = _get_store(project_dir)
    messages = store.get_messages(
        recipient=recipient, msg_type=msg_type,
        unread_only=unread, limit=limit,
    )
    store.close()

    if not messages:
        print("No messages found.")
        return

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()

        table = Table(title=f"Mail Messages ({len(messages)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("From", style="bold", min_width=12)
        table.add_column("To", min_width=12)
        table.add_column("Type", width=15)
        table.add_column("Subject", min_width=20)
        table.add_column("Priority", width=8)
        table.add_column("Read", width=5)
        table.add_column("Time", width=12)

        for m in messages:
            priority_style = ""
            if m.priority == "urgent":
                priority_style = "[red bold]"
            elif m.priority == "high":
                priority_style = "[yellow]"

            read_mark = "[green]Y[/]" if m.read else "[red]N[/]"
            time_str = m.created_at[11:19] if len(m.created_at) > 19 else m.created_at

            table.add_row(
                m.id[:8],
                m.sender,
                m.recipient,
                m.msg_type,
                m.subject[:40],
                f"{priority_style}{m.priority}",
                read_mark,
                time_str,
            )

        console.print(table)
    except ImportError:
        for m in messages:
            read_mark = " " if m.read else "*"
            time_str = m.created_at[11:19] if len(m.created_at) > 19 else ""
            print(f"  {read_mark} {m.id[:8]}  {m.sender:>15} -> {m.recipient:<15}  [{m.msg_type}] {m.subject[:40]}  {time_str}")


@mail_app.command("send")
def mail_send(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    to: Annotated[str, typer.Option("--to", help="Recipient address")] = "orchestrator",
    subject: Annotated[str, typer.Option("--subject", "-s", help="Message subject")] = "",
    body: Annotated[str, typer.Option("--body", "-b", help="Message body")] = "",
    msg_type: Annotated[str, typer.Option("--type", "-t", help="Message type")] = "status",
    priority: Annotated[str, typer.Option("--priority", help="Priority: low, normal, high, urgent")] = "normal",
):
    """Send an inter-agent mail message."""
    if not subject:
        print("--subject is required.")
        raise typer.Exit(1)

    store = _get_store(project_dir)
    msg_id = store.send(
        sender="cli-user",
        recipient=to,
        msg_type=msg_type,
        subject=subject,
        body=body,
        priority=priority,
    )
    store.close()
    print(f"Message sent: {msg_id}")


@mail_app.command("read")
def mail_read(
    msg_id: Annotated[Optional[str], typer.Argument(help="Message ID to mark as read")] = None,
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    all_for: Annotated[Optional[str], typer.Option("--all", help="Mark all read for this recipient")] = None,
):
    """Mark message(s) as read."""
    store = _get_store(project_dir)

    if all_for:
        count = store.mark_all_read(all_for)
        print(f"Marked {count} messages as read for {all_for}.")
    elif msg_id:
        ok = store.mark_read(msg_id)
        print(f"Marked {msg_id[:8]} as read." if ok else f"Message {msg_id[:8]} not found.")
    else:
        print("Provide a message ID or --all RECIPIENT.")

    store.close()


@mail_app.command("thread")
def mail_thread(
    thread_id: Annotated[str, typer.Argument(help="Thread ID to display")],
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Show a mail conversation thread in chronological order."""
    store = _get_store(project_dir)
    msgs = store.get_conversation(thread_id)
    store.close()

    if not msgs:
        print(f"No messages found for thread {thread_id[:8]}.")
        return

    try:
        from rich.console import Console
        from rich.panel import Panel
        console = Console()

        console.print(f"\n[bold]Thread {thread_id[:8]}[/] ({len(msgs)} messages)\n")
        for m in msgs:
            time_str = m.created_at[11:19] if len(m.created_at) > 19 else m.created_at
            header = f"[bold]{m.sender}[/] -> {m.recipient}  [{m.msg_type}]  {time_str}"
            body_text = f"[bold]{m.subject}[/]\n{m.body}" if m.body else f"[bold]{m.subject}[/]"
            console.print(Panel(body_text, title=header, border_style="dim"))
    except ImportError:
        print(f"\nThread {thread_id[:8]} ({len(msgs)} messages):")
        for m in msgs:
            time_str = m.created_at[11:19] if len(m.created_at) > 19 else ""
            print(f"  [{time_str}] {m.sender} -> {m.recipient} ({m.msg_type})")
            print(f"    Subject: {m.subject}")
            if m.body:
                print(f"    {m.body[:200]}")
            print()


@mail_app.command("stats")
def mail_stats(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
):
    """Show mail system statistics and analytics."""
    store = _get_store(project_dir)
    analytics = store.get_analytics()
    store.close()

    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        console = Console()

        # Summary
        lines = [
            f"Total messages: {analytics.get('total', 0)}",
            f"Unread: {analytics.get('unread', 0)}",
        ]

        avg_resp = analytics.get("avg_response_time_seconds")
        if avg_resp is not None:
            if avg_resp < 60:
                lines.append(f"Avg response time: {avg_resp:.1f}s")
            else:
                lines.append(f"Avg response time: {avg_resp / 60:.1f}m")
        else:
            lines.append("Avg response time: N/A")

        dead = analytics.get("dead_letter_count", 0)
        if dead > 0:
            lines.append(f"[red]Dead letters: {dead}[/]")
        else:
            lines.append(f"Dead letters: {dead}")

        console.print(Panel("\n".join(lines), title="Mail Analytics"))

        # By type
        by_type = analytics.get("by_type", {})
        if by_type:
            table = Table(title="Messages by Type")
            table.add_column("Type", style="bold")
            table.add_column("Count", justify="right")
            for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
                table.add_row(t, str(c))
            console.print(table)

        # Top senders
        top = analytics.get("top_senders", {})
        if top:
            table = Table(title="Top Senders")
            table.add_column("Sender", style="bold")
            table.add_column("Count", justify="right")
            for s, c in sorted(top.items(), key=lambda x: -x[1]):
                table.add_row(s, str(c))
            console.print(table)

        # Unread bottlenecks
        unread_by = analytics.get("unread_by_recipient", {})
        if unread_by:
            table = Table(title="Unread by Recipient")
            table.add_column("Recipient", style="bold")
            table.add_column("Unread", justify="right", style="yellow")
            for r, c in sorted(unread_by.items(), key=lambda x: -x[1]):
                table.add_row(r, str(c))
            console.print(table)

    except ImportError:
        print(f"Total: {analytics.get('total', 0)}, Unread: {analytics.get('unread', 0)}")
        print(f"Dead letters: {analytics.get('dead_letter_count', 0)}")
        avg_resp = analytics.get("avg_response_time_seconds")
        if avg_resp is not None:
            print(f"Avg response time: {avg_resp:.1f}s")
        by_type = analytics.get("by_type", {})
        if by_type:
            print("By type:", ", ".join(f"{t}={c}" for t, c in by_type.items()))


@mail_app.command("purge")
def mail_purge(
    project_dir: Annotated[Path, typer.Option("--project-dir", "-p", help="Project directory")] = Path("."),
    days: Annotated[int, typer.Option("--days", "-d", help="Delete read messages older than N days")] = 7,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
):
    """Delete old read messages."""
    store = _get_store(project_dir)

    if not yes:
        confirm = typer.confirm(f"Delete read messages older than {days} days?")
        if not confirm:
            print("Aborted.")
            store.close()
            return

    count = store.delete_old_messages(days=days)
    store.close()
    print(f"Deleted {count} old messages.")

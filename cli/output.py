"""Rich terminal output for the SwarmWeaver CLI."""

import time
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class RichEventRenderer:
    """Renders agent events using the rich library for colored, styled output."""

    def __init__(self, console=None):
        if not HAS_RICH:
            raise ImportError("rich is required for RichEventRenderer: pip install rich>=13.0")
        self.console = console or Console()
        self._tool_count = 0
        self._tool_start_times: dict[str, float] = {}

    async def on_event(self, event: dict) -> None:
        """Handle all event types with rich formatting."""
        etype = event.get("type", "")

        if etype == "text_delta":
            text = event.get("text", "")
            self.console.print(text, end="", highlight=False)

        elif etype == "output":
            self.console.print(event.get("data", ""))

        elif etype == "tool_start":
            tool = event.get("tool", event.get("data", {}).get("tool", "?"))
            file_path = event.get("file", event.get("data", {}).get("file", ""))
            self._tool_count += 1
            self._tool_start_times[tool] = time.monotonic()
            label = f"[dim][bold cyan]\u2192[/] {tool}[/]"
            if file_path:
                label += f" [dim italic]{file_path}[/]"
            self.console.print(f"  {label}")

        elif etype == "tool_done":
            tool = event.get("tool", event.get("data", {}).get("tool", "?"))
            elapsed = ""
            start = self._tool_start_times.pop(tool, None)
            if start is not None:
                dt = time.monotonic() - start
                if dt >= 1.0:
                    elapsed = f" [dim]({dt:.1f}s)[/]"
                else:
                    elapsed = f" [dim]({dt * 1000:.0f}ms)[/]"
            self.console.print(f"  [dim][bold green]\u2713[/] {tool}{elapsed}[/]")

        elif etype == "tool_error":
            tool = event.get("tool", event.get("data", {}).get("tool", "?"))
            error_msg = event.get("error", event.get("data", {}).get("error", "Unknown error"))
            self._tool_start_times.pop(tool, None)
            self.console.print(Panel(
                f"[bold]{tool}[/]\n{error_msg}",
                title="Tool Error",
                style="red",
                expand=False,
            ))

        elif etype == "phase_change":
            phase = event.get("data", {}).get("phase", "?")
            self.console.print()
            self.console.print(Panel(
                f"[bold]{phase.upper()}[/]",
                title="Phase",
                style="blue",
                expand=False,
            ))

        elif etype == "session_start":
            session = event.get("data", {}).get("session", "?")
            phase = event.get("data", {}).get("phase", "")
            self.console.print(f"\n[bold yellow]SESSION {session}[/] {phase}")

        elif etype == "session_error":
            error_msg = event.get("error", event.get("data", "Unknown session error"))
            self.console.print(Panel(
                str(error_msg),
                title="Session Error",
                style="bold red",
                expand=False,
            ))

        elif etype == "error":
            self.console.print(Panel(
                str(event.get("data", "")),
                title="Error",
                style="red",
                expand=False,
            ))

        elif etype == "status":
            self.console.print(f"\n[bold blue]STATUS[/] {event.get('data', '')}")

        elif etype == "task_list_update":
            data = event.get("data", {})
            completed = data.get("completed", 0)
            total = data.get("total", 0)
            in_progress = data.get("in_progress", 0)
            if total:
                pct = int(completed / total * 100)
                bar_width = 20
                filled = int(bar_width * completed / total)
                bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                parts = [f"[dim]Tasks: {completed}/{total} ({pct}%) [/]"]
                parts.append(f"[green]{bar}[/]")
                if in_progress:
                    parts.append(f" [yellow]{in_progress} in progress[/]")
                self.console.print("  " + "".join(parts))


class JsonEventRenderer:
    """Emits newline-delimited JSON events (for --json flag)."""

    async def on_event(self, event: dict) -> None:
        import json
        import sys
        print(json.dumps(event), flush=True)


def make_plain_on_event():
    """Returns the old print-based on_event callback (fallback when rich unavailable)."""

    async def on_event(event: dict) -> None:
        etype = event.get("type", "")
        if etype == "text_delta":
            print(event.get("text", ""), end="", flush=True)
        elif etype == "output":
            print(event.get("data", ""), flush=True)
        elif etype in ("tool_start", "tool_done"):
            tool = event.get("tool", event.get("data", {}).get("tool", "?"))
            status = "\u2192" if etype == "tool_start" else "\u2713"
            print(f"  [{status} {tool}]", flush=True)
        elif etype == "phase_change":
            phase = event.get("data", {}).get("phase", "?")
            print(f"\n[PHASE] {phase.upper()}", flush=True)
        elif etype == "session_start":
            session = event.get("data", {}).get("session", "?")
            phase = event.get("data", {}).get("phase", "")
            print(f"\n[SESSION {session}] {phase}", flush=True)
        elif etype in ("error", "session_error", "tool_error"):
            msg = event.get("data", event.get("error", ""))
            print(f"\n[ERROR] {msg}", flush=True)
        elif etype == "status":
            print(f"\n[STATUS] {event.get('data', '')}", flush=True)
        elif etype == "task_list_update":
            data = event.get("data", {})
            completed = data.get("completed", 0)
            total = data.get("total", 0)
            if total:
                pct = int(completed / total * 100)
                print(f"  [Tasks: {completed}/{total} ({pct}%)]", flush=True)

    return on_event

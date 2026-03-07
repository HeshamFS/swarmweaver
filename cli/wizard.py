"""Interactive pre-planning wizard for CLI."""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


class CLIWizard:
    """Interactive wizard that runs before the agent to refine task input."""

    def __init__(self, console=None):
        if HAS_RICH:
            self.console = console or Console()
        else:
            self.console = None

    async def run(
        self,
        mode: str,
        task_input: str,
        project_dir: Path,
        model: str | None = None,
    ) -> Optional[str]:
        """Run interactive wizard. Returns refined task_input or None to cancel."""
        from core.models import DEFAULT_MODEL
        model = model or DEFAULT_MODEL
        self._print_header(mode, task_input)

        # Step 1: Generate QA questions
        self._print("[dim]Generating clarifying questions...[/]")
        questions = await _generate_qa_questions(mode, task_input, model)

        if not questions:
            self._print("[yellow]Could not generate questions. Proceeding with original input.[/]")
            return task_input

        # Step 2: Collect answers
        answers = self._collect_answers(questions)

        # Step 3: Build refined task description
        refined = self._build_refined_input(task_input, questions, answers)

        # Step 4: Show summary and confirm
        self._print_summary(refined)

        proceed = self._confirm("Proceed with this task description?", default=True)
        if proceed:
            return refined

        # Allow editing
        edit = self._confirm("Edit the description?", default=True)
        if edit:
            feedback = self._prompt("Enter your corrections or additions")
            refined = f"{refined}\n\nAdditional notes: {feedback}"
            return refined

        return None

    def _print_header(self, mode: str, task_input: str) -> None:
        if self.console:
            self.console.print()
            self.console.print(Panel(
                f"[bold]Mode:[/] {mode}\n[bold]Task:[/] {task_input}",
                title="Interactive Wizard",
                style="cyan",
                expand=False,
            ))
        else:
            print(f"\n=== Interactive Wizard ===")
            print(f"Mode: {mode}")
            print(f"Task: {task_input}")

    def _print(self, text: str) -> None:
        if self.console:
            self.console.print(text)
        else:
            # Strip rich markup for plain output
            clean = re.sub(r'\[/?[^\]]*\]', '', text)
            print(clean)

    def _prompt(self, text: str, default: str = "") -> str:
        if self.console and HAS_RICH:
            return Prompt.ask(text, default=default or None) or default
        else:
            suffix = f" [{default}]" if default else ""
            result = input(f"{text}{suffix}: ").strip()
            return result or default

    def _confirm(self, text: str, default: bool = True) -> bool:
        if self.console and HAS_RICH:
            return Confirm.ask(text, default=default)
        else:
            suffix = " [Y/n]" if default else " [y/N]"
            result = input(f"{text}{suffix}: ").strip().lower()
            if not result:
                return default
            return result in ("y", "yes")

    def _collect_answers(self, questions: list[dict]) -> list[str]:
        answers = []
        self._print("\n[bold]Please answer these questions to help the agent:[/]\n")
        for i, q in enumerate(questions, 1):
            question_text = q.get("question", "")
            options = q.get("options", [])

            self._print(f"[bold cyan]{i}.[/] {question_text}")

            if options:
                for j, opt in enumerate(options, 1):
                    label = opt.get("label", f"Option {j}")
                    desc = opt.get("description", "")
                    if desc:
                        self._print(f"   [dim]{j})[/] {label} - [dim]{desc}[/]")
                    else:
                        self._print(f"   [dim]{j})[/] {label}")

            answer = self._prompt("  Your answer")
            answers.append(answer)
            self._print("")

        return answers

    def _build_refined_input(
        self, original: str, questions: list[dict], answers: list[str]
    ) -> str:
        parts = [original, "", "--- Clarifications ---"]
        for q, a in zip(questions, answers):
            if a:
                parts.append(f"Q: {q.get('question', '')}")
                parts.append(f"A: {a}")
                parts.append("")
        return "\n".join(parts)

    def _print_summary(self, refined: str) -> None:
        if self.console:
            self.console.print()
            self.console.print(Panel(
                refined,
                title="Refined Task Description",
                style="green",
                expand=False,
            ))
        else:
            print("\n=== Refined Task Description ===")
            print(refined)
            print("================================")


async def _generate_qa_questions(
    mode: str, task_input: str, model: str
) -> list[dict]:
    """Generate clarifying questions via Claude CLI subprocess.

    Uses asyncio.create_subprocess_exec (no shell) for safe argument passing.
    """
    prompt = (
        f"You are helping plan a {mode} task for an autonomous coding agent.\n"
        f"Task: {task_input}\n\n"
        f"Generate 2-4 clarifying questions to help the agent succeed.\n"
        f'Return JSON only: {{"questions": [{{"question": "...", "options": '
        f'[{{"label": "...", "description": "..."}}]}}]}}'
    )

    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    # Arguments passed as a list to create_subprocess_exec (no shell injection risk)
    cmd = [
        "claude", "-p", "--model", model, "--output-format", "text",
        "--no-session-persistence", "--tools", "",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()), timeout=60
        )
        text = stdout.decode("utf-8", errors="replace").strip()

        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', text)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("questions", [])
    except (asyncio.TimeoutError, FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    return []

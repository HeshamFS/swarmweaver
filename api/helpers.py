"""Shared helper functions and schemas used across API routers and WebSocket handlers."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, WebSocket

from api.models import QAOption, QAQuestion, QAResponse
from core.models import DEFAULT_MODEL, FAST_MODEL


# JSON Schema for SDK structured output (matches QAResponse format)
QA_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "skip_reason": {
            "type": "string",
            "description": "Reason to skip QA questions (empty string if questions are provided)"
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The clarifying question"},
                    "context": {"type": "string", "description": "Why this question matters"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "Short option label"},
                                "description": {"type": "string", "description": "Option details"}
                            },
                            "required": ["label", "description"],
                            "additionalProperties": False
                        },
                        "description": "2-5 answer options"
                    }
                },
                "required": ["question", "options"],
                "additionalProperties": False
            },
            "description": "Clarifying questions (empty array if skip_reason is set)"
        }
    },
    "required": ["skip_reason", "questions"],
    "additionalProperties": False
}


# Schema for architect clarifying questions (reuses QA format)
ARCHITECT_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "A clarifying question based on your research"},
                    "context": {"type": "string", "description": "Why this question matters (reference what you found in research)"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "Short option label"},
                                "description": {"type": "string", "description": "Option details"}
                            },
                            "required": ["label", "description"],
                            "additionalProperties": False
                        },
                        "description": "2-4 answer options"
                    }
                },
                "required": ["question", "context", "options"],
                "additionalProperties": False
            },
            "description": "2-4 clarifying questions informed by web research"
        }
    },
    "required": ["questions"],
    "additionalProperties": False
}


async def _lightweight_claude_call(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    cwd: Optional[str] = None,
    timeout_seconds: int = 180,
    disable_tools: bool = False,
    json_schema: dict | None = None,
) -> str:
    """Run a lightweight `claude -p` subprocess call.

    Same isolation pattern as the QA endpoint: strips CLAUDECODE env var,
    uses --no-session-persistence, runs as an isolated subprocess.
    Returns the raw stdout text.

    Args:
        disable_tools: If True, passes --tools "" to disable all tools
                       (prevents file exploration, makes responses faster).
        json_schema: If provided, passes --json-schema for structured output.
    """
    clean_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    cmd = ["claude", "-p", "--model", model, "--output-format", "text", "--no-session-persistence"]
    if disable_tools:
        cmd.extend(["--tools", ""])
    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])
    if cwd:
        cmd.extend(["--cwd", cwd])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=clean_env,
        start_new_session=True,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail="Lightweight call timed out.")

    if proc.returncode != 0:
        error_msg = stderr_bytes.decode("utf-8", errors="replace").strip()
        if "auth" in error_msg.lower() or "unauthorized" in error_msg.lower():
            raise HTTPException(status_code=401, detail="Authentication failed. Check CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY.")
        if "rate" in error_msg.lower() and "limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail="Rate limited.")
        raise HTTPException(status_code=500, detail=f"Claude call failed: {error_msg[:500]}")

    return stdout_bytes.decode("utf-8", errors="replace").strip()


async def _generate_qa_via_sdk(prompt: str, *, model: str = FAST_MODEL, timeout_seconds: int = 75) -> dict | None:
    """Generate QA questions using the Agent SDK's query() with structured outputs.

    Uses output_format for structured JSON and max_turns=3 to allow the
    StructuredOutput tool call to complete. Returns the structured dict,
    or None on failure (triggers fallback to CLI).
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
    except ImportError:
        return None

    # Strip CLAUDECODE env var so the SDK subprocess doesn't refuse to start
    os.environ.pop("CLAUDECODE", None)

    try:
        options = ClaudeAgentOptions(
            model=model,
            system_prompt=(
                "You are a pre-execution setup assistant for an autonomous coding agent. "
                "Analyze the user's request and produce structured JSON with either clarifying "
                "questions or a skip_reason. Be concise and practical."
            ),
            tools=[],
            max_turns=3,
            output_format={
                "type": "json_schema",
                "schema": QA_OUTPUT_SCHEMA,
            },
        )

        async def _run():
            result = None
            async for msg in query(prompt=prompt, options=options):
                if type(msg).__name__ == "ResultMessage":
                    if hasattr(msg, "structured_output") and msg.structured_output:
                        result = msg.structured_output
            return result

        return await asyncio.wait_for(_run(), timeout=timeout_seconds)

    except asyncio.TimeoutError:
        return None
    except Exception:
        return None


async def _architect_research_via_sdk(
    idea: str, *, model: str, cwd: str | None = None,
    send_event,
) -> tuple[list[dict] | None, str]:
    """Phase 1: Research the idea and generate clarifying questions.

    Sends tool events via send_event callback during research.
    Fully consumes the query() generator to avoid cancel-scope issues.

    Returns: (questions_list_or_None, accumulated_thinking_text)
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import StreamEvent
    except ImportError:
        raise RuntimeError("claude_agent_sdk not installed")

    os.environ.pop("CLAUDECODE", None)

    current_date = datetime.now().strftime("%Y-%m-%d")

    prompt = (
        f"The user wants to build: {idea}\n\n"
        f"Today's date is {current_date}.\n\n"
        "STEP 1: Research this idea using web search. Look up:\n"
        "- Best current frameworks and libraries for this type of project\n"
        "- Latest best practices and patterns\n"
        "- Any relevant recent changes in the ecosystem\n"
        "Do 3-8 web searches depending on complexity.\n\n"
        "STEP 2: Based on your research, generate 2-4 clarifying questions "
        "to ask the user BEFORE writing the specification. These questions "
        "should be informed by what you found in your research. For example:\n"
        "- If you found multiple good framework options, ask which they prefer\n"
        "- If the project could go simple or complex, ask about scope\n"
        "- Ask about specific design/UX preferences\n"
        "- Ask about deployment and infrastructure preferences\n\n"
        "Each question should have 2-4 concrete options based on your research findings. "
        "Reference what you learned in the context field."
    )

    options = ClaudeAgentOptions(
        model=model,
        allowed_tools=["WebSearch", "WebFetch", "Read", "Glob", "Grep"],
        permission_mode="bypassPermissions",
        max_turns=10,
        include_partial_messages=True,
        output_format={"type": "json_schema", "schema": ARCHITECT_QUESTIONS_SCHEMA},
    )

    if cwd:
        options.cwd = cwd

    accumulated_text = ""
    current_tool_name = None
    current_tool_id = None
    questions_data = None

    # Fully consume the generator — never break early to avoid cancel-scope errors
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool_name = content_block.get("name", "Unknown")
                    current_tool_id = content_block.get("id", "")
                    await send_event({"type": "tool_start", "tool": current_tool_name, "id": current_tool_id})

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    accumulated_text += delta.get("text", "")
                elif delta.get("type") == "input_json_delta":
                    chunk = delta.get("partial_json", "")
                    if current_tool_id:
                        await send_event({"type": "tool_input_delta", "id": current_tool_id, "chunk": chunk})

            elif event_type == "content_block_stop":
                # Do NOT emit tool_done here — tool_done when we have ToolResultBlock
                if current_tool_name:
                    current_tool_name = None
                    current_tool_id = None

        elif type(message).__name__ == "UserMessage" and hasattr(message, "content"):
            content = message.content
            if not isinstance(content, str):
                for block in content:
                    if type(block).__name__ == "ToolResultBlock":
                        tool_use_id = getattr(block, "tool_use_id", "")
                        is_error = getattr(block, "is_error", False)
                        result_content = getattr(block, "content", "")
                        if is_error:
                            await send_event({"type": "tool_error", "id": tool_use_id, "error": str(result_content)[:500]})
                        else:
                            text_parts = []
                            if isinstance(result_content, list):
                                for b in result_content:
                                    if isinstance(b, dict) and b.get("type") == "text":
                                        text_parts.append(b.get("text", ""))
                            content_str = "\n".join(text_parts) if text_parts else str(result_content)
                            await send_event({"type": "tool_result", "id": tool_use_id, "status": "success", "content": content_str[:2048]})
                        await send_event({"type": "tool_done", "id": tool_use_id})

        elif type(message).__name__ == "ResultMessage":
            if hasattr(message, "structured_output") and message.structured_output:
                questions_data = message.structured_output.get("questions", []) or None

    return questions_data, accumulated_text


async def _architect_spec_via_sdk(
    prompt: str, *, model: str, cwd: str | None = None,
    send_event,
) -> str:
    """Phase 2: Generate the specification with streaming text.

    Sends text_delta and complete events via send_event callback.
    Fully consumes the query() generator to avoid cancel-scope issues.

    Returns: the full accumulated spec text.
    """
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import StreamEvent
    except ImportError:
        raise RuntimeError("claude_agent_sdk not installed")

    os.environ.pop("CLAUDECODE", None)

    options = ClaudeAgentOptions(
        model=model,
        tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        include_partial_messages=True,
    )

    if cwd:
        options.cwd = cwd

    accumulated_text = ""
    sent_complete = False

    # Fully consume the generator — never break early
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    accumulated_text += text
                    await send_event({"type": "text_delta", "text": text})

        elif type(message).__name__ == "ResultMessage":
            await send_event({"type": "complete", "text": accumulated_text})
            sent_complete = True

    # Guarantee "complete" is always sent even if no ResultMessage was yielded
    if not sent_complete and accumulated_text:
        await send_event({"type": "complete", "text": accumulated_text})

    return accumulated_text


def _normalize_qa_result(data: dict) -> dict:
    """Validate and normalize a structured QA output dict into a QAResponse."""
    if not isinstance(data, dict):
        return QAResponse(skip_reason="Invalid QA output. Proceeding directly.").model_dump()

    skip_reason = data.get("skip_reason", "")
    if skip_reason:
        return QAResponse(skip_reason=skip_reason).model_dump()

    questions = []
    for q in data.get("questions", []):
        options = [
            QAOption(label=opt.get("label", ""), description=opt.get("description", ""))
            for opt in q.get("options", [])
            if opt.get("label")
        ]
        if q.get("question") and options:
            questions.append(QAQuestion(
                question=q["question"],
                options=options,
                context=q.get("context", ""),
            ))

    if not questions:
        return QAResponse(skip_reason="No clarifying questions needed.").model_dump()

    return QAResponse(questions=questions).model_dump()


def _parse_json_response(text: str) -> dict:
    """Extract a JSON object from LLM output, stripping markdown fences and extra text."""
    import re as _re

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Extract JSON object
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start < 0 or json_end <= json_start:
        raise HTTPException(status_code=500, detail="Could not parse JSON from model output.")

    json_str = text[json_start:json_end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Retry 1: strip ALL control chars except \n (keeps JSON structure intact)
        cleaned = _re.sub(r'[\x00-\x09\x0b-\x1f\x7f]', ' ', json_str)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Retry 2: also normalise \r\n -> \n and strip remaining bad chars
        cleaned2 = cleaned.replace('\r\n', '\n').replace('\r', '\n')
        try:
            return json.loads(cleaned2)
        except json.JSONDecodeError:
            pass

        # Retry 3: for very large plans, try to find and parse just the "tasks" array
        tasks_match = _re.search(r'"tasks"\s*:\s*(\[.*?\])\s*[,}]', cleaned2, _re.DOTALL)
        if tasks_match:
            try:
                tasks = json.loads(tasks_match.group(1))
                return {"tasks": tasks}
            except json.JSONDecodeError:
                pass

        # Retry 4: extract individual task objects with a simple pattern
        task_objects = _re.findall(r'\{[^{}]*"id"\s*:\s*"[^"]*"[^{}]*\}', cleaned2)
        if len(task_objects) >= 2:
            tasks = []
            for obj in task_objects:
                try:
                    tasks.append(json.loads(obj))
                except json.JSONDecodeError:
                    pass
            if tasks:
                return {"tasks": tasks}

        raise HTTPException(status_code=500, detail="Invalid JSON from model (plan too large or malformed). Try a simpler project description.")


def _extract_questions_from_text(text: str) -> list[dict] | None:
    """Extract architect questions JSON from research response text."""
    import re

    # Strategy 1: look for ```json fenced blocks
    fenced = re.findall(r"```json\s*\n(.*?)```", text, re.DOTALL)
    for block in fenced:
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "questions" in data and data["questions"]:
                return data["questions"]
        except (json.JSONDecodeError, TypeError):
            continue

    # Strategy 2: try generic JSON extraction
    try:
        data = _parse_json_response(text)
        if isinstance(data, dict) and "questions" in data and data["questions"]:
            return data["questions"]
    except Exception:
        pass

    return None


async def _stream_wizard_response(client, websocket: WebSocket, text_type: str) -> str:
    """Consume client.receive_response() and stream events to the WebSocket."""
    from claude_agent_sdk.types import StreamEvent

    accumulated_text = ""
    current_tool_name = None
    current_tool_id = None

    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_start":
                content_block = event.get("content_block", {})
                if content_block.get("type") == "tool_use":
                    current_tool_name = content_block.get("name", "Unknown")
                    current_tool_id = content_block.get("id", "")
                    await websocket.send_json({
                        "type": "tool_start",
                        "tool": current_tool_name,
                        "id": current_tool_id,
                    })

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    accumulated_text += text
                    await websocket.send_json({
                        "type": "text_delta",
                        "text": text,
                        "text_type": text_type,
                    })
                elif delta.get("type") == "input_json_delta":
                    chunk = delta.get("partial_json", "")
                    if current_tool_id:
                        await websocket.send_json({
                            "type": "tool_input_delta",
                            "id": current_tool_id,
                            "chunk": chunk,
                        })

            elif event_type == "content_block_stop":
                # Do NOT emit tool_done here — tool_done when we have ToolResultBlock
                if current_tool_name:
                    current_tool_name = None
                    current_tool_id = None

        elif type(message).__name__ == "UserMessage" and hasattr(message, "content"):
            content = message.content
            if not isinstance(content, str):
                for block in content:
                    if type(block).__name__ == "ToolResultBlock":
                        tool_use_id = getattr(block, "tool_use_id", "")
                        is_error = getattr(block, "is_error", False)
                        result_content = getattr(block, "content", "")
                        if is_error:
                            await websocket.send_json({
                                "type": "tool_error",
                                "id": tool_use_id,
                                "error": str(result_content)[:500],
                            })
                        else:
                            # Extract text from content blocks
                            text_parts = []
                            if isinstance(result_content, list):
                                for b in result_content:
                                    if isinstance(b, dict) and b.get("type") == "text":
                                        text_parts.append(b.get("text", ""))
                            content_str = "\n".join(text_parts) if text_parts else str(result_content)
                            await websocket.send_json({
                                "type": "tool_result",
                                "id": tool_use_id,
                                "status": "success",
                                "content": content_str[:2048],
                            })
                        await websocket.send_json({
                            "type": "tool_done",
                            "id": tool_use_id,
                        })

    return accumulated_text


def _load_lightweight_prompt(name: str) -> str:
    """Load a lightweight prompt template from prompts/lightweight/."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "lightweight" / f"{name}.md"
    if not prompt_path.exists():
        raise HTTPException(status_code=500, detail=f"Prompt template not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _build_plan_prompt(
    mode: str,
    task_input: str,
    spec: Optional[str] = None,
    codebase_profile: Optional[dict] = None,
    feedback: Optional[str] = None,
    previous_tasks: Optional[dict] = None,
    **kwargs,
) -> str:
    """Build the planner prompt with optional analysis preamble and regeneration context."""
    if mode == "greenfield":
        if not spec:
            raise HTTPException(status_code=400, detail="Spec is required for greenfield planning.")
        template = _load_lightweight_prompt("initializer")
        prompt = template.replace("{spec}", spec).replace("{task_input}", task_input.strip())
    else:
        if mode == "feature":
            template = _load_lightweight_prompt("feature-planner")
            profile_str = json.dumps(codebase_profile, indent=2) if codebase_profile else "{}"
            prompt = template.replace("{codebase_profile}", profile_str).replace("{task_input}", task_input.strip())
        elif mode == "refactor":
            template = _load_lightweight_prompt("refactor-planner")
            profile_str = json.dumps(codebase_profile, indent=2) if codebase_profile else "{}"
            prompt = template.replace("{codebase_profile}", profile_str).replace("{task_input}", task_input.strip())
            if kwargs.get("strategy"):
                prompt = prompt.replace("{strategy}", kwargs["strategy"])
            else:
                prompt = prompt.replace("{strategy}", "(No strategy provided)")
        elif mode == "fix":
            template = _load_lightweight_prompt("fix-planner")
            profile_str = json.dumps(codebase_profile, indent=2) if codebase_profile else "{}"
            prompt = template.replace("{codebase_profile}", profile_str).replace("{task_input}", task_input.strip())
            if kwargs.get("investigation_summary"):
                prompt = prompt.replace("{investigation_summary}", kwargs["investigation_summary"])
            else:
                prompt = prompt.replace("{investigation_summary}", "(No investigation summary)")
        elif mode == "evolve":
            template = _load_lightweight_prompt("evolve-planner")
            profile_str = json.dumps(codebase_profile, indent=2) if codebase_profile else "{}"
            prompt = template.replace("{codebase_profile}", profile_str).replace("{task_input}", task_input.strip())
            if kwargs.get("audit_summary"):
                prompt = prompt.replace("{audit_summary}", kwargs["audit_summary"])
            else:
                prompt = prompt.replace("{audit_summary}", "(No audit summary)")
        elif mode == "security":
            template = _load_lightweight_prompt("security-planner")
            prompt = template.replace("{task_input}", task_input.strip())
            if kwargs.get("security_findings"):
                prompt = prompt.replace("{security_findings}", kwargs["security_findings"])
            else:
                prompt = prompt.replace("{security_findings}", "[]")
        else:
            template = _load_lightweight_prompt("planner")
            profile_str = json.dumps(codebase_profile, indent=2) if codebase_profile else "{}"
            prompt = template.replace("{codebase_profile}", profile_str).replace("{task_input}", task_input.strip())

    analysis_preamble = (
        "Before producing the JSON task list, write a brief analysis (2-4 sentences) "
        "explaining your approach: what you identified as the key areas, how you "
        "structured the tasks, and any important decisions you made. "
        "Then output the JSON task list.\n\n"
    )
    prompt = analysis_preamble + prompt

    if feedback and previous_tasks:
        prompt += (
            "\n\n--- REGENERATION REQUEST ---\n"
            "The user reviewed the previous task list and wants changes.\n\n"
            f"Previous task list:\n```json\n{json.dumps(previous_tasks, indent=2)}\n```\n\n"
            f"User feedback: {feedback}\n\n"
            "Generate an updated task list that addresses the user's feedback. "
            "Keep tasks that are still relevant, modify or remove tasks as requested, "
            "and add new tasks if needed."
        )

    return prompt


def _build_analysis_prompt(mode: str, task_input: str, qa_answers_text: str = "") -> str:
    """Build codebase analysis prompt for feature/refactor/evolve wizard turns."""
    template = _load_lightweight_prompt("analyzer")
    prompt = template.replace("{task_input}", task_input.strip())

    mode_focus = {
        "feature": "Focus on understanding patterns, integration points, and testing infrastructure relevant to the requested feature.",
        "refactor": "Focus on understanding the current architecture, dependencies, and potential migration paths.",
        "evolve": "Focus on understanding code quality, test coverage, performance patterns, and areas that need improvement.",
    }
    prompt += f"\n\nMODE-SPECIFIC FOCUS ({mode}):\n{mode_focus.get(mode, '')}"

    if qa_answers_text:
        prompt += f"\n\n--- USER PREFERENCES ---\n{qa_answers_text}\n"
    return prompt


def _build_investigation_prompt(task_input: str, qa_answers_text: str = "") -> str:
    """Build bug investigation prompt for fix wizard Turn 1."""
    template = _load_lightweight_prompt("fix-investigator")
    prompt = template.replace("{task_input}", task_input.strip())
    if qa_answers_text:
        prompt += f"\n\n--- USER CONTEXT ---\n{qa_answers_text}\n"
    return prompt


def _build_audit_prompt(task_input: str, qa_answers_text: str = "") -> str:
    """Build audit prompt for evolve wizard Turn 1."""
    template = _load_lightweight_prompt("evolve-auditor")
    prompt = template.replace("{task_input}", task_input.strip())
    if qa_answers_text:
        prompt += f"\n\n--- USER PREFERENCES ---\n{qa_answers_text}\n"
    return prompt


def _build_security_scan_prompt(task_input: str, qa_answers_text: str = "") -> str:
    """Build security scan prompt for security wizard Turn 1."""
    template = _load_lightweight_prompt("scanner")
    current_date = datetime.now().strftime("%Y-%m-%d")
    prompt = template.replace("{task_input}", task_input.strip()).replace("{current_date}", current_date)
    if qa_answers_text:
        prompt += f"\n\n--- USER PREFERENCES ---\n{qa_answers_text}\n"
    return prompt


def _build_strategy_prompt(task_input: str, analysis_text: str, answers_text: str = "") -> str:
    """Build refactor strategy generation prompt."""
    prompt = (
        "IMPORTANT: Do NOT use any tools for this step. Generate the strategy directly as text output.\n\n"
        "Based on your analysis of the codebase, generate a detailed migration/refactoring strategy.\n\n"
        f"REFACTORING GOAL: {task_input}\n\n"
        "Include:\n"
        "1. Overall approach (incremental vs. big-bang)\n"
        "2. Migration phases with ordering\n"
        "3. Risk areas and mitigation strategies\n"
        "4. Interop/compatibility approach during migration\n"
        "5. Testing strategy for each phase\n"
        "6. Rollback plan\n\n"
        "Write the strategy in clear markdown format."
    )
    if analysis_text:
        prompt += f"\n\n--- ANALYSIS FINDINGS ---\n{analysis_text[:6000]}\n"
    if answers_text:
        prompt += f"\n\n--- USER PREFERENCES ---\n{answers_text}\n"
    return prompt


def _build_report_prompt(mode: str, task_input: str, analysis_text: str) -> str:
    """Build investigation/audit report generation prompt."""
    if mode == "fix":
        prompt = (
            "IMPORTANT: Do NOT use any tools for this step. Generate the report directly as text output.\n\n"
            "Based on your investigation, write a concise bug investigation report.\n\n"
            f"REPORTED ISSUE: {task_input}\n\n"
            "Include:\n"
            "1. Root cause analysis\n"
            "2. Affected code paths and files\n"
            "3. Steps to reproduce\n"
            "4. Potential fix approach\n"
            "5. Risk of side effects\n\n"
            "Write in clear markdown format."
        )
    else:  # evolve
        prompt = (
            "IMPORTANT: Do NOT use any tools for this step. Generate the report directly as text output.\n\n"
            "Based on your audit, write a concise audit report.\n\n"
            f"IMPROVEMENT GOAL: {task_input}\n\n"
            "Include:\n"
            "1. Current state assessment\n"
            "2. Key findings organized by priority\n"
            "3. Specific areas needing improvement\n"
            "4. Quick wins vs. long-term improvements\n"
            "5. Recommended approach\n\n"
            "Write in clear markdown format."
        )
    if analysis_text:
        prompt += f"\n\n--- ANALYSIS FINDINGS ---\n{analysis_text[:6000]}\n"
    return prompt


async def _plan_via_sdk(prompt: str, model: str, send_event, cwd: str | None = None) -> str:
    """Stream planner output via Agent SDK (no tools, pure thinking)."""
    try:
        from claude_agent_sdk import query, ClaudeAgentOptions
        from claude_agent_sdk.types import StreamEvent
    except ImportError:
        raise RuntimeError("claude_agent_sdk not installed")

    os.environ.pop("CLAUDECODE", None)

    options = ClaudeAgentOptions(
        model=model,
        tools=[],
        permission_mode="bypassPermissions",
        max_turns=3,
        include_partial_messages=True,
    )

    if cwd:
        options.cwd = cwd

    accumulated_text = ""
    sent_complete = False

    # Fully consume the generator — never break early
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, StreamEvent):
            event = message.event
            event_type = event.get("type")

            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    accumulated_text += text
                    await send_event({"type": "text_delta", "text": text})

        elif type(message).__name__ == "ResultMessage":
            await send_event({"type": "complete", "text": accumulated_text})
            sent_complete = True

    if not sent_complete and accumulated_text:
        await send_event({"type": "complete", "text": accumulated_text})

    return accumulated_text


def _parse_qa_response(response_text: str) -> dict:
    """Parse the raw LLM response into a QAResponse dict."""
    if response_text.startswith("```"):
        resp_lines = response_text.split("\n")
        resp_lines = [l for l in resp_lines if not l.strip().startswith("```")]
        response_text = "\n".join(resp_lines).strip()

    json_start = response_text.find("{")
    json_end = response_text.rfind("}") + 1
    if json_start < 0 or json_end <= json_start:
        return QAResponse(skip_reason="Could not parse questions. Proceeding directly.").model_dump()

    response_text = response_text[json_start:json_end]

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return QAResponse(skip_reason="Could not parse questions. Proceeding directly.").model_dump()

    if "skip_reason" in data and data["skip_reason"]:
        return QAResponse(skip_reason=data["skip_reason"]).model_dump()

    questions = []
    for q in data.get("questions", []):
        options = [
            QAOption(label=opt.get("label", ""), description=opt.get("description", ""))
            for opt in q.get("options", [])
            if opt.get("label")
        ]
        if q.get("question") and options:
            questions.append(QAQuestion(
                question=q["question"],
                options=options,
                context=q.get("context", ""),
            ))

    if not questions:
        return QAResponse(skip_reason="No clarifying questions needed.").model_dump()

    return QAResponse(questions=questions).model_dump()

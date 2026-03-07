"""WebSocket handlers for /ws/architect, /ws/plan, and /ws/wizard."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.models import DEFAULT_MODEL, FAST_MODEL

from api.helpers import (
    _architect_research_via_sdk, _architect_spec_via_sdk,
    _build_plan_prompt, _build_analysis_prompt, _build_investigation_prompt,
    _build_audit_prompt, _build_security_scan_prompt, _build_strategy_prompt,
    _build_report_prompt, _plan_via_sdk,
    _extract_questions_from_text, _load_lightweight_prompt,
    _parse_json_response, _stream_wizard_response,
)

router = APIRouter()


@router.websocket("/ws/architect")
async def ws_architect(websocket: WebSocket):
    """WebSocket endpoint that streams architect spec generation via Agent SDK.

    Flow:
    1. Client sends: {idea, model, project_dir}
    2. Server streams: tool events during web research
    3. Server sends: {type: "questions", questions: [...]} — clarifying questions
    4. Client sends: {type: "answers", answers: {...}} — user's answers
    5. Server streams: text_delta events for spec generation
    6. Server sends: {type: "complete", text: full_spec}
    """
    await websocket.accept()
    print("[ws/architect] Connection accepted, waiting for config...", flush=True)

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        config = json.loads(raw)
        idea = config.get("idea", "").strip()
        model = config.get("model", DEFAULT_MODEL)
        project_dir = config.get("project_dir", "")

        if not idea:
            await websocket.send_json({"type": "error", "message": "Idea is required"})
            await websocket.close()
            return

        print(f"[ws/architect] Config: idea={idea[:60]}..., model={model}", flush=True)

        cwd = project_dir if project_dir and Path(project_dir).is_dir() else None

        # --- Phase 1: Research + Generate Questions ---
        await websocket.send_json({"type": "phase", "phase": "research"})

        questions_data, research_thinking = await _architect_research_via_sdk(
            idea, model=model, cwd=cwd, send_event=websocket.send_json,
        )

        # Send questions or skip notification
        if questions_data:
            await websocket.send_json({"type": "questions", "questions": questions_data})
        else:
            await websocket.send_json({"type": "questions_skipped"})

        # --- Phase 2: Wait for User Answers (if questions were sent) ---
        answers_text = ""
        if questions_data:
            await websocket.send_json({"type": "phase", "phase": "waiting_for_answers"})
            print("[ws/architect] Waiting for user answers...", flush=True)

            try:
                answer_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                answer_msg = json.loads(answer_raw)
                if answer_msg.get("type") == "answers":
                    user_answers = answer_msg.get("answers", {})
                    answers_text = "\n".join(
                        f"Q: {q}\nA: {a}" for q, a in user_answers.items()
                    )
                    print(f"[ws/architect] Received {len(user_answers)} answers", flush=True)
            except asyncio.TimeoutError:
                print("[ws/architect] Answer timeout, generating spec without answers", flush=True)
            except Exception:
                print("[ws/architect] Error receiving answers, continuing without", flush=True)

        # --- Phase 3: Generate Spec ---
        await websocket.send_json({"type": "phase", "phase": "generating"})

        template = _load_lightweight_prompt("architect")
        current_date = datetime.now().strftime("%Y-%m-%d")
        spec_prompt = template.replace("{task_input}", idea).replace("{current_date}", current_date)

        if answers_text:
            spec_prompt += (
                "\n\n--- USER CLARIFICATION ANSWERS ---\n"
                "The user answered the following clarifying questions. "
                "Use these answers to guide your specification:\n\n"
                f"{answers_text}\n"
                "\nIncorporate these preferences into the specification."
            )

        if research_thinking:
            spec_prompt += (
                "\n\n--- RESEARCH NOTES ---\n"
                f"{research_thinking}\n"
                "\nUse these research findings to inform the specification."
            )

        await _architect_spec_via_sdk(
            spec_prompt, model=model, cwd=cwd, send_event=websocket.send_json,
        )

    except asyncio.TimeoutError:
        try:
            await websocket.send_json({"type": "error", "message": "Architect timed out"})
        except Exception:
            pass
    except WebSocketDisconnect:
        print("[ws/architect] Client disconnected", flush=True)
    except json.JSONDecodeError:
        try:
            await websocket.send_json({"type": "error", "message": "Invalid JSON config"})
        except Exception:
            pass
    except Exception as e:
        print(f"[ws/architect] Error: {e}", flush=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/plan")
async def ws_plan(websocket: WebSocket):
    """WebSocket endpoint that streams planner task list generation via Agent SDK.

    Flow:
    1. Client sends: {mode, task_input, spec?, codebase_profile?, model, feedback?, previous_tasks?}
    2. Server streams: text_delta events for analysis + JSON
    3. Server sends: {type: "complete", text: full_output}
    4. Server parses JSON and sends: {type: "tasks", tasks: {...}}
    """
    await websocket.accept()
    print("[ws/plan] Connection accepted, waiting for config...", flush=True)

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        config = json.loads(raw)
        mode = config.get("mode", "greenfield")
        task_input = config.get("task_input", "").strip()
        spec = config.get("spec")
        codebase_profile = config.get("codebase_profile")
        model = config.get("model", DEFAULT_MODEL)
        feedback = config.get("feedback")
        previous_tasks = config.get("previous_tasks")

        is_regen = bool(feedback and previous_tasks)
        print(f"[ws/plan] Config: mode={mode}, task_input={task_input[:60]}..., model={model}, regen={is_regen}", flush=True)

        # Build the prompt
        prompt = _build_plan_prompt(
            mode=mode,
            task_input=task_input,
            spec=spec,
            codebase_profile=codebase_profile,
            feedback=feedback,
            previous_tasks=previous_tasks,
        )
        print(f"[ws/plan] Prompt length: {len(prompt)} chars", flush=True)

        # Stream analysis + JSON via SDK
        await websocket.send_json({"type": "phase", "phase": "analyzing"})

        full_text = await _plan_via_sdk(
            prompt, model=model, send_event=websocket.send_json,
        )
        print(f"[ws/plan] SDK complete, output length: {len(full_text)} chars", flush=True)

        # Parse JSON from the accumulated text
        try:
            task_data = _parse_json_response(full_text)
            task_count = len(task_data.get("tasks", []))
            await websocket.send_json({"type": "tasks", "tasks": task_data})
            print(f"[ws/plan] Sent {task_count} tasks to client", flush=True)
        except Exception as parse_err:
            print(f"[ws/plan] JSON parse error: {parse_err}", flush=True)
            await websocket.send_json({
                "type": "error",
                "message": f"Failed to parse task list: {parse_err}",
            })

    except asyncio.TimeoutError:
        try:
            await websocket.send_json({"type": "error", "message": "Planner timed out"})
        except Exception:
            pass
    except WebSocketDisconnect:
        print("[ws/plan] Client disconnected", flush=True)
    except json.JSONDecodeError:
        try:
            await websocket.send_json({"type": "error", "message": "Invalid JSON config"})
        except Exception:
            pass
    except Exception as e:
        print(f"[ws/plan] Error: {e}", flush=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/wizard")
async def ws_wizard(websocket: WebSocket):
    """Unified wizard WebSocket using a single persistent ClaudeSDKClient.

    One subprocess for the entire wizard session. Regeneration is a lightweight
    follow-up turn since the model already has full context.

    Greenfield flow:
      Turn 0: QA questions -> user answers
      Turn 1: Research idea (web search tools) -> architect questions -> user answers
      Turn 2: Generate specification (using research + answers)
      Wait for user to approve spec (or request spec regen)
      Turn 3: Generate task list (analysis + JSON)
      Turn 4+: Regenerate tasks with feedback

    Feature flow:
      Turn 0: QA questions -> user answers
      Turn 1: Codebase analysis (with tools)
      Turn 2: Follow-up questions -> user answers
      Turn 3: Generate task list
      Turn 4+: Regenerate tasks with feedback

    Refactor flow:
      Turn 0: QA questions -> user answers
      Turn 1: Codebase analysis (with tools)
      Turn 2: Strategy questions -> user answers
      Turn 3: Strategy generation (approve/regenerate loop)
      Turn 4: Generate task list
      Turn 5+: Regenerate tasks with feedback

    Fix flow:
      Turn 0: QA questions -> user answers
      Turn 1: Bug investigation (with tools)
      Turn 2: Investigation report -> user acknowledgement
      Turn 3: Generate task list
      Turn 4+: Regenerate tasks with feedback

    Evolve flow:
      Turn 0: QA questions -> user answers
      Turn 1: Codebase audit (with tools)
      Turn 2: Audit report -> user acknowledgement
      Turn 3: Follow-up questions -> user answers
      Turn 4: Generate task list
      Turn 5+: Regenerate tasks with feedback

    Security flow:
      Turn 0: QA questions -> user answers
      Turn 1: Security scan (with tools)
      Turn 2: Security report -> user approves/ignores findings
      Turn 3: Generate task list from approved findings
      Turn 4+: Regenerate tasks with feedback
    """
    await websocket.accept()
    print("[ws/wizard] Connection accepted, waiting for config...", flush=True)

    client = None
    try:
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
        config = json.loads(raw)
        mode = config.get("mode", "greenfield")
        idea = config.get("idea", "").strip()
        task_input = config.get("task_input", "").strip()
        model = config.get("model", DEFAULT_MODEL)
        project_dir = config.get("project_dir", "")
        codebase_profile = config.get("codebase_profile")
        phase_models = config.get("phase_models", {})

        architect_model = phase_models.get("architect", model)
        plan_model = phase_models.get("plan", model)

        cwd = project_dir if project_dir and Path(project_dir).is_dir() else None

        print(f"[ws/wizard] Config: mode={mode}, model={model}, arch_model={architect_model}, plan_model={plan_model}", flush=True)

        # Create persistent ClaudeSDKClient
        os.environ.pop("CLAUDECODE", None)

        options = ClaudeAgentOptions(
            model=architect_model if mode == "greenfield" else plan_model,
            allowed_tools=["WebSearch", "WebFetch", "Read", "Glob", "Grep"],
            permission_mode="bypassPermissions",
            max_turns=10,
            include_partial_messages=True,
        )
        if cwd:
            options.cwd = cwd

        client = ClaudeSDKClient(options=options)
        await client.connect()
        print("[ws/wizard] ClaudeSDKClient connected", flush=True)

        import time as _time
        _wizard_start = _time.monotonic()

        # === QA TURN (Turn 0 — all modes) ===
        # Generate clarifying questions using the same persistent conversation.
        # Uses the same model as the rest of the wizard (NOT Haiku).
        _qa_phase_start = _time.monotonic()
        await websocket.send_json({"type": "phase", "phase": "qa"})

        qa_mode_guidance = {
            "greenfield": (
                "This is a NEW PROJECT from scratch. Consider asking about:\n"
                "- Preferred tech stack (language, framework, database)\n"
                "- Architecture style (monolith, microservices, serverless)\n"
                "- Quality requirements (testing strategy, CI/CD, linting)\n"
                "- Deployment target (Docker, cloud provider, local only)\n"
                "- Authentication/authorization needs\n"
                "- Styling preferences (CSS framework, design system)"
            ),
            "feature": (
                "This is ADDING A FEATURE to an existing codebase. Consider asking about:\n"
                "- How it integrates with existing components\n"
                "- Testing expectations (unit, integration, e2e)\n"
                "- Whether to follow existing patterns or introduce new ones\n"
                "- UI/UX preferences if it has a frontend component\n"
                "- Backward compatibility requirements\n"
                "- Performance or scale considerations"
            ),
            "refactor": (
                "This is a REFACTORING/MIGRATION task. Consider asking about:\n"
                "- Migration strategy (big bang vs incremental)\n"
                "- Backward compatibility requirements\n"
                "- Whether to keep old code as fallback\n"
                "- Test coverage expectations post-refactor\n"
                "- Performance benchmarks to maintain\n"
                "- Dependencies that might break"
            ),
            "fix": (
                "This is a BUG FIX task. Consider asking about:\n"
                "- Steps to reproduce the bug\n"
                "- Urgency/severity level\n"
                "- Known workarounds in use\n"
                "- Whether a regression test is expected\n"
                "- Environment specifics (OS, browser, versions)\n"
                "- Related issues or recent changes that might be connected"
            ),
            "evolve": (
                "This is an IMPROVEMENT/EVOLUTION task. Consider asking about:\n"
                "- Priority order if multiple improvements mentioned\n"
                "- Scope boundaries (how far to go)\n"
                "- Success metrics or targets\n"
                "- Whether to prioritize performance, readability, or maintainability\n"
                "- Test coverage goals\n"
                "- Documentation expectations"
            ),
            "security": (
                "This is a SECURITY SCAN/AUDIT task. Consider asking about:\n"
                "- Compliance frameworks to target (OWASP, SOC2, HIPAA)\n"
                "- Scan scope (full codebase vs specific areas)\n"
                "- Remediation urgency (report only vs fix immediately)\n"
                "- Dependency audit preferences\n"
                "- Secrets/credentials handling review scope\n"
                "- Whether to include infrastructure config review"
            ),
        }

        qa_guidance = qa_mode_guidance.get(mode, (
            "Consider asking about priorities, scope, preferences, "
            "and any ambiguous aspects of the request."
        ))

        qa_prompt = (
            "IMPORTANT: Do NOT use any tools for this step. Generate the questions directly.\n\n"
            "Analyze the user's request and generate clarifying questions "
            "before the agent starts working. The user wants to guide the agent "
            "with their preferences — always give them that opportunity.\n\n"
            f"MODE: {mode}\n"
            f"USER REQUEST: {task_input or idea}\n"
            + (f"PROJECT DIRECTORY: {project_dir}\n" if project_dir else "")
            + f"\n{qa_guidance}\n\n"
            "RULES:\n"
            "1. ALWAYS generate at least 2-3 clarifying questions. Even for simple "
            "requests, ask about preferences like tech stack, styling, testing "
            "approach, or project structure. The user values human-in-the-loop "
            "control. Only set skip_reason for trivially obvious one-line fixes "
            '(e.g. "Fix typo in README").\n'
            "2. Return 2-8 clarifying questions.\n"
            "3. Each question must have 2-5 options that cover the most likely answers.\n"
            "4. Questions should be ordered by importance.\n"
            '5. Include a brief "context" field explaining why each question matters.\n'
            "6. Do NOT ask obvious questions or about things already specified.\n"
            "7. For complex multi-part requests, consider asking about phasing.\n\n"
            "Output the result as a JSON block in this exact format:\n"
            "```json\n"
            '{"questions": [{"question": "...", "context": "...", '
            '"options": [{"label": "...", "description": "..."}]}]}\n'
            "```\n"
        )

        await client.query(qa_prompt)
        qa_text = await _stream_wizard_response(client, websocket, "qa")
        _qa_secs = _time.monotonic() - _qa_phase_start
        await websocket.send_json({"type": "timing", "phase": "qa", "seconds": round(_qa_secs, 1)})
        print(f"[ws/wizard] QA complete, {len(qa_text)} chars, {_qa_secs:.1f}s", flush=True)

        # Extract QA questions from text
        qa_questions = _extract_questions_from_text(qa_text)

        qa_answers_text = ""
        if qa_questions:
            await websocket.send_json({"type": "qa_questions", "questions": qa_questions})

            # Wait for user to answer or skip
            try:
                qa_msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                qa_msg = json.loads(qa_msg_raw)
                if qa_msg.get("type") == "qa_answers":
                    user_qa_answers = qa_msg.get("answers", {})
                    qa_answers_text = "\n".join(
                        f"Q: {q}\nA: {a}" for q, a in user_qa_answers.items()
                    )
                    print(f"[ws/wizard] Received {len(user_qa_answers)} QA answers", flush=True)
                elif qa_msg.get("type") == "qa_skip":
                    print("[ws/wizard] QA skipped by user", flush=True)
            except asyncio.TimeoutError:
                print("[ws/wizard] QA answer timeout, continuing without", flush=True)
            except Exception:
                print("[ws/wizard] Error receiving QA answers, continuing without", flush=True)
        else:
            await websocket.send_json({"type": "qa_skipped"})
            print("[ws/wizard] No QA questions extracted, skipping", flush=True)

        await websocket.send_json({"type": "qa_complete"})

        if mode == "greenfield":
            # === GREENFIELD FLOW ===

            # --- Turn 1: Research + Questions ---
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "research"})

            current_date = datetime.now().strftime("%Y-%m-%d")
            research_prompt = (
                f"The user wants to build: {idea or task_input}\n\n"
                f"Today's date is {current_date}.\n\n"
            )
            if qa_answers_text:
                research_prompt += (
                    "--- USER SETUP ANSWERS ---\n"
                    "The user answered these clarifying questions about their preferences:\n\n"
                    f"{qa_answers_text}\n\n"
                    "Use these answers to focus your research.\n\n"
                )
            research_prompt += (
                "Research this idea using web search. Look up:\n"
                "- Best current frameworks and libraries for this type of project\n"
                "- Latest best practices and patterns\n"
                "- Any relevant recent changes in the ecosystem\n"
                "Do 3-8 web searches depending on complexity.\n\n"
                "After researching, summarize your findings clearly. "
                "Do NOT output any JSON or questions — just your research summary."
            )

            await client.query(research_prompt)
            research_text = await _stream_wizard_response(client, websocket, "research")
            _research_secs = _time.monotonic() - _phase_start
            print(f"[ws/wizard] Research complete, {len(research_text)} chars, {_research_secs:.1f}s", flush=True)
            await websocket.send_json({"type": "timing", "phase": "research", "seconds": round(_research_secs, 1)})

            await websocket.send_json({"type": "research_complete"})

            # --- Turn 2: Architect follow-up questions (based on research) ---
            architect_answers_text = ""
            questions_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the questions directly as text.\n\n"
                "Based on your research, generate 2-4 clarifying questions to ask the user "
                "before writing the specification. These should be architecture-level questions "
                "that help you make better design decisions — things like:\n"
                "- Which framework/library to use (based on your research findings)\n"
                "- Database choice or data storage approach\n"
                "- Authentication/authorization requirements\n"
                "- Deployment target or hosting preferences\n"
                "- Any trade-offs you discovered during research\n\n"
                "Output ONLY a JSON object in a ```json fenced block with this structure:\n"
                "```json\n"
                '{"questions": [{"question": "...", "context": "...", "options": [{"label": "...", "description": "..."}]}]}\n'
                "```\n"
                "Each question should have 2-4 options based on your research findings. "
                "Do NOT output anything else — just the JSON block."
            )
            await client.query(questions_prompt)
            questions_text = await _stream_wizard_response(client, websocket, "research")
            arch_questions = _extract_questions_from_text(questions_text)

            if arch_questions and len(arch_questions) > 0:
                await websocket.send_json({"type": "questions", "questions": arch_questions})
                await websocket.send_json({"type": "phase", "phase": "waiting_for_answers"})
                print(f"[ws/wizard] Sent {len(arch_questions)} architect questions, waiting for answers", flush=True)

                # Wait for user answers (10 min timeout)
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                    msg = json.loads(msg_raw)
                    if msg.get("type") == "answers":
                        answers = msg.get("answers", {})
                        architect_answers_text = "\n".join(
                            f"- {q}: {a}" for q, a in answers.items()
                        )
                        print(f"[ws/wizard] Received architect answers: {len(answers)} answers", flush=True)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    print("[ws/wizard] Architect questions timed out, proceeding without answers", flush=True)
            else:
                await websocket.send_json({"type": "questions_skipped"})
                print("[ws/wizard] No architect questions extracted, skipping", flush=True)

            # --- Turn 3: Generate Spec ---
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "generating"})

            template = _load_lightweight_prompt("architect")
            current_date = datetime.now().strftime("%Y-%m-%d")
            spec_prompt = (
                "IMPORTANT: Do NOT use any tools for this step. You already have all the "
                "context from your research. Write the specification directly as text output.\n\n"
            ) + template.replace("{task_input}", idea or task_input).replace("{current_date}", current_date)

            if qa_answers_text:
                spec_prompt += (
                    "\n\n--- USER SETUP ANSWERS ---\n"
                    "The user answered the following clarifying questions. "
                    "Use these answers to guide your specification:\n\n"
                    f"{qa_answers_text}\n"
                    "\nIncorporate these preferences into the specification."
                )

            if architect_answers_text:
                spec_prompt += (
                    "\n\n--- ARCHITECT FOLLOW-UP ANSWERS ---\n"
                    "The user answered these follow-up questions about architecture decisions:\n\n"
                    f"{architect_answers_text}\n"
                    "\nIncorporate these decisions into the specification."
                )

            if research_text:
                spec_prompt += (
                    "\n\n--- RESEARCH NOTES ---\n"
                    "You already researched this idea. Use those findings to inform the specification. "
                    "Here is a summary of what you found:\n\n"
                    f"{research_text[:8000]}\n"
                    "\nUse these research findings to inform the specification."
                )

            await client.query(spec_prompt)
            spec_full = await _stream_wizard_response(client, websocket, "spec")
            _spec_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "spec_complete", "text": spec_full})
            await websocket.send_json({"type": "timing", "phase": "spec", "seconds": round(_spec_secs, 1)})
            print(f"[ws/wizard] Spec complete, {len(spec_full)} chars, {_spec_secs:.1f}s", flush=True)

            # --- Wait for spec approval or regeneration ---
            while True:
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                    msg = json.loads(msg_raw)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    break

                if msg.get("type") == "approve_spec":
                    print("[ws/wizard] Spec approved, moving to plan", flush=True)
                    break
                elif msg.get("type") == "regenerate_spec":
                    feedback = msg.get("feedback", "")
                    print(f"[ws/wizard] Spec regen requested: {feedback[:80]}", flush=True)
                    _phase_start = _time.monotonic()
                    await websocket.send_json({"type": "phase", "phase": "generating"})
                    regen_spec_prompt = (
                        "IMPORTANT: Do NOT use any tools. Write the updated spec directly.\n\n"
                        f"The user reviewed the specification and wants changes.\n\n"
                        f"User feedback: {feedback}\n\n"
                        "Regenerate the full specification incorporating this feedback. "
                        "Write the complete updated specification."
                    )
                    await client.query(regen_spec_prompt)
                    spec_full = await _stream_wizard_response(client, websocket, "spec")
                    _regen_secs = _time.monotonic() - _phase_start
                    await websocket.send_json({"type": "spec_complete", "text": spec_full})
                    await websocket.send_json({"type": "timing", "phase": "spec_regen", "seconds": round(_regen_secs, 1)})
                    print(f"[ws/wizard] Spec regen complete, {len(spec_full)} chars, {_regen_secs:.1f}s", flush=True)
                elif msg.get("type") in ("approve", "close"):
                    # User wants to close the wizard
                    return

            # Switch model for planning if different
            if plan_model != architect_model:
                try:
                    print(f"[ws/wizard] Switching model: {architect_model} -> {plan_model}", flush=True)
                    await client.set_model(plan_model)
                except Exception as e:
                    print(f"[ws/wizard] set_model failed ({e}), continuing with {architect_model}", flush=True)

            # --- Turn 3: Generate Plan ---
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})

            plan_prompt = _build_plan_prompt(
                mode="greenfield",
                task_input=task_input or idea,
                spec=spec_full,
            )
            # Model has full context — skip tools for pure text generation
            plan_prompt = (
                "IMPORTANT: Do NOT use any tools for this step. You already have the full "
                "specification and research context. Generate the task list directly as text output.\n"
                "Create as many tasks as needed to fully cover the specification — there is no artificial limit. "
                "Aim for small, focused tasks (one task = one logical unit of work). "
                "Keep task descriptions concise (under 200 chars each) to avoid JSON parsing issues.\n\n"
            ) + plan_prompt

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start
            print(f"[ws/wizard] Plan complete, {len(plan_text)} chars, {_plan_secs:.1f}s", flush=True)

            # Parse tasks from plan text
            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
                print(f"[ws/wizard] Sent {task_count} tasks (total wizard: {_total_secs:.1f}s)", flush=True)
            except Exception as parse_err:
                print(f"[ws/wizard] Task parse error: {parse_err}", flush=True)
                await websocket.send_json({
                    "type": "error",
                    "message": f"Failed to parse task list: {parse_err}",
                })
                return

        elif mode == "feature":
            # === FEATURE FLOW: Analysis -> Follow-up Questions -> Plan ===

            # Turn 1: Analysis with tools
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "analyzing"})

            analysis_prompt = _build_analysis_prompt("feature", task_input, qa_answers_text)
            await client.query(analysis_prompt)
            analysis_text = await _stream_wizard_response(client, websocket, "analysis")
            _analysis_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "timing", "phase": "analysis", "seconds": round(_analysis_secs, 1)})
            print(f"[ws/wizard] Feature analysis complete, {len(analysis_text)} chars, {_analysis_secs:.1f}s", flush=True)

            # Turn 2: Follow-up questions
            _phase_start = _time.monotonic()
            questions_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the questions directly.\n\n"
                "Based on your analysis of the codebase, generate 2-5 follow-up clarifying questions "
                "about the feature implementation. Focus on architectural decisions, integration "
                "patterns, and trade-offs specific to this codebase.\n\n"
                "Output as JSON: ```json\n{\"questions\": [{\"question\": \"...\", \"context\": \"...\", \"options\": [{\"label\": \"...\", \"description\": \"...\"}]}]}\n```"
            )
            await client.query(questions_prompt)
            q_text = await _stream_wizard_response(client, websocket, "questions")
            _q_secs = _time.monotonic() - _phase_start

            arch_questions = _extract_questions_from_text(q_text)
            architect_answers_text = ""
            if arch_questions:
                await websocket.send_json({"type": "questions", "questions": arch_questions})
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                    msg = json.loads(msg_raw)
                    if msg.get("type") == "answers":
                        answers = msg.get("answers", {})
                        architect_answers_text = "\n".join(f"- {q}: {a}" for q, a in answers.items())
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    pass
            else:
                await websocket.send_json({"type": "questions_skipped"})

            # Turn 3: Plan generation
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})

            # Build codebase profile from analysis text
            codebase_profile_for_plan = codebase_profile or {"analysis_summary": analysis_text[:4000]}
            plan_prompt = _build_plan_prompt(mode="feature", task_input=task_input, codebase_profile=codebase_profile_for_plan)
            plan_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n"
            ) + plan_prompt
            if qa_answers_text:
                plan_prompt += f"\n\n--- USER SETUP ANSWERS ---\n{qa_answers_text}\n"
            if architect_answers_text:
                plan_prompt += f"\n\n--- FOLLOW-UP ANSWERS ---\n{architect_answers_text}\n"

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
                print(f"[ws/wizard] Feature plan sent {task_count} tasks (total: {_total_secs:.1f}s)", flush=True)
            except Exception as parse_err:
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        elif mode == "refactor":
            # === REFACTOR FLOW: Analysis -> Questions -> Strategy -> Plan ===

            # Turn 1: Analysis with tools
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "analyzing"})
            analysis_prompt = _build_analysis_prompt("refactor", task_input, qa_answers_text)
            await client.query(analysis_prompt)
            analysis_text = await _stream_wizard_response(client, websocket, "analysis")
            _analysis_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "timing", "phase": "analysis", "seconds": round(_analysis_secs, 1)})

            # Turn 2: Strategy questions
            _phase_start = _time.monotonic()
            questions_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the questions directly.\n\n"
                "Based on your analysis, generate 2-5 clarifying questions about the refactoring/migration strategy. "
                "Focus on migration approach, compatibility requirements, and risk tolerance.\n\n"
                "Output as JSON: ```json\n{\"questions\": [{\"question\": \"...\", \"context\": \"...\", \"options\": [{\"label\": \"...\", \"description\": \"...\"}]}]}\n```"
            )
            await client.query(questions_prompt)
            q_text = await _stream_wizard_response(client, websocket, "questions")

            arch_questions = _extract_questions_from_text(q_text)
            architect_answers_text = ""
            if arch_questions:
                await websocket.send_json({"type": "questions", "questions": arch_questions})
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                    msg = json.loads(msg_raw)
                    if msg.get("type") == "answers":
                        answers = msg.get("answers", {})
                        architect_answers_text = "\n".join(f"- {q}: {a}" for q, a in answers.items())
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    pass
            else:
                await websocket.send_json({"type": "questions_skipped"})

            # Turn 3: Strategy generation (with approve/regenerate loop)
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "generating_strategy"})
            strategy_prompt = _build_strategy_prompt(task_input, analysis_text, architect_answers_text)
            if qa_answers_text:
                strategy_prompt += f"\n\n--- USER SETUP ANSWERS ---\n{qa_answers_text}\n"

            await client.query(strategy_prompt)
            strategy_text = await _stream_wizard_response(client, websocket, "strategy")
            _strategy_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "strategy_complete"})
            await websocket.send_json({"type": "timing", "phase": "strategy", "seconds": round(_strategy_secs, 1)})

            # Strategy approve/regenerate loop
            while True:
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                    msg = json.loads(msg_raw)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    return

                if msg.get("type") == "approve_strategy":
                    break
                elif msg.get("type") == "regenerate_strategy":
                    feedback = msg.get("feedback", "")
                    _phase_start = _time.monotonic()
                    await websocket.send_json({"type": "phase", "phase": "generating_strategy"})
                    regen_prompt = (
                        "IMPORTANT: Do NOT use any tools. Regenerate the strategy directly.\n\n"
                        f"User feedback on the strategy: {feedback}\n\n"
                        "Regenerate the full migration strategy incorporating this feedback."
                    )
                    await client.query(regen_prompt)
                    strategy_text = await _stream_wizard_response(client, websocket, "strategy")
                    _regen_secs = _time.monotonic() - _phase_start
                    await websocket.send_json({"type": "strategy_complete"})
                    await websocket.send_json({"type": "timing", "phase": "strategy_regen", "seconds": round(_regen_secs, 1)})
                elif msg.get("type") in ("approve", "close"):
                    return

            # Turn 4: Plan generation
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})
            codebase_profile_for_plan = codebase_profile or {"analysis_summary": analysis_text[:4000]}
            plan_prompt = _build_plan_prompt(mode="refactor", task_input=task_input, codebase_profile=codebase_profile_for_plan, strategy=strategy_text[:6000])
            plan_prompt = "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n" + plan_prompt
            if qa_answers_text:
                plan_prompt += f"\n\n--- USER SETUP ANSWERS ---\n{qa_answers_text}\n"

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
            except Exception as parse_err:
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        elif mode == "fix":
            # === FIX FLOW: Investigation -> Report -> Plan ===

            # Turn 1: Investigation with tools
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "investigating"})
            investigation_prompt = _build_investigation_prompt(task_input, qa_answers_text)
            await client.query(investigation_prompt)
            investigation_text = await _stream_wizard_response(client, websocket, "investigation")
            _inv_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "timing", "phase": "investigation", "seconds": round(_inv_secs, 1)})

            # Turn 2: Report generation (no tools)
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "generating_report"})
            report_prompt = _build_report_prompt("fix", task_input, investigation_text)
            await client.query(report_prompt)
            report_text = await _stream_wizard_response(client, websocket, "report")
            _report_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "report_complete"})
            await websocket.send_json({"type": "timing", "phase": "report", "seconds": round(_report_secs, 1)})

            # Wait for acknowledgement
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                msg = json.loads(msg_raw)
                if msg.get("type") not in ("acknowledge_report",):
                    if msg.get("type") in ("approve", "close"):
                        return
            except (asyncio.TimeoutError, WebSocketDisconnect):
                return

            # Turn 3: Plan generation
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})
            codebase_profile_for_plan = codebase_profile or {"investigation_summary": investigation_text[:4000]}
            plan_prompt = _build_plan_prompt(mode="fix", task_input=task_input, codebase_profile=codebase_profile_for_plan, investigation_summary=report_text[:6000])
            plan_prompt = "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n" + plan_prompt
            if qa_answers_text:
                plan_prompt += f"\n\n--- USER CONTEXT ---\n{qa_answers_text}\n"

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
            except Exception as parse_err:
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        elif mode == "evolve":
            # === EVOLVE FLOW: Audit -> Report -> Questions -> Plan ===

            # Turn 1: Audit with tools
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "auditing"})
            audit_prompt = _build_audit_prompt(task_input, qa_answers_text)
            await client.query(audit_prompt)
            audit_text = await _stream_wizard_response(client, websocket, "audit")
            _audit_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "timing", "phase": "audit", "seconds": round(_audit_secs, 1)})
            print(f"[ws/wizard] Evolve audit complete, {len(audit_text)} chars, {_audit_secs:.1f}s", flush=True)

            # Turn 2: Report generation (no tools)
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "generating_report"})
            report_prompt = _build_report_prompt("evolve", task_input, audit_text)
            await client.query(report_prompt)
            report_text = await _stream_wizard_response(client, websocket, "audit_report")
            _report_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "report_complete"})
            await websocket.send_json({"type": "timing", "phase": "report", "seconds": round(_report_secs, 1)})
            print(f"[ws/wizard] Evolve report complete, {len(report_text)} chars, {_report_secs:.1f}s — waiting for acknowledge", flush=True)

            # Wait for acknowledgement
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                msg = json.loads(msg_raw)
                if msg.get("type") not in ("acknowledge_report",):
                    if msg.get("type") in ("approve", "close"):
                        return
            except (asyncio.TimeoutError, WebSocketDisconnect):
                print("[ws/wizard] Evolve acknowledge timed out or disconnected", flush=True)
                return

            print("[ws/wizard] Evolve report acknowledged, proceeding to questions", flush=True)

            # Turn 3: Follow-up questions
            _phase_start = _time.monotonic()
            questions_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the questions directly.\n\n"
                "Based on your audit, generate 2-5 follow-up questions about improvement priorities "
                "and approach. Focus on scope, trade-offs, and phasing.\n\n"
                "Output as JSON: ```json\n{\"questions\": [{\"question\": \"...\", \"context\": \"...\", \"options\": [{\"label\": \"...\", \"description\": \"...\"}]}]}\n```"
            )
            await client.query(questions_prompt)
            q_text = await _stream_wizard_response(client, websocket, "questions")

            arch_questions = _extract_questions_from_text(q_text)
            print(f"[ws/wizard] Evolve questions: {len(arch_questions) if arch_questions else 0} extracted", flush=True)
            architect_answers_text = ""
            if arch_questions:
                await websocket.send_json({"type": "questions", "questions": arch_questions})
                try:
                    msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                    msg = json.loads(msg_raw)
                    if msg.get("type") == "answers":
                        answers = msg.get("answers", {})
                        architect_answers_text = "\n".join(f"- {q}: {a}" for q, a in answers.items())
                        print(f"[ws/wizard] Evolve received {len(answers)} follow-up answers", flush=True)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    print("[ws/wizard] Evolve follow-up answers timed out or disconnected", flush=True)
                    pass
            else:
                await websocket.send_json({"type": "questions_skipped"})
                print("[ws/wizard] Evolve questions skipped (none generated)", flush=True)

            # Turn 4: Plan generation
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})
            codebase_profile_for_plan = codebase_profile or {"audit_summary": audit_text[:4000]}
            plan_prompt = _build_plan_prompt(mode="evolve", task_input=task_input, codebase_profile=codebase_profile_for_plan, audit_summary=report_text[:6000])
            plan_prompt = "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n" + plan_prompt
            if qa_answers_text:
                plan_prompt += f"\n\n--- USER PREFERENCES ---\n{qa_answers_text}\n"
            if architect_answers_text:
                plan_prompt += f"\n\n--- FOLLOW-UP ANSWERS ---\n{architect_answers_text}\n"

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
                print(f"[ws/wizard] Evolve plan sent {task_count} tasks (total: {_total_secs:.1f}s)", flush=True)
            except Exception as parse_err:
                print(f"[ws/wizard] Evolve plan parse error: {parse_err}", flush=True)
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        elif mode == "security":
            # === SECURITY FLOW: Scan -> Findings Review -> Plan ===

            # Turn 1: Scan with tools
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "scanning"})
            scan_prompt = _build_security_scan_prompt(task_input, qa_answers_text)
            await client.query(scan_prompt)
            scan_text = await _stream_wizard_response(client, websocket, "scan")
            _scan_secs = _time.monotonic() - _phase_start
            await websocket.send_json({"type": "timing", "phase": "scan", "seconds": round(_scan_secs, 1)})

            # Turn 2: Security report generation (no tools)
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "generating_security"})
            security_gen_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the security report directly as JSON.\n\n"
                "Based on your security scan, produce a comprehensive security_report.json with ALL findings.\n"
                "Use the exact format from your scanning instructions. Sort findings by severity (critical first).\n"
                "Return ONLY valid JSON (no markdown fences, no extra text)."
            )
            await client.query(security_gen_prompt)
            security_text = await _stream_wizard_response(client, websocket, "security")
            _security_secs = _time.monotonic() - _phase_start

            # Parse and send findings
            try:
                security_data = _parse_json_response(security_text)
                findings = security_data.get("findings", [])
                await websocket.send_json({"type": "security_complete", "findings": findings, "summary": security_data.get("summary", {})})
            except Exception:
                findings = []
                await websocket.send_json({"type": "security_complete", "findings": [], "summary": {}})
            await websocket.send_json({"type": "timing", "phase": "security", "seconds": round(_security_secs, 1)})

            # Wait for findings approval
            approved_ids = []
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                msg = json.loads(msg_raw)
                if msg.get("type") == "approve_findings":
                    approved_ids = msg.get("approved_ids", [])
                elif msg.get("type") in ("approve", "close"):
                    return
            except (asyncio.TimeoutError, WebSocketDisconnect):
                return

            # Filter to approved findings only
            approved_findings = [f for f in findings if f.get("id") in approved_ids]
            approved_findings_json = json.dumps(approved_findings, indent=2)

            # Turn 3: Plan generation from approved findings
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})
            plan_prompt = _build_plan_prompt(mode="security", task_input=task_input, security_findings=approved_findings_json)
            plan_prompt = "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n" + plan_prompt

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
            except Exception as parse_err:
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        else:
            # === FALLBACK for any unknown mode ===
            _phase_start = _time.monotonic()
            await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})
            plan_prompt = _build_plan_prompt(mode=mode, task_input=task_input, codebase_profile=codebase_profile)
            plan_prompt = (
                "IMPORTANT: Do NOT use any tools. Generate the task list directly.\n\n"
            ) + plan_prompt
            if qa_answers_text:
                plan_prompt += f"\n\n--- USER SETUP ANSWERS ---\n{qa_answers_text}\n"

            await client.query(plan_prompt)
            plan_text = await _stream_wizard_response(client, websocket, "plan")
            _plan_secs = _time.monotonic() - _phase_start

            try:
                task_data = _parse_json_response(plan_text)
                task_count = len(task_data.get("tasks", []))
                await websocket.send_json({"type": "tasks", "tasks": task_data})
                await websocket.send_json({"type": "plan_complete"})
                _total_secs = _time.monotonic() - _wizard_start
                await websocket.send_json({"type": "timing", "phase": "plan", "seconds": round(_plan_secs, 1), "total": round(_total_secs, 1)})
            except Exception as parse_err:
                await websocket.send_json({"type": "error", "message": f"Failed to parse task list: {parse_err}"})
                return

        # === REGENERATION LOOP (both modes, after initial plan) ===
        _regen_count = 0
        while True:
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=3600)
                msg = json.loads(msg_raw)
            except (asyncio.TimeoutError, WebSocketDisconnect):
                break

            if msg.get("type") == "regenerate":
                _regen_count += 1
                feedback = msg.get("feedback", "")
                print(f"[ws/wizard] Plan regen #{_regen_count} requested: {feedback[:80]}", flush=True)
                _phase_start = _time.monotonic()
                await websocket.send_json({"type": "phase", "phase": "plan_analyzing"})

                regen_prompt = (
                    "IMPORTANT: Do NOT use any tools. Generate the updated task list directly.\n\n"
                    f"The user reviewed the task list and wants changes.\n\n"
                    f"User feedback: {feedback}\n\n"
                    "Regenerate the task list incorporating this feedback. "
                    "Write a brief analysis first, then the JSON task list."
                )
                await client.query(regen_prompt)
                plan_text = await _stream_wizard_response(client, websocket, "plan")
                _regen_secs = _time.monotonic() - _phase_start

                try:
                    task_data = _parse_json_response(plan_text)
                    task_count = len(task_data.get("tasks", []))
                    await websocket.send_json({"type": "tasks", "tasks": task_data})
                    await websocket.send_json({"type": "plan_complete"})
                    _total_secs = _time.monotonic() - _wizard_start
                    await websocket.send_json({"type": "timing", "phase": "regen", "seconds": round(_regen_secs, 1), "total": round(_total_secs, 1), "regen_number": _regen_count})
                    print(f"[ws/wizard] Regen #{_regen_count} sent {task_count} tasks in {_regen_secs:.1f}s (total: {_total_secs:.1f}s)", flush=True)
                except Exception as parse_err:
                    print(f"[ws/wizard] Regen parse error: {parse_err}", flush=True)
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to parse regenerated tasks: {parse_err}",
                    })

            elif msg.get("type") in ("approve", "close"):
                print("[ws/wizard] Wizard approved/closed", flush=True)
                break

    except asyncio.TimeoutError:
        try:
            await websocket.send_json({"type": "error", "message": "Wizard timed out"})
        except Exception:
            pass
    except WebSocketDisconnect:
        print("[ws/wizard] Client disconnected", flush=True)
    except json.JSONDecodeError:
        try:
            await websocket.send_json({"type": "error", "message": "Invalid JSON config"})
        except Exception:
            pass
    except Exception as e:
        print(f"[ws/wizard] Error: {e}", flush=True)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        if client:
            try:
                await client.disconnect()
                print("[ws/wizard] ClaudeSDKClient disconnected", flush=True)
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass

"use client";

import { useState, useCallback, useRef } from "react";
import type { TaskData } from "./useSwarmWeaver";

export type WizardPhase =
  | "idle"
  | "qa"              // Generating QA questions (Turn 0)
  | "qa_questions"    // Waiting for user to answer QA questions
  | "qa_complete"     // QA done, moving to next phase
  | "research"        // Architect researching (tool calls)
  | "questions"       // Waiting for user to answer architect questions
  | "generating"      // Generating spec
  | "spec_complete"   // Spec ready for review
  | "plan_analyzing"  // Generating plan (analysis + JSON)
  | "plan_complete"   // Tasks ready for review
  | "analyzing"           // Codebase analysis (feature/refactor/evolve)
  | "investigating"       // Bug investigation (fix mode)
  | "auditing"           // Codebase audit (evolve mode)
  | "scanning"           // Security scan (security mode)
  | "generating_strategy" // Generating migration strategy (refactor)
  | "strategy_complete"   // Strategy ready for review
  | "generating_report"   // Generating investigation/audit report
  | "report_complete"     // Report ready for acknowledgement
  | "generating_security" // Generating security findings
  | "security_complete"   // Security findings ready for review
  | "error";

export interface WizardToolEvent {
  id: string;
  tool: string;
  input: string;
  status: "running" | "done";
}

export interface WizardQuestion {
  question: string;
  context: string;
  options: { label: string; description: string }[];
}

export interface WizardStreamConfig {
  mode: string;
  idea?: string;
  task_input: string;
  model: string;
  project_dir?: string;
  codebase_profile?: Record<string, unknown>;
  phase_models?: { architect?: string; plan?: string; code?: string };
}

export function useWizardStream() {
  const [phase, setPhase] = useState<WizardPhase>("idle");
  const [tools, setTools] = useState<WizardToolEvent[]>([]);
  const [questions, setQuestions] = useState<WizardQuestion[]>([]);
  const [qaQuestions, setQaQuestions] = useState<WizardQuestion[]>([]);
  const [specText, setSpecText] = useState("");
  const [analysisText, setAnalysisText] = useState("");
  const [tasks, setTasks] = useState<TaskData | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timings, setTimings] = useState<Record<string, number>>({});
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const [strategyText, setStrategyText] = useState("");
  const [reportText, setReportText] = useState("");
  const [securityFindings, setSecurityFindings] = useState<Record<string, unknown>[] | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const specRef = useRef("");
  const analysisRef = useRef("");
  const strategyRef = useRef("");
  const reportRef = useRef("");
  const securityRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  // Track current phase internally for routing text_delta events
  const phaseRef = useRef<WizardPhase>("idle");

  const close = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback(() => {
    stopTimer();
    startTimeRef.current = Date.now();
    setElapsedSecs(0);
    timerRef.current = setInterval(() => {
      setElapsedSecs(Math.round((Date.now() - startTimeRef.current) / 1000));
    }, 1000);
  }, [stopTimer]);

  const reset = useCallback(() => {
    setPhase("idle");
    setTools([]);
    setQuestions([]);
    setQaQuestions([]);
    setSpecText("");
    setAnalysisText("");
    setTasks(null);
    setIsStreaming(false);
    setError(null);
    setTimings({});
    setElapsedSecs(0);
    specRef.current = "";
    analysisRef.current = "";
    strategyRef.current = "";
    reportRef.current = "";
    securityRef.current = "";
    setStrategyText("");
    setReportText("");
    setSecurityFindings(null);
    phaseRef.current = "idle";
    stopTimer();
  }, [stopTimer]);

  const updatePhase = useCallback((p: WizardPhase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

  const sendQAAnswers = useCallback((answers: Record<string, string>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "qa_answers", answers }));
      updatePhase("qa_complete");
    }
  }, [updatePhase]);

  const skipQA = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "qa_skip" }));
      updatePhase("qa_complete");
    }
  }, [updatePhase]);

  const sendAnswers = useCallback((answers: Record<string, string>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "answers", answers }));
      updatePhase("generating");
    }
  }, [updatePhase]);

  const approveSpec = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "approve_spec" }));
      // Reset plan-related state for the new plan phase
      analysisRef.current = "";
      setAnalysisText("");
      setTasks(null);
      updatePhase("plan_analyzing");
      setIsStreaming(true);
      // Don't restart timer — keep it continuous from connect()
    }
  }, [updatePhase]);

  const approveStrategy = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "approve_strategy" }));
      updatePhase("plan_analyzing");
      setIsStreaming(true);
    }
  }, [updatePhase]);

  const regenerateStrategy = useCallback((feedback: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "regenerate_strategy", feedback }));
      strategyRef.current = "";
      setStrategyText("");
      updatePhase("generating_strategy");
      setIsStreaming(true);
    }
  }, [updatePhase]);

  const acknowledgeReport = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "acknowledge_report" }));
      setIsStreaming(true);
    }
  }, []);

  const approveFindings = useCallback((ids: string[], reasons: Record<string, string>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "approve_findings", approved_ids: ids, ignored_reasons: reasons }));
      updatePhase("plan_analyzing");
      setIsStreaming(true);
    }
  }, [updatePhase]);

  const regenerateSpec = useCallback((feedback: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "regenerate_spec", feedback }));
      specRef.current = "";
      setSpecText("");
      updatePhase("generating");
      setIsStreaming(true);
      // Don't restart timer — keep it continuous from connect()
    }
  }, [updatePhase]);

  const regenerate = useCallback((feedback: string) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "regenerate", feedback }));
      analysisRef.current = "";
      setAnalysisText("");
      setTasks(null);
      updatePhase("plan_analyzing");
      setIsStreaming(true);
      // Don't restart timer — keep it continuous from connect()
    }
  }, [updatePhase]);

  const approve = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "approve" }));
    }
    close();
  }, [close]);

  const connect = useCallback(
    (config: WizardStreamConfig) => {
      close();
      reset();
      setIsStreaming(true);
      startTimer();

      // All modes start with QA (Turn 0) before their main phase
      updatePhase("qa");

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname;
      const port = 8000;
      const ws = new WebSocket(`${protocol}//${host}:${port}/ws/wizard`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify(config));
      };

      ws.onmessage = (evt) => {
        try {
          const event = JSON.parse(evt.data);

          switch (event.type) {
            case "phase": {
              const p = event.phase as string;
              if (p === "qa") updatePhase("qa");
              else if (p === "research") updatePhase("research");
              else if (p === "waiting_for_answers") updatePhase("questions");
              else if (p === "generating") updatePhase("generating");
              else if (p === "plan_analyzing") updatePhase("plan_analyzing");
              else if (p === "analyzing") updatePhase("analyzing");
              else if (p === "investigating") updatePhase("investigating");
              else if (p === "auditing") updatePhase("auditing");
              else if (p === "scanning") updatePhase("scanning");
              else if (p === "generating_strategy") updatePhase("generating_strategy");
              else if (p === "generating_report") updatePhase("generating_report");
              else if (p === "generating_security") updatePhase("generating_security");
              break;
            }

            // --- QA events (Turn 0) ---
            case "qa_questions":
              setQaQuestions(event.questions || []);
              updatePhase("qa_questions");
              setIsStreaming(false);
              break;

            case "qa_skipped":
              updatePhase("qa_complete");
              break;

            case "qa_complete":
              updatePhase("qa_complete");
              setIsStreaming(true);
              break;

            // --- Tool events (research phase) ---
            case "tool_start":
              setTools((prev) => [
                ...prev,
                { id: event.id, tool: event.tool, input: "", status: "running" },
              ]);
              break;

            case "tool_input_delta":
              setTools((prev) =>
                prev.map((t) =>
                  t.id === event.id ? { ...t, input: t.input + event.chunk } : t
                )
              );
              break;

            case "tool_done":
              setTools((prev) =>
                prev.map((t) =>
                  t.id === event.id ? { ...t, status: "done" } : t
                )
              );
              break;

            case "questions":
              setQuestions(event.questions || []);
              updatePhase("questions");
              break;

            case "questions_skipped":
              updatePhase("generating");
              break;

            // --- Research complete (greenfield: research done, spec next) ---
            case "research_complete":
              // Just a phase marker — generating phase event follows
              break;

            case "text_delta": {
              // Route based on text_type from backend (preferred) or current phase.
              // Research/analysis-phase text (text_type="research", "analysis", "investigation",
              // "audit") is intentionally NOT displayed — progress is shown through tool_start/
              // tool_done events in the ArchitectResearchPanel. Only "plan" text is displayed.
              // QA-phase text (text_type="qa") is also not displayed — shown via qa_questions event.
              // Explicit text_type from backend takes priority over phase-based routing.
              // This prevents misrouting when phase is temporarily stale (e.g. sendAnswers
              // sets phase="generating" but plan text arrives with text_type="plan").
              const textType = event.text_type || "";
              if (textType === "spec" || (!textType && phaseRef.current === "generating")) {
                specRef.current += event.text;
                setSpecText(specRef.current);
              } else if (textType === "plan" || (!textType && phaseRef.current === "plan_analyzing")) {
                analysisRef.current += event.text;
                setAnalysisText(analysisRef.current);
              } else if (textType === "strategy" || (!textType && phaseRef.current === "generating_strategy")) {
                strategyRef.current += event.text;
                setStrategyText(strategyRef.current);
              } else if (textType === "report" || textType === "audit_report" || (!textType && phaseRef.current === "generating_report")) {
                reportRef.current += event.text;
                setReportText(reportRef.current);
              } else if (textType === "security" || (!textType && phaseRef.current === "generating_security")) {
                securityRef.current += event.text;
                setSecurityFindings(null); // will parse on security_complete
              }
              break;
            }

            case "spec_complete":
              if (event.text) {
                specRef.current = event.text;
                setSpecText(event.text);
              }
              updatePhase("spec_complete");
              setIsStreaming(false);
              // Don't stop timer — it runs continuously across all wizard phases
              break;

            case "tasks":
              setTasks(event.tasks as TaskData);
              break;

            case "plan_complete":
              updatePhase("plan_complete");
              setIsStreaming(false);
              // Don't stop timer — it runs continuously across all wizard phases
              break;

            case "strategy_complete":
              updatePhase("strategy_complete");
              setIsStreaming(false);
              break;

            case "report_complete":
              updatePhase("report_complete");
              setIsStreaming(false);
              break;

            case "security_complete": {
              // Parse security findings from accumulated text or from event payload
              const findings = event.findings || null;
              if (findings) {
                setSecurityFindings(findings);
              } else {
                try {
                  const parsed = JSON.parse(securityRef.current);
                  setSecurityFindings(parsed.findings || []);
                } catch {
                  setSecurityFindings([]);
                }
              }
              updatePhase("security_complete");
              setIsStreaming(false);
              break;
            }

            case "timing":
              setTimings((prev) => ({
                ...prev,
                [event.phase]: event.seconds,
                ...(event.total != null ? { total: event.total } : {}),
              }));
              break;

            case "error":
              setError(event.message || "Unknown error");
              setIsStreaming(false);
              stopTimer();
              updatePhase("error");
              break;
          }
        } catch {
          // Ignore non-JSON messages
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection failed");
        setIsStreaming(false);
        updatePhase("error");
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
          setIsStreaming(false);
          stopTimer();
        }
      };
    },
    [close, reset, updatePhase, startTimer, stopTimer]
  );

  return {
    // Connection
    connect,
    close,
    reset,
    // Actions
    sendQAAnswers,
    skipQA,
    sendAnswers,
    approveSpec,
    regenerateSpec,
    regenerate,
    approve,
    approveStrategy,
    regenerateStrategy,
    acknowledgeReport,
    approveFindings,
    // State
    phase,
    tools,
    questions,
    qaQuestions,
    specText,
    analysisText,
    strategyText,
    reportText,
    securityFindings,
    tasks,
    isStreaming,
    error,
    // Timing
    timings,
    elapsedSecs,
  };
}

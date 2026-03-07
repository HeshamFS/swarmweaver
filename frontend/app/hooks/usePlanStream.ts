"use client";

import { useState, useCallback, useRef } from "react";
import type { TaskData } from "./useSwarmWeaver";

export type PlanPhase = "idle" | "analyzing" | "complete" | "error";

export interface PlanStreamConfig {
  mode: string;
  task_input: string;
  spec?: string;
  codebase_profile?: Record<string, unknown>;
  model: string;
  feedback?: string;
  previous_tasks?: Record<string, unknown>;
}

export function usePlanStream() {
  const [analysisText, setAnalysisText] = useState("");
  const [tasks, setTasks] = useState<TaskData | null>(null);
  const [phase, setPhase] = useState<PlanPhase>("idle");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const textRef = useRef("");

  const close = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    setAnalysisText("");
    setTasks(null);
    setPhase("idle");
    setError(null);
    setIsStreaming(false);
    textRef.current = "";
  }, []);

  const connect = useCallback(
    (config: PlanStreamConfig) => {
      close();
      reset();
      setIsStreaming(true);
      setPhase("analyzing");

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname;
      const port = 8000;
      const ws = new WebSocket(`${protocol}//${host}:${port}/ws/plan`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify(config));
      };

      ws.onmessage = (evt) => {
        try {
          const event = JSON.parse(evt.data);

          switch (event.type) {
            case "phase":
              if (event.phase === "analyzing") setPhase("analyzing");
              break;

            case "text_delta":
              textRef.current += event.text;
              setAnalysisText(textRef.current);
              break;

            case "tasks":
              setTasks(event.tasks as TaskData);
              break;

            case "complete":
              setAnalysisText(textRef.current);
              setIsStreaming(false);
              setPhase("complete");
              break;

            case "error":
              setError(event.message || "Unknown error");
              setIsStreaming(false);
              setPhase("error");
              break;
          }
        } catch {
          // Ignore non-JSON messages
        }
      };

      ws.onerror = () => {
        setError("WebSocket connection failed");
        setIsStreaming(false);
        setPhase("error");
      };

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null;
          setIsStreaming(false);
          // If the WS closed without tasks or error, signal failure so fallback kicks in
          setPhase((prev) => {
            if (prev === "analyzing") {
              setError("Connection closed before task list was received");
              return "error";
            }
            return prev;
          });
        }
      };
    },
    [close, reset]
  );

  return {
    connect, close, reset,
    analysisText, tasks, phase,
    isStreaming, error,
  };
}

"use client";

import { useState, useCallback, useRef } from "react";

export interface ToolEvent {
  id: string;
  tool: string;
  input: string;
  status: "running" | "done";
}

export interface ArchitectQuestion {
  question: string;
  context: string;
  options: { label: string; description: string }[];
}

export type ArchitectPhase = "idle" | "research" | "questions" | "generating" | "complete" | "error";

export function useArchitectStream() {
  const [streamedText, setStreamedText] = useState("");
  const [tools, setTools] = useState<ToolEvent[]>([]);
  const [questions, setQuestions] = useState<ArchitectQuestion[]>([]);
  const [phase, setPhase] = useState<ArchitectPhase>("idle");
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
    setStreamedText("");
    setTools([]);
    setQuestions([]);
    setPhase("idle");
    setError(null);
    textRef.current = "";
  }, []);

  const sendAnswers = useCallback((answers: Record<string, string>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "answers", answers }));
      setPhase("generating");
    }
  }, []);

  const connect = useCallback(
    (config: { idea: string; model: string; project_dir: string }) => {
      close();
      reset();
      setIsStreaming(true);
      setPhase("research");

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname;
      const port = 8000;
      const ws = new WebSocket(`${protocol}//${host}:${port}/ws/architect`);
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify(config));
      };

      ws.onmessage = (evt) => {
        try {
          const event = JSON.parse(evt.data);

          switch (event.type) {
            case "phase":
              if (event.phase === "research") setPhase("research");
              else if (event.phase === "waiting_for_answers") setPhase("questions");
              else if (event.phase === "generating") setPhase("generating");
              break;

            case "text_delta":
              textRef.current += event.text;
              setStreamedText(textRef.current);
              break;

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
              setPhase("questions");
              break;

            case "questions_skipped":
              // No questions — go straight to spec generation
              setPhase("generating");
              break;

            case "complete":
              setStreamedText(event.text);
              textRef.current = event.text;
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
        }
      };
    },
    [close, reset]
  );

  return {
    connect, close, reset, sendAnswers,
    streamedText, tools, questions, phase,
    isStreaming, error,
  };
}

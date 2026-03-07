"use client";

import { useState, useRef, useEffect } from "react";
import type { Mode, AgentStatus, RunConfig } from "../hooks/useSwarmWeaver";

interface CommandInputProps {
  status: AgentStatus;
  onRun: (config: RunConfig) => void;
}

const COMMAND_HELP = `Usage: swarmweaver <mode> --project-dir <path> [options]

Modes:
  greenfield  --project-dir <path> [--spec <file>]
  feature     --project-dir <path> --description "..."
  refactor    --project-dir <path> --goal "..."
  fix         --project-dir <path> --issue "..."
  evolve      --project-dir <path> --goal "..."

Options:
  --model <model>          Model to use (default: claude-sonnet-4-6)
  --max-iterations <n>     Max sessions to run
  --no-resume              Start fresh`;

function parseCommand(input: string): RunConfig | string {
  const parts: string[] = [];
  let current = "";
  let inQuote = false;
  let quoteChar = "";

  for (const ch of input) {
    if (!inQuote && (ch === '"' || ch === "'")) {
      inQuote = true;
      quoteChar = ch;
    } else if (inQuote && ch === quoteChar) {
      inQuote = false;
    } else if (!inQuote && ch === " ") {
      if (current) parts.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  if (current) parts.push(current);

  // Remove leading "swarmweaver" or "python autonomous_agent_demo.py" if present
  let i = 0;
  if (parts[i] === "swarmweaver" || parts[i] === "python") {
    i++;
    if (parts[i] === "autonomous_agent_demo.py") i++;
  }

  const mode = parts[i] as Mode;
  if (!["greenfield", "feature", "refactor", "fix", "evolve"].includes(mode)) {
    return `Unknown mode: "${parts[i] || ""}".\n\n${COMMAND_HELP}`;
  }
  i++;

  const config: RunConfig = {
    mode,
    project_dir: "",
    task_input: "",
    model: "claude-sonnet-4-6",
    no_resume: false,
  };

  while (i < parts.length) {
    const flag = parts[i];
    if (flag === "--project-dir" && parts[i + 1]) {
      config.project_dir = parts[++i];
    } else if (flag === "--description" && parts[i + 1]) {
      config.task_input = parts[++i];
    } else if (flag === "--goal" && parts[i + 1]) {
      config.task_input = parts[++i];
    } else if (flag === "--issue" && parts[i + 1]) {
      config.task_input = parts[++i];
    } else if (flag === "--spec" && parts[i + 1]) {
      config.spec = parts[++i];
    } else if (flag === "--model" && parts[i + 1]) {
      config.model = parts[++i];
    } else if (flag === "--max-iterations" && parts[i + 1]) {
      config.max_iterations = parseInt(parts[++i]);
    } else if (flag === "--no-resume") {
      config.no_resume = true;
    }
    i++;
  }

  if (!config.project_dir) {
    return "Missing --project-dir";
  }

  return config;
}

export function CommandInput({ status, onRun }: CommandInputProps) {
  const [cmd, setCmd] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const isRunning = status === "running" || status === "starting";

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = cmd.trim();
    if (!trimmed || isRunning) return;

    if (trimmed === "help" || trimmed === "--help") {
      setError(COMMAND_HELP);
      return;
    }

    const result = parseCommand(trimmed);
    if (typeof result === "string") {
      setError(result);
      return;
    }

    setError("");
    setHistory((prev) => [trimmed, ...prev.slice(0, 49)]);
    setHistoryIdx(-1);
    onRun(result);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowUp" && history.length > 0) {
      e.preventDefault();
      const next = Math.min(historyIdx + 1, history.length - 1);
      setHistoryIdx(next);
      setCmd(history[next]);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIdx <= 0) {
        setHistoryIdx(-1);
        setCmd("");
      } else {
        const next = historyIdx - 1;
        setHistoryIdx(next);
        setCmd(history[next]);
      }
    }
  };

  return (
    <div className="space-y-1">
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <span className="text-accent font-mono text-sm font-bold select-none">
          $
        </span>
        <input
          ref={inputRef}
          type="text"
          value={cmd}
          onChange={(e) => {
            setCmd(e.target.value);
            setError("");
          }}
          onKeyDown={handleKeyDown}
          placeholder='swarmweaver feature --project-dir ./my-app --description "Add dark mode"'
          disabled={isRunning}
          className="flex-1 bg-transparent border-none outline-none text-sm text-text-primary font-mono placeholder:text-text-muted disabled:opacity-50"
        />
      </form>
      {error && (
        <pre className="text-xs text-error font-mono whitespace-pre-wrap pl-4">
          {error}
        </pre>
      )}
    </div>
  );
}

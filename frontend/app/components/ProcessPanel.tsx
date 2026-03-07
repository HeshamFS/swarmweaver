"use client";

import { useState, useEffect } from "react";

interface ProcessEntry {
  pid: number;
  port: number | null;
  type: string;
  alive: boolean;
  command_preview: string;
}

interface ProcessPanelProps {
  projectDir: string;
}

const TYPE_COLORS: Record<string, string> = {
  backend: "text-accent bg-accent/10",
  frontend: "text-info bg-info/10",
  test: "text-success bg-success/10",
  "dev-tool": "text-warning bg-warning/10",
  other: "text-text-muted bg-surface",
};

export function ProcessPanel({ projectDir }: ProcessPanelProps) {
  const [processes, setProcesses] = useState<ProcessEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [portsInUse, setPortsInUse] = useState<number[]>([]);

  useEffect(() => {
    if (!projectDir) return;
    fetchProcesses();
    const interval = setInterval(fetchProcesses, 5000);
    return () => clearInterval(interval);
  }, [projectDir]);

  const fetchProcesses = async () => {
    try {
      const res = await fetch(`/api/processes?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      setProcesses(data.processes || []);
      setPortsInUse(data.ports_in_use || []);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const aliveCount = processes.filter((p) => p.alive).length;
  const deadCount = processes.filter((p) => !p.alive).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center p-4">
        <span className="text-xs text-text-muted">Loading processes...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="flex items-center gap-3 text-xs font-mono">
        <span className="text-text-muted">
          {processes.length} tracked
        </span>
        {aliveCount > 0 && (
          <span className="text-success">{aliveCount} alive</span>
        )}
        {deadCount > 0 && (
          <span className="text-error">{deadCount} dead</span>
        )}
        {portsInUse.length > 0 && (
          <span className="text-text-muted">
            Ports: {portsInUse.join(", ")}
          </span>
        )}
      </div>

      {processes.length === 0 ? (
        <div className="text-xs text-text-muted text-center py-4">
          No background processes tracked
        </div>
      ) : (
        <div className="space-y-2">
          {processes.map((proc) => (
            <div
              key={proc.pid}
              className="rounded-lg border border-border-subtle bg-surface-raised px-3 py-2"
            >
              <div className="flex items-center gap-2 mb-1">
                {/* Alive indicator */}
                <span
                  className={`w-2 h-2 rounded-full ${proc.alive ? "bg-success" : "bg-error"}`}
                />
                {/* Type badge */}
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                    TYPE_COLORS[proc.type] || TYPE_COLORS.other
                  }`}
                >
                  {proc.type}
                </span>
                {/* PID */}
                <span className="text-[10px] text-text-muted font-mono">
                  PID {proc.pid}
                </span>
                {/* Port */}
                {proc.port && (
                  <span className="text-[10px] text-accent font-mono ml-auto">
                    :{proc.port}
                  </span>
                )}
              </div>
              {/* Command */}
              <div className="text-[10px] text-text-muted font-mono truncate">
                {proc.command_preview}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

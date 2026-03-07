"use client";

import { useMemo } from "react";

export interface MonitorHealthSummary {
  fleet_score: number;
  worker_statuses: Array<{
    worker_id: number;
    status: string;
    last_output_ago: number;
    escalation_level: number;
    warnings: string[];
  }>;
  actions_taken: Array<{
    type: string;
    worker_id?: number;
    reason: string;
  }>;
  check_number: number;
  timestamp: string;
}

interface MonitorPanelProps {
  latest: MonitorHealthSummary | null;
  trend: number[];
  daemonRunning: boolean;
  checkInterval: number;
  totalChecks: number;
}

function scoreColor(score: number): string {
  if (score > 70) return "#10B981";
  if (score > 40) return "#F59E0B";
  return "#EF4444";
}

function statusDot(status: string): string {
  switch (status) {
    case "healthy":
      return "bg-success";
    case "warning":
      return "bg-warning animate-pulse";
    case "stalled":
      return "bg-orange-500 animate-pulse";
    case "dead":
      return "bg-error";
    default:
      return "bg-text-muted";
  }
}

function actionIcon(type: string): string {
  switch (type) {
    case "nudge":
      return "\u{1F4AC}";
    case "alert":
      return "\u26A0";
    case "flag":
      return "\u{1F6A9}";
    case "warning":
      return "\u{26A0}";
    default:
      return "\u2022";
  }
}

/** SVG sparkline of fleet scores over time. */
function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;
  const w = 200;
  const h = 32;
  const max = 100;
  const step = w / (data.length - 1);

  const points = data
    .map((v, i) => `${i * step},${h - (v / max) * h}`)
    .join(" ");

  const lastScore = data[data.length - 1];
  const color = scoreColor(lastScore);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-8" preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
      {/* Fill area under the line */}
      <polygon
        fill={color}
        fillOpacity="0.1"
        points={`0,${h} ${points} ${(data.length - 1) * step},${h}`}
      />
    </svg>
  );
}

/** Semicircular gauge for fleet score. */
function ScoreGauge({ score }: { score: number }) {
  const r = 40;
  const cx = 50;
  const cy = 50;
  const startAngle = Math.PI;
  const sweepAngle = Math.PI;
  const pct = Math.max(0, Math.min(100, score)) / 100;

  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const endAngle = startAngle + sweepAngle * pct;
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const largeArc = pct > 0.5 ? 1 : 0;

  const bgX2 = cx + r * Math.cos(startAngle + sweepAngle);
  const bgY2 = cy + r * Math.sin(startAngle + sweepAngle);

  const color = scoreColor(score);

  return (
    <svg viewBox="0 0 100 60" className="w-24 h-14">
      {/* Background arc */}
      <path
        d={`M ${x1} ${y1} A ${r} ${r} 0 1 1 ${bgX2} ${bgY2}`}
        fill="none"
        stroke="var(--color-border-subtle)"
        strokeWidth="6"
        strokeLinecap="round"
      />
      {/* Foreground arc */}
      {pct > 0 && (
        <path
          d={`M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
        />
      )}
      {/* Score text */}
      <text
        x={cx}
        y={cy - 2}
        textAnchor="middle"
        fill={color}
        fontSize="18"
        fontWeight="bold"
        fontFamily="monospace"
      >
        {score}
      </text>
    </svg>
  );
}

export function MonitorPanel({ latest, trend, daemonRunning, checkInterval, totalChecks }: MonitorPanelProps) {
  const workers = latest?.worker_statuses ?? [];
  const actions = latest?.actions_taken ?? [];

  const formattedTime = useMemo(() => {
    if (!latest?.timestamp) return "";
    try {
      return new Date(latest.timestamp).toLocaleTimeString();
    } catch {
      return latest.timestamp;
    }
  }, [latest?.timestamp]);

  if (!latest && !daemonRunning) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-text-muted">
        Monitor daemon is not active. Enable it in run configuration for swarm runs.
      </div>
    );
  }

  return (
    <div className="space-y-3 text-sm">
      {/* Header: Daemon status + score gauge */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <ScoreGauge score={latest?.fleet_score ?? 0} />
          <div>
            <div className="text-xs text-text-muted">Fleet Health</div>
            <div
              className="text-2xl font-mono font-bold"
              style={{ color: scoreColor(latest?.fleet_score ?? 0) }}
            >
              {latest?.fleet_score ?? 0}
            </div>
          </div>
        </div>
        <div className="text-right space-y-0.5">
          <div className="flex items-center gap-1.5 justify-end">
            <span
              className={`w-2 h-2 rounded-full ${daemonRunning ? "bg-success animate-pulse" : "bg-text-muted"}`}
            />
            <span className="text-[10px] font-mono text-text-muted">
              Monitor: {daemonRunning ? "Running" : "Stopped"}
            </span>
          </div>
          <div className="text-[10px] font-mono text-text-muted">
            every {checkInterval}s | {totalChecks} checks
          </div>
          {formattedTime && (
            <div className="text-[10px] font-mono text-text-muted">
              Last: {formattedTime}
            </div>
          )}
        </div>
      </div>

      {/* Health trend sparkline */}
      {trend.length > 1 && (
        <div className="px-1">
          <div className="text-[10px] font-mono text-text-muted mb-1">Health Trend</div>
          <Sparkline data={trend} />
        </div>
      )}

      {/* Per-worker health table */}
      {workers.length > 0 && (
        <div>
          <div className="text-[10px] font-mono text-text-muted mb-1.5 uppercase tracking-wider">
            Worker Health
          </div>
          <div className="space-y-1">
            {workers.map((w) => (
              <div
                key={w.worker_id}
                className="flex items-center gap-2 px-2 py-1 rounded border border-border-subtle bg-surface"
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${statusDot(w.status)}`} />
                <span className="text-xs font-mono text-text-secondary w-16">
                  W{w.worker_id}
                </span>
                <span className="text-[10px] font-mono text-text-muted flex-1">
                  {w.status}
                </span>
                <span className="text-[10px] font-mono text-text-muted">
                  {w.last_output_ago >= 0 ? `${w.last_output_ago}s ago` : "-"}
                </span>
                {w.escalation_level > 0 && (
                  <span className="text-[10px] font-mono text-warning px-1 rounded border border-warning/30 bg-warning/10">
                    L{w.escalation_level}
                  </span>
                )}
                {w.warnings.length > 0 && (
                  <span
                    className="text-[10px] font-mono text-text-muted"
                    title={w.warnings.join("\n")}
                  >
                    {w.warnings.length}w
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Auto-actions log */}
      {actions.length > 0 && (
        <div>
          <div className="text-[10px] font-mono text-text-muted mb-1.5 uppercase tracking-wider">
            Actions Taken
          </div>
          <div className="max-h-32 overflow-y-auto space-y-0.5">
            {actions.map((a, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-mono text-text-muted"
              >
                <span>{actionIcon(a.type)}</span>
                <span className="text-text-secondary">{a.type}</span>
                {a.worker_id != null && (
                  <span className="text-text-muted">W{a.worker_id}</span>
                )}
                <span className="text-text-muted truncate flex-1">
                  {a.reason}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state when daemon is running but no workers yet */}
      {daemonRunning && workers.length === 0 && !latest && (
        <div className="text-center text-xs text-text-muted py-4">
          Waiting for first health check...
        </div>
      )}
    </div>
  );
}

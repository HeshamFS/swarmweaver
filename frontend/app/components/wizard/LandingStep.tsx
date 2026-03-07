"use client";

import { useState, useEffect } from "react";
import { BrainCog } from "lucide-react";
import { Omnibar } from "./Omnibar";
import { ConfirmModal } from "../ConfirmModal";
import { MODE_ICONS } from "../../utils/modeIcons";
import type { ProjectInfo, ProjectStatus, RunConfig, Mode } from "../../hooks/useSwarmWeaver";
import type { GlobalSettings } from "../../hooks/useGlobalSettings";

/* ── Run History types ── */
interface RunInfo {
  run_id: string;
  status: string;
  started_at: string;
  agents?: number;
  mode?: string;
}

/* ── Helpers ── */
function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffSec = Math.floor((now - then) / 1000);
  if (diffSec < 60) return "just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

interface LandingStepProps {
  projects: ProjectInfo[];
  onResumeProject: (project: ProjectInfo) => void;
  onRemoveProject: (projectPath: string) => void;
  onClearAllProjects?: () => void;
  fetchProjects: () => void;
  checkProjectStatus: (path: string) => Promise<ProjectStatus | null>;
  fetchProjectSettings?: (path: string) => Promise<Record<string, unknown> | null>;
  saveProjectSettings?: (path: string, settings: Record<string, unknown>) => Promise<void>;
  onRunDirect: (config: RunConfig) => void;
  onRunArchitectOnly: (config: RunConfig) => void;
  onRunPlanOnly: (config: RunConfig) => void;
  onRunScanOnly: (config: RunConfig) => void;
  onStartQA?: (config: RunConfig) => void;
  globalSettings?: GlobalSettings;
  onUpdateGlobalSettings?: (partial: Partial<GlobalSettings>) => void;
}

export default function LandingStep({
  projects,
  onResumeProject,
  onRemoveProject,
  onClearAllProjects,
  fetchProjects,
  checkProjectStatus,
  fetchProjectSettings,
  saveProjectSettings,
  onRunDirect,
  onRunArchitectOnly,
  onRunPlanOnly,
  onRunScanOnly,
  onStartQA,
  globalSettings,
  onUpdateGlobalSettings,
}: LandingStepProps) {
  useEffect(() => {
    fetchProjects();
    const interval = setInterval(fetchProjects, 30000);
    return () => clearInterval(interval);
  }, [fetchProjects]);

  const recentProjects = [...projects]
    .sort((a, b) => {
      const ta = a.last_modified ? new Date(a.last_modified).getTime() : 0;
      const tb = b.last_modified ? new Date(b.last_modified).getTime() : 0;
      return tb - ta;
    })
    .slice(0, 10);

  const [runHistory, setRunHistory] = useState<Record<string, RunInfo | null>>({});
  const [chainCounts, setChainCounts] = useState<Record<string, number>>({});
  const [removeConfirm, setRemoveConfirm] = useState<{ path: string; name: string } | null>(null);
  const [clearAllConfirm, setClearAllConfirm] = useState(false);

  useEffect(() => {
    if (recentProjects.length === 0) return;
    const paths = recentProjects.map((p) => p.path);
    paths.forEach((p) => {
      if (p in runHistory) return;
      const enc = encodeURIComponent(p);
      fetch(`/api/runs?path=${enc}&limit=1`)
        .then((r) => (r.ok ? r.json() : null))
        .then((data) => {
          const run = Array.isArray(data) && data.length > 0 ? data[0] : null;
          setRunHistory((prev) => ({ ...prev, [p]: run }));
        })
        .catch(() => {
          setRunHistory((prev) => ({ ...prev, [p]: null }));
        });
      // Fetch chain data for each project
      fetch(`/api/session/chain?path=${enc}`)
        .then((r) => (r.ok ? r.json() : []))
        .then((data) => {
          if (Array.isArray(data) && data.length > 1) {
            setChainCounts((prev) => ({ ...prev, [p]: data.length }));
          }
        })
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recentProjects.map((p) => p.path).join(",")]);

  return (
    <div className="min-h-screen bg-[#0C0C0C] flex flex-col items-center pt-24 pb-20 px-6">
      {/* Top Badge / System Status */}
      <div className="text-[var(--color-accent)] mb-6 text-[10px] tracking-[0.2em] border border-[#333] px-3 py-1 bg-[#121212] uppercase flex items-center font-mono">
        <BrainCog className="w-3.5 h-3.5 animate-pulse mr-2 shrink-0" /> Autonomous Coding Engine
      </div>

      {/* Main Logo Text */}
      <h1 className="text-5xl md:text-6xl font-bold tracking-widest text-[#E0E0E0] mb-3 flex items-center font-mono">
        SWARM<span className="text-[var(--color-accent)]">WEAVER</span><span className="animate-pulse text-[var(--color-accent)] ml-1 font-normal">_</span>
      </h1>
      <p className="text-[#555] mb-12 uppercase tracking-[0.15em] text-xs font-mono">
        <span className="text-[#888]">&gt;</span> What would you like to build today?
      </p>

      {/* Omnibar Command Center */}
      <div className="w-full max-w-4xl mb-16">
        <Omnibar
          isFocused={true}
          projects={projects}
          fetchProjects={fetchProjects}
          checkProjectStatus={checkProjectStatus}
          fetchProjectSettings={fetchProjectSettings}
          saveProjectSettings={saveProjectSettings}
          onRunDirect={onRunDirect}
          onRunArchitectOnly={onRunArchitectOnly}
          onRunPlanOnly={onRunPlanOnly}
          onRunScanOnly={onRunScanOnly}
          onStartQA={onStartQA}
          globalSettings={globalSettings}
          onUpdateGlobalSettings={onUpdateGlobalSettings}
        />
      </div>

      {/* Recent Projects */}
      <div className="w-full max-w-4xl">
        {/* Divider + Clear all */}
        <div className="flex items-center text-[10px] text-[#555] mb-6 uppercase tracking-[0.2em] font-mono">
          <div className="flex-1 h-px bg-[#333]" />
          <span className="px-4">Recent Projects</span>
          <div className="flex-1 h-px bg-[#333]" />
          {recentProjects.length > 0 && onClearAllProjects && (
            <button
              onClick={(e) => { e.stopPropagation(); setClearAllConfirm(true); }}
              className="ml-4 px-2 py-1 border border-[#333] text-[#555] hover:text-[var(--color-error)] hover:border-[var(--color-error)] transition-colors font-mono shrink-0"
              title="Clear all recent projects from history"
            >
              Clear all
            </button>
          )}
        </div>

        {recentProjects.length > 0 ? (
          <div className="space-y-2">
            {recentProjects.map((project) => {
              const pctDone = Math.round(project.percentage);
              const isDone = pctDone === 100;
              const barBlocks = 8;
              const filledBlocks = Math.round((pctDone / 100) * barBlocks);
              const asciiBar = "\u2593".repeat(filledBlocks) + "\u2591".repeat(barBlocks - filledBlocks);

              return (
                <div
                  key={project.path}
                  className="flex flex-col sm:flex-row sm:items-center justify-between p-3 px-4 border border-[#222] bg-[#121212] hover:border-[#444] hover:bg-[#1A1A1A] cursor-pointer transition-colors group gap-3 sm:gap-0"
                  onClick={(e) => { e.stopPropagation(); onResumeProject(project); }}
                >
                  <div className="flex items-center gap-4 min-w-0">
                    {(() => {
                      const modeKey = (project.mode ?? "feature") as Mode;
                      const ModeIcon = MODE_ICONS[modeKey] ?? MODE_ICONS.feature;
                      return <ModeIcon className="w-4 h-4 shrink-0" style={{ color: project.mode ? `var(--color-mode-${project.mode})` : "var(--color-text-muted)" }} />;
                    })()}
                    <span className="text-[#E0E0E0] group-hover:text-white transition-colors truncate font-bold font-mono">
                      {project.name}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 sm:gap-6 text-xs shrink-0 ml-7 sm:ml-0">
                    {project.mode && (
                      <span className="border border-[#333] px-2 py-0.5 text-[#555] bg-[#0C0C0C] text-[10px] uppercase tracking-wider font-mono">
                        {project.mode}
                      </span>
                    )}
                    {chainCounts[project.path] > 1 && (
                      <span
                        className="text-[10px] font-mono text-[var(--color-accent)] px-1.5 py-0.5 border border-[#333] bg-[#0C0C0C]"
                        title={`${chainCounts[project.path]} sessions in chain`}
                      >
                        {"\u2261"}{chainCounts[project.path]}
                      </span>
                    )}
                    <span className="tracking-widest font-mono hidden sm:block">
                      <span className="text-[var(--color-accent)]">{asciiBar.replace(/\u2591/g, "")}</span>
                      <span className="text-[#333]">{asciiBar.replace(/\u2593/g, "")}</span>
                    </span>
                    <span className="text-[#555] group-hover:text-[#888] transition-colors w-8 text-right font-mono">
                      {isDone ? "done" : `${pctDone}%`}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRemoveConfirm({ path: project.path, name: project.name });
                      }}
                      className="shrink-0 p-1 text-[#555] hover:text-[var(--color-error)] transition-colors border border-transparent hover:border-[var(--color-error)]"
                      title="Remove from recent"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <polyline points="3 6 5 6 21 6" />
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        <line x1="10" y1="11" x2="10" y2="17" />
                        <line x1="14" y1="11" x2="14" y2="17" />
                      </svg>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onResumeProject(project); }}
                      className={`text-[10px] font-mono font-bold px-2 py-1 border transition-colors shrink-0 ${
                        isDone
                          ? "border-[#333] text-[#555] hover:text-[#E0E0E0] hover:border-[#555] opacity-0 group-hover:opacity-100"
                          : "border-[var(--color-accent)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[#0C0C0C]"
                      }`}
                    >
                      {isDone ? "Open" : "Resume"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="border border-dashed border-[#333] bg-[#121212] px-4 py-6 text-center">
            <p className="text-[12px] text-[#555] font-mono">
              No recent projects yet.
            </p>
          </div>
        )}
      </div>

      <ConfirmModal
        open={!!removeConfirm}
        title="Remove from recent"
        message={
          removeConfirm
            ? `Remove "${removeConfirm.name}" from recent projects? You can still open it from the Omnibar.`
            : ""
        }
        confirmLabel="Remove"
        cancelLabel="Cancel"
        variant="default"
        onConfirm={() => {
          if (removeConfirm) {
            onRemoveProject(removeConfirm.path);
            setRemoveConfirm(null);
          }
        }}
        onCancel={() => setRemoveConfirm(null)}
      />

      <ConfirmModal
        open={clearAllConfirm}
        title="Clear all recent projects"
        message="Clear all recent projects from history? This only removes them from the list. You can still open projects from the Omnibar."
        confirmLabel="Clear all"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={() => {
          onClearAllProjects?.();
          setClearAllConfirm(false);
        }}
        onCancel={() => setClearAllConfirm(false)}
      />
    </div>
  );
}

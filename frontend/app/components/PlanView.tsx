"use client";

import { useState, useEffect, useCallback } from "react";

/* ── Types ── */

interface PlanTask {
  id?: string;
  title?: string;
  status?: string;
  priority?: string;
  description?: string;
  dependencies?: string[];
}

interface PlanData {
  mode: string;
  model: string;
  task_input: string;
  spec: string;
  phases: string[];
  tasks: PlanTask[];
  codebase_profile: Record<string, unknown> | null;
  iteration: number;
}

interface PlanViewProps {
  projectDir: string;
  mode: string;
  taskInput: string;
  model: string;
  onApprove: () => void;
  onReject: () => void;
  onModify: (feedback: string) => void;
}

/* ── Constants ── */

const MODE_DESC: Record<string, string> = {
  greenfield: "Build a new project from specification",
  feature: "Add features to an existing codebase",
  refactor: "Restructure or migrate existing code",
  fix: "Diagnose and fix bugs",
  evolve: "Improve existing code",
  security: "Scan and remediate vulnerabilities",
};

const PHASE_META: Record<string, { icon: string; desc: string }> = {
  initialize: { icon: "\u25B6", desc: "Create task list + scaffold" },
  analyze: { icon: "\u25C7", desc: "Analyze existing codebase" },
  plan: { icon: "\u2630", desc: "Plan tasks and dependencies" },
  implement: { icon: "\u2726", desc: "Implement features iteratively" },
  code: { icon: "\u2726", desc: "Implement code iteratively" },
  investigate: { icon: "\u25C7", desc: "Reproduce and diagnose issue" },
  fix: { icon: "\u2611", desc: "Fix and add regression tests" },
  audit: { icon: "\u25C8", desc: "Audit codebase" },
  improve: { icon: "\u2191", desc: "Implement improvements" },
  scan: { icon: "\u25A0", desc: "Scan for vulnerabilities" },
  remediate: { icon: "\u2611", desc: "Fix approved vulnerabilities" },
  migrate: { icon: "\u25B6", desc: "Execute migration steps" },
};

const STATUS_STYLE: Record<string, { icon: string; color: string }> = {
  done: { icon: "\u2713", color: "#10B981" },
  in_progress: { icon: "\u25B6", color: "var(--color-accent)" },
  pending: { icon: "\u25CB", color: "#555" },
  blocked: { icon: "\u25A0", color: "#EF4444" },
};

/* ── Component ── */

export function PlanView({ projectDir, mode, taskInput, model, onApprove, onReject }: PlanViewProps) {
  const [plan, setPlan] = useState<PlanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<"overview" | "spec" | "tasks">("overview");

  // Editing states
  const [editingSpec, setEditingSpec] = useState(false);
  const [specDraft, setSpecDraft] = useState("");
  const [editingTasks, setEditingTasks] = useState(false);
  const [tasksDraft, setTasksDraft] = useState("");
  const [saving, setSaving] = useState(false);

  // AI modification
  const [modifyFeedback, setModifyFeedback] = useState("");
  const [modifyTarget, setModifyTarget] = useState<"all" | "spec" | "tasks">("all");
  const [modifying, setModifying] = useState(false);
  const [modifyStatus, setModifyStatus] = useState<string | null>(null);

  // Fetch plan from disk
  const fetchPlan = useCallback(() => {
    if (!projectDir) { setLoading(false); return; }
    setLoading(true);
    const params = new URLSearchParams({ path: projectDir, mode, task_input: taskInput || "", model });
    fetch(`/api/plan?${params}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.plan) {
          setPlan(d.plan);
          setSpecDraft(d.plan.spec || "");
          setTasksDraft(JSON.stringify(d.plan.tasks || [], null, 2));
          if (d.plan.spec) setActiveSection("spec");
          else if (d.plan.tasks?.length > 0) setActiveSection("tasks");
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectDir, mode, taskInput, model]);

  useEffect(() => { fetchPlan(); }, [fetchPlan]);

  // Save spec to disk
  const saveSpec = async () => {
    if (!projectDir) return;
    setSaving(true);
    try {
      await fetch(`/api/plan/modify?path=${encodeURIComponent(projectDir)}&spec=${encodeURIComponent(specDraft)}`, { method: "POST" });
      setPlan((p) => p ? { ...p, spec: specDraft } : p);
      setEditingSpec(false);
    } catch { /* silent */ }
    setSaving(false);
  };

  // Save tasks to disk
  const saveTasks = async () => {
    if (!projectDir) return;
    setSaving(true);
    try {
      await fetch(`/api/plan/modify?path=${encodeURIComponent(projectDir)}&tasks=${encodeURIComponent(tasksDraft)}`, { method: "POST" });
      const parsed = JSON.parse(tasksDraft);
      const taskArray = Array.isArray(parsed) ? parsed : parsed.tasks || parsed.features || [];
      setPlan((p) => p ? { ...p, tasks: taskArray } : p);
      setEditingTasks(false);
    } catch { /* silent */ }
    setSaving(false);
  };

  // AI-powered modification
  const runAiModify = async () => {
    if (!projectDir || !modifyFeedback.trim()) return;
    setModifying(true);
    setModifyStatus("Claude is rewriting... (this may take 30-60s)");
    try {
      const params = new URLSearchParams({
        path: projectDir,
        feedback: modifyFeedback.trim(),
        target: modifyTarget,
        model,
      });
      // Call backend directly (not through Next.js proxy) to avoid timeout on long Claude calls
      const res = await fetch(`http://localhost:8000/api/plan/modify-with-ai?${params}`, { method: "POST" });
      const data = await res.json();

      if (data.status === "ok" && data.modified?.length > 0) {
        setModifyStatus(`Modified: ${data.modified.join(", ")}`);
        // Refresh plan from disk
        setTimeout(() => { fetchPlan(); setModifyStatus(null); setModifyFeedback(""); }, 1500);
      } else {
        setModifyStatus(data.spec_error || data.tasks_error || "No changes made");
        setTimeout(() => setModifyStatus(null), 3000);
      }
    } catch (e) {
      setModifyStatus("Connection failed — try again");
      setTimeout(() => setModifyStatus(null), 3000);
    }
    setModifying(false);
  };

  const totalTasks = plan?.tasks?.length ?? 0;
  const doneTasks = plan?.tasks?.filter((t) => t.status === "done").length ?? 0;
  const hasSpec = (plan?.spec?.length ?? 0) > 0;
  const hasTasks = totalTasks > 0;

  const tabCls = (tab: string) =>
    `px-2 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider transition-colors ${
      activeSection === tab
        ? "text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]"
        : "text-[#555] hover:text-[#888]"
    }`;

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0">
          <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Execution Plan</span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs font-mono text-[#555]">Loading plan...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
        <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Execution Plan</span>
        <span className="text-[10px] font-mono px-1.5 py-0.5 border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
          {mode}
        </span>
      </div>

      {/* Sub-tabs */}
      <div className="flex items-center border-b border-[#222] bg-[#0C0C0C] shrink-0 px-2">
        <button onClick={() => setActiveSection("overview")} className={tabCls("overview")}>Overview</button>
        <button onClick={() => setActiveSection("spec")} className={tabCls("spec")}>
          Spec {hasSpec && <span className="text-[9px] ml-1 text-[#555]">({Math.round((plan?.spec?.length ?? 0) / 1000)}K)</span>}
        </button>
        <button onClick={() => setActiveSection("tasks")} className={tabCls("tasks")}>
          Tasks {hasTasks && <span className="text-[9px] ml-1 text-[#555]">({totalTasks})</span>}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-4">

        {/* ── OVERVIEW ── */}
        {activeSection === "overview" && (
          <>
            <div className="text-[10px] font-mono text-[#888]">{MODE_DESC[mode] || mode}</div>

            {(taskInput || plan?.task_input) && (
              <div className="bg-[#121212] border border-[#222] p-2.5">
                <div className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-1">Task</div>
                <div className="text-xs font-mono text-[#E0E0E0] whitespace-pre-wrap">{taskInput || plan?.task_input}</div>
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <div className="bg-[#121212] border border-[#222] p-2 text-center">
                <div className="text-lg font-mono font-bold text-[#E0E0E0]">{plan?.phases?.length ?? 0}</div>
                <div className="text-[10px] font-mono text-[#555]">Phases</div>
              </div>
              <div className="bg-[#121212] border border-[#222] p-2 text-center">
                <div className="text-lg font-mono font-bold text-[#E0E0E0]">{totalTasks}</div>
                <div className="text-[10px] font-mono text-[#555]">Tasks</div>
              </div>
              <div className="bg-[#121212] border border-[#222] p-2 text-center">
                <div className="text-lg font-mono font-bold text-[#10B981]">{doneTasks}</div>
                <div className="text-[10px] font-mono text-[#555]">Done</div>
              </div>
            </div>

            {plan?.phases && plan.phases.length > 0 && (
              <div>
                <div className="text-[10px] font-mono text-[#555] uppercase tracking-wider mb-2">Phases</div>
                <div className="space-y-1">
                  {plan.phases.map((phase, i) => {
                    const meta = PHASE_META[phase] || { icon: "\u25CB", desc: phase };
                    return (
                      <div key={phase} className="flex items-center gap-2 py-1">
                        <span className="text-[10px] font-mono text-[#555] w-4 text-right shrink-0">{i + 1}</span>
                        <span className="text-xs font-mono text-[var(--color-accent)] w-4 shrink-0">{meta.icon}</span>
                        <span className="text-xs font-mono text-[#E0E0E0]">{phase}</span>
                        <span className="text-[10px] font-mono text-[#555] ml-auto">{meta.desc}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between text-[10px] font-mono">
              <span className="text-[#555]">Model</span>
              <span className="text-[#888]">{model}</span>
            </div>
          </>
        )}

        {/* ── SPEC TAB ── */}
        {activeSection === "spec" && (
          <>
            {hasSpec ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">Specification</span>
                  {!editingSpec ? (
                    <button onClick={() => { setSpecDraft(plan?.spec || ""); setEditingSpec(true); }}
                      className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">
                      Edit
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button onClick={saveSpec} disabled={saving}
                        className="text-[10px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-50">
                        {saving ? "Saving..." : "Save to disk"}
                      </button>
                      <button onClick={() => setEditingSpec(false)} className="text-[10px] font-mono text-[#555]">Cancel</button>
                    </div>
                  )}
                </div>
                {editingSpec ? (
                  <textarea value={specDraft} onChange={(e) => setSpecDraft(e.target.value)}
                    className="w-full h-[400px] bg-[#121212] border border-[#333] text-xs text-[#E0E0E0] font-mono p-3 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
                ) : (
                  <div className="bg-[#121212] border border-[#222] p-3 text-xs font-mono text-[#CCC] whitespace-pre-wrap max-h-[500px] overflow-y-auto leading-relaxed">
                    {plan?.spec}
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-[#121212] border border-[#222] p-4 text-center">
                <div className="text-xs font-mono text-[#555]">No specification generated yet</div>
              </div>
            )}
          </>
        )}

        {/* ── TASKS TAB ── */}
        {activeSection === "tasks" && (
          <>
            {hasTasks ? (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">
                    {totalTasks} tasks ({doneTasks} done, {totalTasks - doneTasks} pending)
                  </span>
                  {!editingTasks ? (
                    <button onClick={() => { setTasksDraft(JSON.stringify(plan?.tasks || [], null, 2)); setEditingTasks(true); }}
                      className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">
                      Edit JSON
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <button onClick={saveTasks} disabled={saving}
                        className="text-[10px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-50">
                        {saving ? "Saving..." : "Save to disk"}
                      </button>
                      <button onClick={() => setEditingTasks(false)} className="text-[10px] font-mono text-[#555]">Cancel</button>
                    </div>
                  )}
                </div>
                {editingTasks ? (
                  <textarea value={tasksDraft} onChange={(e) => setTasksDraft(e.target.value)}
                    className="w-full h-[400px] bg-[#121212] border border-[#333] text-xs text-[#E0E0E0] font-mono p-3 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
                ) : (
                  <div className="space-y-0.5">
                    {plan?.tasks?.map((task, i) => {
                      const si = STATUS_STYLE[task.status || "pending"] || STATUS_STYLE.pending;
                      return (
                        <div key={task.id || i} className="flex items-start gap-2 px-2 py-1.5 hover:bg-[#1A1A1A] transition-colors">
                          <span className="text-[10px] font-mono text-[#555] w-6 text-right shrink-0 mt-0.5">{task.id || `#${i + 1}`}</span>
                          <span className="text-xs font-mono shrink-0 mt-0.5" style={{ color: si.color }}>{si.icon}</span>
                          <div className="flex-1 min-w-0">
                            <span className="text-xs font-mono text-[#E0E0E0]">{task.title || task.description || `Task ${i + 1}`}</span>
                            {task.description && task.title && (
                              <div className="text-[10px] font-mono text-[#555] mt-0.5">{task.description}</div>
                            )}
                          </div>
                          {task.priority && (
                            <span className={`text-[9px] font-mono px-1 py-0.5 border shrink-0 ${
                              task.priority === "high" ? "text-[#EF4444] border-[#EF4444]/30" :
                              task.priority === "medium" ? "text-[#F59E0B] border-[#F59E0B]/30" :
                              "text-[#555] border-[#333]"
                            }`}>{task.priority}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-[#121212] border border-[#222] p-4 text-center">
                <div className="text-xs font-mono text-[#555]">No tasks generated yet</div>
              </div>
            )}
          </>
        )}
      </div>

      {/* AI Modify bar */}
      <div className="px-4 py-2 border-t border-[#222] bg-[#0C0C0C] shrink-0 space-y-2">
        <div className="flex items-center gap-2">
          <select value={modifyTarget} onChange={(e) => setModifyTarget(e.target.value as "all" | "spec" | "tasks")}
            className="bg-[#1A1A1A] text-[#E0E0E0] text-[10px] font-mono px-1.5 py-1 border border-[#333] focus:outline-none focus:border-[var(--color-accent)]">
            <option value="all">Modify All</option>
            <option value="spec">Spec Only</option>
            <option value="tasks">Tasks Only</option>
          </select>
          <input
            value={modifyFeedback}
            onChange={(e) => setModifyFeedback(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && modifyFeedback.trim()) { e.preventDefault(); runAiModify(); } }}
            placeholder="Tell Claude what to change..."
            disabled={modifying}
            className="flex-1 bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] placeholder:text-[#555] py-1 px-2 focus:outline-none focus:border-[var(--color-accent)] font-mono disabled:opacity-50"
          />
          <button onClick={runAiModify} disabled={modifying || !modifyFeedback.trim()}
            className="px-3 py-1 text-[10px] font-mono font-bold bg-[#F59E0B] text-[#0C0C0C] hover:brightness-110 transition-all disabled:opacity-30 shrink-0">
            {modifying ? "Modifying..." : "Modify"}
          </button>
        </div>
        {modifyStatus && (
          <div className={`text-[10px] font-mono ${modifying ? "text-[#F59E0B] animate-pulse" : "text-[#10B981]"}`}>
            {modifyStatus}
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="px-4 py-2.5 border-t border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
        <span className="text-[10px] font-mono text-[#555]">Review before execution</span>
        <div className="flex items-center gap-2">
          <button onClick={onReject}
            className="px-3 py-1 text-[10px] font-mono font-bold border border-[#EF4444] text-[#EF4444] hover:bg-[#EF4444] hover:text-[#0C0C0C] transition-colors">
            Reject
          </button>
          <button onClick={onApprove}
            className="px-3 py-1 text-[10px] font-mono font-bold bg-[#10B981] text-[#0C0C0C] hover:brightness-110 transition-all">
            Approve & Execute
          </button>
        </div>
      </div>
    </div>
  );
}

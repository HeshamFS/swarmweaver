/**
 * @deprecated This full-page component is replaced by TaskReviewBlock in
 * chat-blocks/TaskReviewBlock.tsx, which renders inside ChatWizardFeed with
 * the TUI aesthetic. Kept for reference only — do not import.
 */
"use client";

import { useState, useEffect, useRef } from "react";
import type { TaskData } from "../../hooks/useSwarmWeaver";

interface PlanReviewProps {
  isLoading: boolean;
  tasks: TaskData | null;
  projectDir: string;
  onApproveAndBuild: () => void;
  onModifyPlan: () => void;
  onBack: () => void;
}

export default function PlanReview({ isLoading, tasks, projectDir, onApproveAndBuild, onModifyPlan, onBack }: PlanReviewProps) {

  // Editable task titles: map task index -> edited title
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editedTitles, setEditedTitles] = useState<Record<number, string>>({});
  const editInputRef = useRef<HTMLInputElement>(null);

  // Toggle tasks: track which tasks are skipped
  const [skippedTasks, setSkippedTasks] = useState<Set<number>>(new Set());

  // Regenerate feedback
  const [showRegenerateInput, setShowRegenerateInput] = useState(false);
  const [regenerateFeedback, setRegenerateFeedback] = useState("");

  const hasTasks = tasks && tasks.tasks.length > 0;
  const isComplete = hasTasks && !isLoading;

  // Focus input when editing starts
  useEffect(() => {
    if (editingIdx !== null && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingIdx]);

  const taskStats = (() => {
    if (!tasks) return null;
    const allTasks = tasks.tasks;
    const categories = new Set(allTasks.map((t) => t.category).filter(Boolean));
    const includedCount = allTasks.length - skippedTasks.size;
    // Estimate sessions: roughly 5-7 tasks per session
    const minSessions = Math.max(1, Math.ceil(includedCount / 7));
    const maxSessions = Math.max(1, Math.ceil(includedCount / 5));
    const sessionEstimate = minSessions === maxSessions ? `${minSessions}` : `${minSessions}-${maxSessions}`;
    return { total: allTasks.length, included: includedCount, categories: categories.size, sessionEstimate };
  })();

  const startEditing = (idx: number, currentTitle: string) => {
    setEditingIdx(idx);
    setEditValue(editedTitles[idx] || currentTitle);
  };

  const saveEdit = (idx: number) => {
    if (editValue.trim()) {
      setEditedTitles((prev) => ({ ...prev, [idx]: editValue.trim() }));
    }
    setEditingIdx(null);
  };

  const cancelEdit = () => {
    setEditingIdx(null);
    setEditValue("");
  };

  const toggleTask = (idx: number) => {
    setSkippedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const handleRegenerate = () => {
    // For now, regenerate triggers onModifyPlan. If onRegenerate existed, we'd call it.
    if (regenerateFeedback.trim()) {
      // TODO: Pass feedback to a regenerate handler when available
      setRegenerateFeedback("");
      setShowRegenerateInput(false);
      onModifyPlan();
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      {/* Header */}
      <div className="flex items-center gap-4 mb-10">
        <button onClick={onBack} className="p-2 rounded-xl hover:bg-[var(--surface-overlay)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)] border border-[var(--border-subtle)]">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div>
          <h2 className="text-xl font-semibold text-[var(--text-primary)]">
            {isComplete ? "Review Your Plan" : "Planning Your Tasks"}
          </h2>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            {isComplete ? "Review the planned tasks before execution" : "The agent is analyzing and creating a task plan"}
          </p>
        </div>
      </div>

      {/* Spinner */}
      {isLoading && !hasTasks && (
        <div className="text-center py-16">
          <div className="inline-flex items-center gap-2.5 text-[var(--text-muted)] text-sm">
            <svg className="w-4 h-4 animate-spin text-[var(--accent)]" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
            Analyzing and planning...
          </div>
        </div>
      )}

      {/* Task List */}
      {isComplete && tasks && (
        <div className="space-y-5">
          {/* Estimated effort summary */}
          {taskStats && (
            <div className="flex items-center gap-3 px-5 py-3.5 rounded-xl bg-[var(--surface-raised)] border border-[var(--border-subtle)]">
              <span className="text-sm text-[var(--text-primary)] font-medium">
                {taskStats.included} task{taskStats.included !== 1 ? "s" : ""}
              </span>
              <span className="text-[var(--text-muted)]">&middot;</span>
              <span className="text-sm text-[var(--text-secondary)]">
                {taskStats.categories} categor{taskStats.categories !== 1 ? "ies" : "y"}
              </span>
              <span className="text-[var(--text-muted)]">&middot;</span>
              <span className="text-sm text-[var(--text-secondary)]">
                est. {taskStats.sessionEstimate} session{taskStats.sessionEstimate === "1" ? "" : "s"}
              </span>
              {skippedTasks.size > 0 && (
                <>
                  <span className="text-[var(--text-muted)]">&middot;</span>
                  <span className="text-sm text-[var(--text-muted)]">
                    {skippedTasks.size} skipped
                  </span>
                </>
              )}
              {tasks.metadata?.mode && (
                <>
                  <span className="ml-auto text-xs font-mono px-2 py-0.5 rounded-md bg-[var(--accent-glow)] text-[var(--accent)] border border-[var(--accent)]/20">
                    {tasks.metadata.mode}
                  </span>
                </>
              )}
            </div>
          )}

          {/* Task items */}
          <div className="rounded-xl border border-[var(--border-subtle)] overflow-hidden divide-y divide-[var(--border-subtle)]">
            {tasks.tasks.map((task, i) => {
              const isSkipped = skippedTasks.has(i);
              const isEditing = editingIdx === i;
              const displayTitle = editedTitles[i] || task.title;

              return (
                <div
                  key={task.id || i}
                  className={`px-5 py-4 transition-colors ${
                    isSkipped
                      ? "bg-[var(--surface-raised)]/50 opacity-50"
                      : "bg-[var(--surface-raised)] hover:bg-[var(--surface-overlay)]"
                  }`}
                >
                  <div className="flex items-start gap-3.5">
                    {/* Toggle checkbox */}
                    <button
                      onClick={() => toggleTask(i)}
                      className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-all duration-200 ${
                        !isSkipped
                          ? "border-[var(--accent)] bg-[var(--accent)]"
                          : "border-[var(--border-default)] hover:border-[var(--text-muted)]"
                      }`}
                    >
                      {!isSkipped && (
                        <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>

                    <div className="w-6 h-6 rounded-lg bg-[var(--surface-overlay)] flex items-center justify-center text-xs text-[var(--text-muted)] font-mono shrink-0 mt-0.5 border border-[var(--border-subtle)]">
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2.5 mb-1">
                        {isEditing ? (
                          <input
                            ref={editInputRef}
                            type="text"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") saveEdit(i);
                              if (e.key === "Escape") cancelEdit();
                            }}
                            onBlur={() => saveEdit(i)}
                            className="flex-1 text-sm font-medium text-[var(--text-primary)] bg-[var(--surface)] px-2 py-0.5 rounded-lg border border-[var(--accent)] outline-none"
                          />
                        ) : (
                          <span
                            className={`text-sm font-medium cursor-pointer hover:text-[var(--accent)] transition-colors ${
                              isSkipped ? "line-through text-[var(--text-muted)]" : "text-[var(--text-primary)]"
                            }`}
                            onDoubleClick={() => startEditing(i, displayTitle)}
                            title="Double-click to edit"
                          >
                            {displayTitle}
                          </span>
                        )}
                        {task.category && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-[var(--surface-overlay)] text-[var(--text-muted)] uppercase tracking-wider border border-[var(--border-subtle)]">
                            {task.category}
                          </span>
                        )}
                        {task.priority !== undefined && task.priority <= 2 && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-[var(--accent-glow)] text-[var(--accent)] border border-[var(--accent)]/20">
                            P{task.priority}
                          </span>
                        )}
                      </div>
                      {task.description && <p className={`text-xs leading-relaxed ${isSkipped ? "text-[var(--text-muted)]" : "text-[var(--text-muted)]"}`}>{task.description}</p>}
                      {task.depends_on && task.depends_on.length > 0 && (
                        <div className="mt-1.5 text-[11px] text-[var(--text-muted)] font-mono">
                          Depends on: {task.depends_on.join(", ")}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Regenerate feedback input */}
          {showRegenerateInput && (
            <div className="p-5 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-raised)] space-y-3">
              <label className="block text-sm font-medium text-[var(--text-secondary)]">What should be different?</label>
              <textarea
                value={regenerateFeedback}
                onChange={(e) => setRegenerateFeedback(e.target.value)}
                placeholder="E.g., Split the auth tasks into smaller steps, add more test tasks..."
                rows={3}
                className="w-full px-3.5 py-2.5 text-sm rounded-xl border border-[var(--border-default)] bg-[var(--surface)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] resize-y"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleRegenerate}
                  disabled={!regenerateFeedback.trim()}
                  className={`px-4 py-2.5 text-sm rounded-xl font-medium transition-all ${
                    regenerateFeedback.trim()
                      ? "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white"
                      : "bg-[var(--surface-overlay)] text-[var(--text-muted)] cursor-not-allowed"
                  }`}
                >
                  Regenerate Plan
                </button>
                <button
                  onClick={() => { setShowRegenerateInput(false); setRegenerateFeedback(""); }}
                  className="px-4 py-2.5 text-sm rounded-xl text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={() => setShowRegenerateInput(!showRegenerateInput)}
              className="px-5 py-3.5 text-sm rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] hover:text-[var(--text-primary)] transition-all flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
              </svg>
              Regenerate
            </button>
            <button
              onClick={onModifyPlan}
              className="px-5 py-3.5 text-sm rounded-xl border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--surface-overlay)] hover:text-[var(--text-primary)] transition-all"
            >
              Edit Plan
            </button>
            <button
              onClick={onApproveAndBuild}
              className="flex-1 py-3.5 rounded-xl text-sm font-semibold bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-white shadow-lg shadow-[var(--accent)]/20 hover:shadow-[var(--accent)]/30 transition-all flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              Approve &amp; Build
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

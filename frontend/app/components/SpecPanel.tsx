"use client";

import { useState, useEffect } from "react";

interface SpecEntry {
  task_id: string;
  author: string;
  created_at: string;
  size: number;
}

export function SpecPanel({ projectDir }: { projectDir: string }) {
  const [specs, setSpecs] = useState<SpecEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSpec, setActiveSpec] = useState<string | null>(null);
  const [specContent, setSpecContent] = useState<string>("");
  const [specLoading, setSpecLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newTaskId, setNewTaskId] = useState("");
  const [newContent, setNewContent] = useState("");

  useEffect(() => {
    if (!projectDir) return;
    fetchSpecs();
  }, [projectDir]);

  const fetchSpecs = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/specs?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      setSpecs(data.specs || []);
    } catch {
      setSpecs([]);
    } finally {
      setLoading(false);
    }
  };

  const loadSpec = async (taskId: string) => {
    setSpecLoading(true);
    setActiveSpec(taskId);
    setEditing(false);
    try {
      const res = await fetch(`/api/specs/${encodeURIComponent(taskId)}?path=${encodeURIComponent(projectDir)}`);
      const data = await res.json();
      setSpecContent(data.content || "");
    } catch {
      setSpecContent("Failed to load spec.");
    } finally {
      setSpecLoading(false);
    }
  };

  const saveSpec = async (taskId: string, content: string) => {
    try {
      await fetch(`/api/specs/${encodeURIComponent(taskId)}?path=${encodeURIComponent(projectDir)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      setEditing(false);
      setSpecContent(content);
      fetchSpecs();
    } catch {
      // Ignore
    }
  };

  const createSpec = async () => {
    if (!newTaskId.trim() || !newContent.trim()) return;
    await saveSpec(newTaskId.trim(), newContent);
    setShowCreate(false);
    setNewTaskId("");
    setNewContent("");
    fetchSpecs();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-text-muted">
        Loading specs...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised shrink-0 flex items-center justify-between">
        <span className="text-xs font-mono text-text-muted">
          Specs ({specs.length})
        </span>
        <button
          onClick={() => { setShowCreate(!showCreate); setActiveSpec(null); }}
          className="text-xs text-accent hover:text-accent-hover transition-colors"
        >
          {showCreate ? "Cancel" : "+ Create"}
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="px-3 py-2 border-b border-border-subtle space-y-2 shrink-0">
          <input
            type="text"
            value={newTaskId}
            onChange={(e) => setNewTaskId(e.target.value)}
            placeholder="Task ID (e.g., FEAT-001)"
            className="w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-primary placeholder:text-text-muted"
          />
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="Spec content (markdown)"
            rows={6}
            className="w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-text-primary placeholder:text-text-muted font-mono resize-none"
          />
          <button
            onClick={createSpec}
            className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-hover transition-colors"
          >
            Create Spec
          </button>
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 min-h-0 flex">
        {/* Spec list */}
        <div className="w-40 border-r border-border-subtle overflow-y-auto shrink-0">
          {specs.length === 0 ? (
            <div className="p-3 text-[10px] text-text-muted text-center">
              No specs yet
            </div>
          ) : (
            <div className="divide-y divide-border-subtle/50">
              {specs.map((spec) => (
                <button
                  key={spec.task_id}
                  onClick={() => loadSpec(spec.task_id)}
                  className={`w-full text-left px-3 py-2 transition-colors ${
                    activeSpec === spec.task_id
                      ? "bg-accent/10 border-l-2 border-accent"
                      : "hover:bg-surface-raised/50 border-l-2 border-transparent"
                  }`}
                >
                  <div className="text-xs font-mono text-text-primary">{spec.task_id}</div>
                  <div className="text-[10px] text-text-muted">
                    {spec.author && `by ${spec.author} | `}
                    {Math.round(spec.size / 1024)}KB
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Spec content viewer */}
        <div className="flex-1 min-w-0 overflow-y-auto">
          {activeSpec ? (
            specLoading ? (
              <div className="flex items-center justify-center h-full text-xs text-text-muted">
                Loading...
              </div>
            ) : editing ? (
              <div className="flex flex-col h-full">
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="flex-1 w-full p-3 bg-surface text-xs font-mono text-text-primary resize-none focus:outline-none"
                />
                <div className="flex gap-2 p-2 border-t border-border-subtle">
                  <button
                    onClick={() => saveSpec(activeSpec, editContent)}
                    className="rounded-md bg-accent px-3 py-1 text-xs font-medium text-white hover:bg-accent-hover transition-colors"
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="rounded-md border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="relative">
                <button
                  onClick={() => { setEditing(true); setEditContent(specContent); }}
                  className="absolute top-2 right-2 text-[10px] font-mono px-2 py-0.5 rounded border border-accent/30 text-accent hover:bg-accent/10 transition-colors z-10"
                >
                  Edit
                </button>
                <div className="p-3 prose-invert text-xs">
                  <pre className="whitespace-pre-wrap font-mono text-text-secondary leading-relaxed">
                    {specContent}
                  </pre>
                </div>
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-xs text-text-muted">
              Select a spec to view
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

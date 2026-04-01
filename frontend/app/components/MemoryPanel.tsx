"use client";

import { useState, useEffect, useCallback } from "react";

interface ClaudeMdFile {
  path: string;
  scope: string;
  content: string;
  is_rules: boolean;
}

interface MemoryFile {
  path: string;
  name: string;
  description: string;
  memory_type: string;
  content: string;
  mtime: number;
  age_days: number;
}

interface MemoryPanelProps {
  projectDir: string;
}

const TYPE_COLORS: Record<string, string> = {
  user: "text-[#3B82F6] border-[#3B82F6]/30",
  feedback: "text-[#F59E0B] border-[#F59E0B]/30",
  project: "text-[#10B981] border-[#10B981]/30",
  reference: "text-[#bc8cff] border-[#bc8cff]/30",
};

export function MemoryPanel({ projectDir }: MemoryPanelProps) {
  const [activeView, setActiveView] = useState<"claude-md" | "index" | "files">("claude-md");
  const [claudeMdFiles, setClaudeMdFiles] = useState<ClaudeMdFile[]>([]);
  const [memoryFiles, setMemoryFiles] = useState<MemoryFile[]>([]);
  const [memoryIndex, setMemoryIndex] = useState("");
  const [loading, setLoading] = useState(true);

  // Edit states
  const [editingScope, setEditingScope] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editingIndex, setEditingIndex] = useState(false);
  const [indexDraft, setIndexDraft] = useState("");
  const [saving, setSaving] = useState(false);

  // New memory file
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("project");
  const [newDesc, setNewDesc] = useState("");
  const [newContent, setNewContent] = useState("");

  // Selected file detail
  const [selectedFile, setSelectedFile] = useState<MemoryFile | null>(null);

  const fetchAll = useCallback(() => {
    if (!projectDir) { setLoading(false); return; }
    const enc = encodeURIComponent(projectDir);
    Promise.all([
      fetch(`/api/memory/claude-md?path=${enc}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`/api/memory/files?scope=project&path=${enc}`).then((r) => r.ok ? r.json() : null).catch(() => null),
      fetch(`/api/memory/files?scope=global`).then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([claudeMd, projMem, globalMem]) => {
      if (claudeMd?.files) setClaudeMdFiles(claudeMd.files);
      const allFiles: MemoryFile[] = [];
      if (globalMem?.files) allFiles.push(...globalMem.files.map((f: MemoryFile) => ({ ...f, memory_type: f.memory_type || "global" })));
      if (projMem?.files) allFiles.push(...projMem.files);
      setMemoryFiles(allFiles);
      if (projMem?.index) { setMemoryIndex(projMem.index); setIndexDraft(projMem.index); }
    }).finally(() => setLoading(false));
  }, [projectDir]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const saveClaudeMd = async () => {
    if (!editingScope) return;
    setSaving(true);
    await fetch("/api/memory/claude-md", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: editingScope, content: editContent, path: projectDir }),
    }).catch(() => {});
    setEditingScope(null);
    setSaving(false);
    fetchAll();
  };

  const saveIndex = async () => {
    setSaving(true);
    await fetch("/api/memory/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: "project", content: indexDraft, path: projectDir }),
    }).catch(() => {});
    setEditingIndex(false);
    setSaving(false);
    fetchAll();
  };

  const createMemory = async () => {
    if (!newName.trim() || !newContent.trim()) return;
    setSaving(true);
    await fetch("/api/memory/files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newName.trim(),
        content: newContent,
        type: newType,
        description: newDesc,
        scope: "project",
        path: projectDir,
      }),
    }).catch(() => {});
    setShowCreate(false);
    setNewName(""); setNewType("project"); setNewDesc(""); setNewContent("");
    setSaving(false);
    fetchAll();
  };

  const deleteMemory = async (filename: string) => {
    await fetch(`/api/memory/files/${encodeURIComponent(filename)}?scope=project&path=${encodeURIComponent(projectDir)}`, {
      method: "DELETE",
    }).catch(() => {});
    setSelectedFile(null);
    fetchAll();
  };

  const tabCls = (tab: string) =>
    `px-2 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wider transition-colors ${
      activeView === tab
        ? "text-[var(--color-accent)] border-b-2 border-[var(--color-accent)]"
        : "text-[#555] hover:text-[#888]"
    }`;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <span className="text-xs font-mono text-[#555]">Loading memory...</span>
      </div>
    );
  }

  // File detail view
  if (selectedFile) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={() => setSelectedFile(null)} className="text-[#555] hover:text-[#E0E0E0] text-xs font-mono">{"\u2190"}</button>
            <span className="text-xs font-mono font-medium text-[#E0E0E0]">{selectedFile.name}</span>
            <span className={`text-[9px] font-mono px-1 py-0.5 border ${TYPE_COLORS[selectedFile.memory_type] || "text-[#555] border-[#333]"}`}>
              {selectedFile.memory_type}
            </span>
          </div>
          <button onClick={() => { const parts = selectedFile.path.split(/[/\\]/); deleteMemory(parts[parts.length - 1]); }}
            className="text-[10px] font-mono text-[#EF4444] hover:underline">Delete</button>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-2">
          {selectedFile.description && (
            <div className="text-[10px] font-mono text-[#888]">{selectedFile.description}</div>
          )}
          <div className="text-[9px] font-mono text-[#444]">
            {selectedFile.age_days === 0 ? "Updated today" : `${selectedFile.age_days} days old`}
            {selectedFile.age_days > 1 && (
              <span className="text-[#F59E0B] ml-2">May be stale — verify before relying on it</span>
            )}
          </div>
          <div className="bg-[#121212] border border-[#222] p-3 text-xs font-mono text-[#CCC] whitespace-pre-wrap leading-relaxed">
            {selectedFile.content}
          </div>
        </div>
      </div>
    );
  }

  // Create memory view
  if (showCreate) {
    return (
      <div className="flex flex-col h-full">
        <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center gap-2">
          <button onClick={() => setShowCreate(false)} className="text-[#555] hover:text-[#E0E0E0] text-xs font-mono">{"\u2190"}</button>
          <span className="text-xs font-mono font-medium text-[#E0E0E0]">New Memory</span>
        </div>
        <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3">
          <div className="flex gap-2">
            <label className="block flex-1">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Name</span>
              <input value={newName} onChange={(e) => setNewName(e.target.value)}
                className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)]" />
            </label>
            <label className="block w-28">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Type</span>
              <select value={newType} onChange={(e) => setNewType(e.target.value)}
                className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none">
                <option value="user">user</option>
                <option value="feedback">feedback</option>
                <option value="project">project</option>
                <option value="reference">reference</option>
              </select>
            </label>
          </div>
          <label className="block">
            <span className="text-[10px] text-[#555] mb-1 block font-mono">Description (one line)</span>
            <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
              className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)]" />
          </label>
          <label className="block">
            <span className="text-[10px] text-[#555] mb-1 block font-mono">Content</span>
            <textarea value={newContent} onChange={(e) => setNewContent(e.target.value)} rows={10}
              className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
          </label>
          <button onClick={createMemory} disabled={saving || !newName.trim() || !newContent.trim()}
            className="px-3 py-1 text-[10px] font-mono font-bold bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-30">
            {saving ? "Saving..." : "Save Memory"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2.5 border-b border-[#222] bg-[#0C0C0C] shrink-0 flex items-center justify-between">
        <span className="text-xs font-mono font-medium text-[#E0E0E0] uppercase tracking-wider">Memory</span>
      </div>

      {/* Sub-tabs */}
      <div className="flex items-center border-b border-[#222] bg-[#0C0C0C] shrink-0 px-2">
        <button onClick={() => setActiveView("claude-md")} className={tabCls("claude-md")}>CLAUDE.md</button>
        <button onClick={() => setActiveView("index")} className={tabCls("index")}>Index</button>
        <button onClick={() => setActiveView("files")} className={tabCls("files")}>
          Files ({memoryFiles.length})
        </button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3">

        {/* CLAUDE.MD VIEW */}
        {activeView === "claude-md" && (
          <>
            {claudeMdFiles.length === 0 ? (
              <div className="bg-[#121212] border border-[#222] p-3 text-center">
                <div className="text-xs font-mono text-[#555]">No CLAUDE.md files found</div>
                <div className="text-[10px] font-mono text-[#444] mt-1">
                  Create one at ~/.swarmweaver/CLAUDE.md (global) or .swarmweaver/CLAUDE.md (project)
                </div>
                <button onClick={() => { setEditingScope("project"); setEditContent("# Project Instructions\n\n"); }}
                  className="mt-2 px-3 py-1 text-[10px] font-mono text-[var(--color-accent)] border border-[var(--color-accent)]/30 hover:bg-[var(--color-accent)]/10">
                  Create Project CLAUDE.md
                </button>
              </div>
            ) : (
              claudeMdFiles.map((f) => (
                <div key={f.path} className="bg-[#121212] border border-[#222]">
                  <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#222]">
                    <div className="flex items-center gap-2">
                      <span className={`text-[9px] font-mono px-1 py-0.5 border ${
                        f.scope === "global" ? "text-[#3B82F6] border-[#3B82F6]/30" :
                        f.scope === "local" ? "text-[#F59E0B] border-[#F59E0B]/30" :
                        "text-[#10B981] border-[#10B981]/30"
                      }`}>
                        {f.scope}
                      </span>
                      <span className="text-[10px] font-mono text-[#555] truncate">{f.path}</span>
                    </div>
                    <button onClick={() => { setEditingScope(f.scope); setEditContent(f.content); }}
                      className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">Edit</button>
                  </div>
                  {editingScope === f.scope ? (
                    <div className="p-2 space-y-2">
                      <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} rows={12}
                        className="w-full bg-[#1A1A1A] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
                      <div className="flex items-center gap-2">
                        <button onClick={saveClaudeMd} disabled={saving}
                          className="px-3 py-1 text-[10px] font-mono font-bold bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-50">
                          {saving ? "Saving..." : "Save"}
                        </button>
                        <button onClick={() => setEditingScope(null)} className="px-3 py-1 text-[10px] font-mono text-[#555]">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 text-xs font-mono text-[#CCC] whitespace-pre-wrap max-h-[200px] overflow-y-auto leading-relaxed">
                      {f.content.slice(0, 500)}{f.content.length > 500 ? "..." : ""}
                    </div>
                  )}
                </div>
              ))
            )}
            {!claudeMdFiles.some((f) => f.scope === "global") && (
              <button onClick={() => { setEditingScope("global"); setEditContent("# Global SwarmWeaver Instructions\n\n"); }}
                className="w-full px-3 py-2 text-[10px] font-mono text-[#555] border border-dashed border-[#333] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] transition-colors">
                + Create Global CLAUDE.md
              </button>
            )}
          </>
        )}

        {/* INDEX VIEW */}
        {activeView === "index" && (
          <>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">MEMORY.md Index</span>
              {!editingIndex ? (
                <button onClick={() => { setIndexDraft(memoryIndex); setEditingIndex(true); }}
                  className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">Edit</button>
              ) : (
                <div className="flex items-center gap-2">
                  <button onClick={saveIndex} disabled={saving}
                    className="text-[10px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent)] text-[#0C0C0C] disabled:opacity-50">Save</button>
                  <button onClick={() => setEditingIndex(false)} className="text-[10px] font-mono text-[#555]">Cancel</button>
                </div>
              )}
            </div>
            {editingIndex ? (
              <textarea value={indexDraft} onChange={(e) => setIndexDraft(e.target.value)} rows={15}
                className="w-full bg-[#121212] border border-[#333] text-xs text-[#E0E0E0] font-mono px-2 py-1.5 focus:outline-none focus:border-[var(--color-accent)] resize-y" />
            ) : (
              <div className="bg-[#121212] border border-[#222] p-3 text-xs font-mono text-[#CCC] whitespace-pre-wrap leading-relaxed min-h-[100px]">
                {memoryIndex || "Empty index. Memories will be indexed here as they are created."}
              </div>
            )}
            <div className="text-[9px] font-mono text-[#444]">
              Max 200 lines / 25KB. Always loaded into agent prompt.
            </div>
          </>
        )}

        {/* FILES VIEW */}
        {activeView === "files" && (
          <>
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono text-[#555] uppercase tracking-wider">Topic Files</span>
              <button onClick={() => setShowCreate(true)}
                className="text-[10px] font-mono text-[var(--color-accent)] hover:underline">+ Create</button>
            </div>
            {memoryFiles.length === 0 ? (
              <div className="bg-[#121212] border border-[#222] p-4 text-center">
                <div className="text-xs font-mono text-[#555]">No memory files yet</div>
                <div className="text-[10px] font-mono text-[#444] mt-1">Create topic files to store knowledge</div>
              </div>
            ) : (
              <div className="divide-y divide-[#222]">
                {memoryFiles.map((f) => (
                  <button key={f.path} onClick={() => setSelectedFile(f)}
                    className="w-full text-left py-2 hover:bg-[#1A1A1A] transition-colors">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-xs font-mono text-[#E0E0E0]">{f.name}</span>
                      <span className={`text-[9px] font-mono px-1 py-0.5 border ${TYPE_COLORS[f.memory_type] || "text-[#555] border-[#333]"}`}>
                        {f.memory_type}
                      </span>
                      <span className="text-[9px] font-mono text-[#444] ml-auto">
                        {f.age_days === 0 ? "today" : `${f.age_days}d ago`}
                      </span>
                    </div>
                    {f.description && (
                      <div className="text-[10px] font-mono text-[#555] truncate">{f.description}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

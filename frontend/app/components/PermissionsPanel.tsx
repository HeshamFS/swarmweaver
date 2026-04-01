"use client";

import { useState, useEffect } from "react";

interface ToolPermission {
  tool: string;
  category: string;
  permission: "allow" | "deny" | "ask";
  description: string;
}

const DEFAULT_PERMISSIONS: ToolPermission[] = [
  { tool: "Bash", category: "execution", permission: "ask", description: "Execute shell commands" },
  { tool: "Write", category: "files", permission: "allow", description: "Create new files" },
  { tool: "Edit", category: "files", permission: "allow", description: "Edit existing files" },
  { tool: "Read", category: "files", permission: "allow", description: "Read file contents" },
  { tool: "Glob", category: "search", permission: "allow", description: "Search files by pattern" },
  { tool: "Grep", category: "search", permission: "allow", description: "Search file contents" },
  { tool: "WebSearch", category: "network", permission: "ask", description: "Search the web" },
  { tool: "WebFetch", category: "network", permission: "ask", description: "Fetch web content" },
  { tool: "git push", category: "git", permission: "deny", description: "Push to remote repository" },
  { tool: "git reset --hard", category: "git", permission: "deny", description: "Hard reset git state" },
  { tool: "rm -rf", category: "dangerous", permission: "deny", description: "Recursive force delete" },
  { tool: "pip install", category: "packages", permission: "ask", description: "Install Python packages" },
  { tool: "npm install", category: "packages", permission: "ask", description: "Install Node packages" },
];

const CATEGORY_COLORS: Record<string, string> = {
  execution: "text-warning bg-warning/10 border-warning/20",
  files: "text-info bg-info/10 border-info/20",
  search: "text-success bg-success/10 border-success/20",
  network: "text-accent bg-accent/10 border-accent/20",
  git: "text-error bg-error/10 border-error/20",
  dangerous: "text-error bg-error/10 border-error/20",
  packages: "text-warning bg-warning/10 border-warning/20",
};

const PERMISSION_STYLES: Record<string, { label: string; cls: string }> = {
  allow: { label: "Allow", cls: "text-success bg-success/10 border-success/30" },
  deny: { label: "Deny", cls: "text-error bg-error/10 border-error/30" },
  ask: { label: "Ask", cls: "text-warning bg-warning/10 border-warning/30" },
};

interface PermissionsPanelProps {
  projectDir: string;
}

export function PermissionsPanel({ projectDir }: PermissionsPanelProps) {
  const [permissions, setPermissions] = useState<ToolPermission[]>(DEFAULT_PERMISSIONS);
  const [filter, setFilter] = useState<string>("all");
  const [dirty, setDirty] = useState(false);

  // Load saved permissions
  useEffect(() => {
    if (!projectDir) return;
    const enc = encodeURIComponent(projectDir);
    fetch(`/api/projects/settings?path=${enc}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.settings?.tool_permissions) {
          const saved = d.settings.tool_permissions as Record<string, string>;
          setPermissions((prev) =>
            prev.map((p) => ({
              ...p,
              permission: (saved[p.tool] as "allow" | "deny" | "ask") || p.permission,
            }))
          );
        }
      })
      .catch(() => {});
  }, [projectDir]);

  const handlePermissionChange = (tool: string, newPerm: "allow" | "deny" | "ask") => {
    setPermissions((prev) =>
      prev.map((p) => (p.tool === tool ? { ...p, permission: newPerm } : p))
    );
    setDirty(true);
  };

  const handleSave = () => {
    const permMap: Record<string, string> = {};
    permissions.forEach((p) => { permMap[p.tool] = p.permission; });

    fetch(`/api/projects/settings?path=${encodeURIComponent(projectDir)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_permissions: permMap }),
    })
      .then(() => setDirty(false))
      .catch(() => {});
  };

  const categories = Array.from(new Set(permissions.map((p) => p.category)));
  const filtered = filter === "all" ? permissions : permissions.filter((p) => p.category === filter);

  return (
    <div className="flex flex-col h-full rounded-lg border border-border-subtle bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-subtle bg-surface-raised flex items-center justify-between">
        <span className="text-xs text-text-muted font-mono uppercase tracking-wider">Tool Permissions</span>
        {dirty && (
          <button
            onClick={handleSave}
            className="px-2 py-0.5 text-[10px] font-mono font-bold bg-accent text-[var(--color-surface-base)] hover:bg-accent-hover transition-colors"
          >
            Save
          </button>
        )}
      </div>

      {/* Filter bar */}
      <div className="px-3 py-1.5 border-b border-border-subtle flex items-center gap-1 overflow-x-auto">
        <button
          onClick={() => setFilter("all")}
          className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors shrink-0 ${
            filter === "all" ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary"
          }`}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors shrink-0 ${
              filter === cat ? "bg-accent/20 text-accent" : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Permissions list */}
      <div className="flex-1 overflow-y-auto min-h-0 p-2 space-y-1">
        {filtered.map((perm) => (
          <div
            key={perm.tool}
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-surface-raised/50 transition-colors"
          >
            {/* Category badge */}
            <span className={`text-[9px] font-mono px-1 py-0.5 rounded border shrink-0 ${
              CATEGORY_COLORS[perm.category] || "text-text-muted border-border-subtle"
            }`}>
              {perm.category}
            </span>

            {/* Tool name + description */}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-mono text-text-primary">{perm.tool}</div>
              <div className="text-[10px] text-text-muted truncate">{perm.description}</div>
            </div>

            {/* Permission toggle */}
            <div className="flex rounded-md border border-border-subtle overflow-hidden shrink-0">
              {(["allow", "ask", "deny"] as const).map((level) => (
                <button
                  key={level}
                  onClick={() => handlePermissionChange(perm.tool, level)}
                  className={`px-1.5 py-0.5 text-[9px] font-mono font-medium transition-colors ${
                    perm.permission === level
                      ? PERMISSION_STYLES[level].cls
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {PERMISSION_STYLES[level].label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Footer stats */}
      <div className="px-3 py-1.5 border-t border-border-subtle bg-surface-raised flex items-center gap-3 text-[10px] font-mono text-text-muted">
        <span className="text-success">{permissions.filter((p) => p.permission === "allow").length} allowed</span>
        <span className="text-warning">{permissions.filter((p) => p.permission === "ask").length} ask</span>
        <span className="text-error">{permissions.filter((p) => p.permission === "deny").length} denied</span>
      </div>
    </div>
  );
}

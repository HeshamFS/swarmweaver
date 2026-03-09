"use client";

import { useState, useEffect, useCallback, useRef } from "react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface MCPServer {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
  transport: string;
  timeout: number;
  description: string;
  scope: string; // "builtin" | "global" | "project"
  builtin: boolean;
}

interface MCPServerListResponse {
  servers: MCPServer[];
  total: number;
  enabled: number;
}

interface TestResult {
  success: boolean;
  message: string;
  duration_ms: number;
}

interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

interface EnvRow {
  key: string;
  value: string;
}

interface ServerFormState {
  name: string;
  command: string;
  args: string;
  description: string;
  timeout: number;
  scope: "project" | "global";
  envRows: EnvRow[];
}

interface MCPModalProps {
  projectDir: string;
  onClose: () => void;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SCOPE_BADGE_CLASSES: Record<string, string> = {
  builtin: "text-[#bc8cff] bg-[#bc8cff]/10 border border-[#bc8cff]/30",
  global: "text-[#4FC3F7] bg-[#4FC3F7]/10 border border-[#4FC3F7]/30",
  project: "text-[var(--color-accent)] bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/30",
};

const EMPTY_FORM: ServerFormState = {
  name: "",
  command: "",
  args: "",
  description: "",
  timeout: 60,
  scope: "project",
  envRows: [{ key: "", value: "" }],
};

const QUICK_ADD_SUGGESTIONS = [
  {
    label: "Filesystem Server",
    desc: "Read and write files with path-aware context",
    cmd: "npx @modelcontextprotocol/server-filesystem",
  },
  {
    label: "PostgreSQL Server",
    desc: "Query and inspect PostgreSQL databases",
    cmd: "npx @modelcontextprotocol/server-postgres",
  },
  {
    label: "GitHub Server",
    desc: "Interact with GitHub repositories, issues, and PRs",
    cmd: "npx @modelcontextprotocol/server-github",
  },
  {
    label: "Brave Search Server",
    desc: "Web search via Brave Search API",
    cmd: "npx @modelcontextprotocol/server-brave-search",
  },
];

/* ------------------------------------------------------------------ */
/*  JSON Editor Modal                                                   */
/* ------------------------------------------------------------------ */

interface JsonEditorModalProps {
  projectDir: string;
  onClose: () => void;
  onSaved: () => void;
}

function JsonEditorModal({ projectDir, onClose, onSaved }: JsonEditorModalProps) {
  const [scope, setScope] = useState<"project" | "global">("project");
  const [content, setContent] = useState("[]");
  const [filePath, setFilePath] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<{ status: string; entries?: number; error?: string; warnings?: string[] } | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const saveRef = useRef<() => void>(() => {});

  const fetchConfig = useCallback(async (s: "project" | "global") => {
    setLoading(true);
    setError(null);
    setSaveResult(null);
    try {
      const params = new URLSearchParams({ path: projectDir, scope: s });
      const res = await fetch(`/api/mcp/config?${params}`);
      if (!res.ok) {
        // Backend might not have the endpoint yet — show empty editor
        const scopeLabel = s === "global" ? "~/.swarmweaver" : ".swarmweaver";
        setFilePath(`${scopeLabel}/mcp_servers.json`);
        setContent("[]");
        setError(`Could not load config (HTTP ${res.status}). You can still edit and save.`);
        return;
      }
      const data = await res.json();
      setFilePath(data.path || "");
      // Pretty-format for editing
      try {
        const parsed = JSON.parse(data.content || "[]");
        setContent(JSON.stringify(parsed, null, 2));
      } catch {
        setContent(data.content || "[]");
      }
    } catch (err) {
      setFilePath("");
      setContent("[]");
      setError(err instanceof Error ? err.message : "Failed to load config. You can still edit and save.");
    } finally {
      setLoading(false);
    }
  }, [projectDir]);

  useEffect(() => {
    fetchConfig(scope);
  }, [scope, fetchConfig]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveResult(null);
    setError(null);
    try {
      const params = new URLSearchParams({ path: projectDir, scope });
      const res = await fetch(`/api/mcp/config?${params}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
      const data = await res.json();
      if (data.status === "ok") {
        setSaveResult(data);
        onSaved();
      } else {
        setError(data.error || "Save failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [content, projectDir, scope, onSaved]);

  // Keep a ref to the latest handleSave for keyboard shortcut
  saveRef.current = handleSave;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        saveRef.current();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Check if content is valid JSON
  let jsonValid = true;
  try {
    JSON.parse(content);
  } catch {
    jsonValid = false;
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-[70]" onClick={onClose} />
      <div className="fixed inset-0 flex items-center justify-center z-[70] pointer-events-none">
        <div
          className="w-[640px] max-h-[80vh] bg-[#0C0C0C] border border-[#333] flex flex-col shadow-2xl pointer-events-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-bold text-[#888] uppercase tracking-wider font-mono">
                Edit Config File
              </span>
              {/* Scope toggle */}
              <div className="flex border border-[#333] overflow-hidden">
                <button
                  type="button"
                  onClick={() => setScope("project")}
                  className={`px-2 py-0.5 text-[10px] font-mono transition-colors ${
                    scope === "project"
                      ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                      : "text-[#555] hover:text-[#888]"
                  }`}
                >
                  Project
                </button>
                <button
                  type="button"
                  onClick={() => setScope("global")}
                  className={`px-2 py-0.5 text-[10px] font-mono transition-colors ${
                    scope === "global"
                      ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                      : "text-[#555] hover:text-[#888]"
                  }`}
                >
                  Global
                </button>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-[#555] hover:text-[#E0E0E0] transition-colors p-1"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* File path display */}
          <div className="px-4 py-2 border-b border-[#333]/50 bg-[#111]">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-[#555] font-mono shrink-0">File:</span>
              <code className="text-[10px] text-[#888] font-mono truncate" title={filePath}>
                {filePath}
              </code>
            </div>
          </div>

          {/* Editor body */}
          <div className="flex-1 overflow-hidden flex flex-col min-h-0">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <span className="text-[11px] text-[#555] font-mono animate-pulse">Loading...</span>
              </div>
            ) : (
              <textarea
                ref={textareaRef}
                value={content}
                onChange={(e) => {
                  setContent(e.target.value);
                  setSaveResult(null);
                  setError(null);
                }}
                spellCheck={false}
                className="flex-1 w-full bg-[#111] text-[#E0E0E0] text-[11px] font-mono px-4 py-3 resize-none focus:outline-none border-none min-h-[300px] tui-scrollbar leading-relaxed"
                placeholder={'[\n  {\n    "name": "my-server",\n    "command": "npx",\n    "args": ["@modelcontextprotocol/server-name"],\n    "env": {},\n    "enabled": true,\n    "description": "My MCP server"\n  }\n]\n\nAlso accepts Claude Desktop format:\n{\n  "mcpServers": {\n    "server-name": { "command": "...", "args": [...], "env": {...} }\n  }\n}'}
              />
            )}
          </div>

          {/* Status bar */}
          {(error || saveResult) && (
            <div className={`px-4 py-1.5 border-t border-[#333]/50 text-[10px] font-mono space-y-0.5 ${
              error ? "text-[var(--color-error)] bg-[var(--color-error)]/5" : "text-[var(--color-success)] bg-[var(--color-success)]/5"
            }`}>
              <div>{error || (saveResult && `Saved ${saveResult.entries} server(s) to disk`)}</div>
              {saveResult?.warnings?.map((w, i) => (
                <div key={i} className="text-[#FFB300]">{w}</div>
              ))}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between px-4 py-3 border-t border-[#333]">
            <div className="flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${jsonValid ? "bg-[var(--color-success)]" : "bg-[var(--color-error)]"}`} />
              <span className={`text-[10px] font-mono ${jsonValid ? "text-[#555]" : "text-[var(--color-error)]"}`}>
                {jsonValid ? "Valid JSON" : "Invalid JSON"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[9px] text-[#444] font-mono">Ctrl+S to save</span>
              <button
                onClick={handleSave}
                disabled={saving || !jsonValid}
                className="bg-[var(--color-accent)] px-3 py-1 text-[11px] font-medium font-mono text-[#0C0C0C] hover:opacity-90 transition-opacity disabled:opacity-40"
              >
                {saving ? "Saving..." : "Save to Disk"}
              </button>
              <button
                onClick={onClose}
                className="text-[10px] font-mono text-[#555] hover:text-[#E0E0E0] transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Add / Edit Server Modal (nested, smaller)                          */
/* ------------------------------------------------------------------ */

interface AddServerModalProps {
  mode: "add" | "edit";
  editingName: string | null;
  form: ServerFormState;
  saving: boolean;
  formError: string | null;
  validation: ValidationResult | null;
  validating: boolean;
  onUpdateForm: (partial: Partial<ServerFormState>) => void;
  onAddEnvRow: () => void;
  onRemoveEnvRow: (idx: number) => void;
  onUpdateEnvRow: (idx: number, field: "key" | "value", val: string) => void;
  onSave: () => void;
  onValidate: () => void;
  onClose: () => void;
}

function AddServerModal({
  mode,
  editingName,
  form,
  saving,
  formError,
  validation,
  validating,
  onUpdateForm,
  onAddEnvRow,
  onRemoveEnvRow,
  onUpdateEnvRow,
  onSave,
  onValidate,
  onClose,
}: AddServerModalProps) {
  /* Escape key closes this modal */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const inputClass =
    "w-full bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] transition-colors";

  return (
    <>
      {/* Backdrop for nested modal */}
      <div
        className="fixed inset-0 bg-black/40 z-[70]"
        onClick={onClose}
      />
      {/* Modal */}
      <div className="fixed inset-0 flex items-center justify-center z-[70] pointer-events-none">
        <div
          className="w-[480px] max-h-[70vh] bg-[#0C0C0C] border border-[#333] flex flex-col shadow-2xl pointer-events-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
            <span className="text-[11px] font-bold text-[#888] uppercase tracking-wider font-mono">
              {mode === "add" ? "Add Server" : `Edit: ${editingName}`}
            </span>
            <button
              onClick={onClose}
              className="text-[#555] hover:text-[#E0E0E0] transition-colors p-1"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Form body */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 tui-scrollbar">
            {/* Name */}
            <label className="block">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Name</span>
              <input
                type="text"
                value={form.name}
                onChange={(e) => onUpdateForm({ name: e.target.value })}
                readOnly={mode === "edit"}
                placeholder="my-server"
                className={`${inputClass} ${mode === "edit" ? "opacity-60 cursor-not-allowed" : ""}`}
              />
            </label>

            {/* Command */}
            <label className="block">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Command</span>
              <input
                type="text"
                value={form.command}
                onChange={(e) => onUpdateForm({ command: e.target.value })}
                placeholder="npx @modelcontextprotocol/server-name"
                className={inputClass}
              />
            </label>

            {/* Args */}
            <label className="block">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">
                Arguments (space-separated)
              </span>
              <input
                type="text"
                value={form.args}
                onChange={(e) => onUpdateForm({ args: e.target.value })}
                placeholder="--port 3000 --verbose"
                className={inputClass}
              />
            </label>

            {/* Description */}
            <label className="block">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Description</span>
              <input
                type="text"
                value={form.description}
                onChange={(e) => onUpdateForm({ description: e.target.value })}
                placeholder="What this server provides"
                className={inputClass}
              />
            </label>

            {/* Timeout + Scope row */}
            <div className="flex gap-3 items-end">
              <label className="block w-24">
                <span className="text-[10px] text-[#555] mb-1 block font-mono">Timeout (s)</span>
                <input
                  type="number"
                  value={form.timeout}
                  onChange={(e) => onUpdateForm({ timeout: parseInt(e.target.value) || 60 })}
                  min={1}
                  className={inputClass}
                />
              </label>
              {mode === "add" && (
                <div className="flex-1">
                  <span className="text-[10px] text-[#555] mb-1 block font-mono">Scope</span>
                  <div className="flex border border-[#333] overflow-hidden">
                    <button
                      type="button"
                      onClick={() => onUpdateForm({ scope: "project" })}
                      className={`flex-1 px-2 py-1.5 text-[10px] font-mono transition-colors ${
                        form.scope === "project"
                          ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                          : "text-[#555] hover:text-[#888]"
                      }`}
                    >
                      Project
                    </button>
                    <button
                      type="button"
                      onClick={() => onUpdateForm({ scope: "global" })}
                      className={`flex-1 px-2 py-1.5 text-[10px] font-mono transition-colors ${
                        form.scope === "global"
                          ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                          : "text-[#555] hover:text-[#888]"
                      }`}
                    >
                      Global
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Environment Variables */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-[#555] font-mono">
                  Environment Variables
                </span>
                <button
                  type="button"
                  onClick={onAddEnvRow}
                  className="text-[10px] text-[var(--color-accent)] hover:text-[#E0E0E0] transition-colors font-mono"
                >
                  + Add
                </button>
              </div>
              <div className="space-y-1">
                {form.envRows.map((row, idx) => (
                  <div key={idx} className="flex gap-1.5 items-center">
                    <input
                      type="text"
                      value={row.key}
                      onChange={(e) => onUpdateEnvRow(idx, "key", e.target.value)}
                      placeholder="KEY"
                      className="flex-1 bg-[#1A1A1A] text-[#E0E0E0] text-[10px] font-mono px-2 py-1 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                    />
                    <span className="text-[10px] text-[#555]">=</span>
                    <input
                      type="text"
                      value={row.value}
                      onChange={(e) => onUpdateEnvRow(idx, "value", e.target.value)}
                      placeholder="value"
                      className="flex-1 bg-[#1A1A1A] text-[#E0E0E0] text-[10px] font-mono px-2 py-1 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                    />
                    {form.envRows.length > 1 && (
                      <button
                        type="button"
                        onClick={() => onRemoveEnvRow(idx)}
                        className="text-[#555] hover:text-[var(--color-error)] text-xs transition-colors shrink-0 px-0.5"
                      >
                        {"\u2715"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Validation result */}
            {validation && (
              <div
                className={`border p-2 text-[10px] font-mono space-y-0.5 ${
                  validation.valid
                    ? "border-[var(--color-success)]/30 bg-[var(--color-success)]/5 text-[var(--color-success)]"
                    : "border-[var(--color-error)]/30 bg-[var(--color-error)]/5 text-[var(--color-error)]"
                }`}
              >
                {validation.valid && (
                  <div className="text-[var(--color-success)]">Configuration is valid.</div>
                )}
                {validation.errors.map((e, i) => (
                  <div key={`e-${i}`} className="text-[var(--color-error)]">
                    Error: {e}
                  </div>
                ))}
                {validation.warnings.map((w, i) => (
                  <div key={`w-${i}`} className="text-[#FFB300]">
                    Warning: {w}
                  </div>
                ))}
              </div>
            )}

            {/* Form error */}
            {formError && (
              <div className="text-[10px] font-mono text-[var(--color-error)] bg-[var(--color-error)]/5 border border-[var(--color-error)]/30 px-2 py-1">
                {formError}
              </div>
            )}
          </div>

          {/* Footer buttons */}
          <div className="flex items-center gap-2 px-4 py-3 border-t border-[#333]">
            <button
              onClick={onSave}
              disabled={saving || !form.name.trim() || !form.command.trim()}
              className="bg-[var(--color-accent)] px-3 py-1 text-[11px] font-medium font-mono text-[#0C0C0C] hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              {saving ? "Saving..." : mode === "add" ? "Add Server" : "Save Changes"}
            </button>
            <button
              onClick={onValidate}
              disabled={validating || !form.command.trim()}
              className="text-[10px] font-mono border border-[#333] px-2 py-1 text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors disabled:opacity-40"
            >
              {validating ? "Validating..." : "Validate"}
            </button>
            <button
              onClick={onClose}
              className="text-[10px] font-mono text-[#555] hover:text-[#E0E0E0] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Server Row Component                                               */
/* ------------------------------------------------------------------ */

interface ServerRowProps {
  server: MCPServer;
  isTesting: boolean;
  testResult: TestResult | null;
  isConfirmingDelete: boolean;
  onToggle: () => void;
  onTest: () => void;
  onEdit: () => void;
  onDeleteRequest: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;
}

function ServerRow({
  server,
  isTesting,
  testResult,
  isConfirmingDelete,
  onToggle,
  onTest,
  onEdit,
  onDeleteRequest,
  onDeleteConfirm,
  onDeleteCancel,
}: ServerRowProps) {
  const commandDisplay =
    server.command.length > 60
      ? server.command.slice(0, 57) + "..."
      : server.command;

  const argsDisplay = server.args.length > 0 ? server.args.join(" ") : null;
  const argsShort =
    argsDisplay && argsDisplay.length > 40
      ? argsDisplay.slice(0, 37) + "..."
      : argsDisplay;

  return (
    <div
      className={`px-4 py-3 hover:bg-[#1A1A1A]/50 transition-colors ${
        !server.enabled ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            {/* Enabled dot */}
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                server.enabled ? "bg-[var(--color-success)]" : "bg-[#555]"
              }`}
              title={server.enabled ? "Enabled" : "Disabled"}
            />
            {/* Name */}
            <span className="text-[11px] font-medium text-[#E0E0E0] font-mono">
              {server.name}
            </span>
            {/* Scope badge */}
            <span
              className={`text-[9px] px-1.5 py-0.5 font-medium font-mono ${
                SCOPE_BADGE_CLASSES[server.scope] || SCOPE_BADGE_CLASSES.project
              }`}
            >
              {server.scope}
            </span>
          </div>

          {/* Description */}
          {server.description && (
            <p className="text-[11px] text-[#B0B0B0] mb-1">{server.description}</p>
          )}

          {/* Command + args */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <code className="text-[10px] text-[#888] font-mono bg-[#1A1A1A] px-1.5 py-0.5 border border-[#333] truncate max-w-[400px]">
              {commandDisplay}
            </code>
            {argsShort && (
              <code
                className="text-[10px] text-[#555] font-mono truncate max-w-[250px]"
                title={argsDisplay || ""}
              >
                {argsShort}
              </code>
            )}
          </div>

          {/* Test result */}
          {testResult && (
            <div
              className={`mt-1.5 text-[10px] font-mono flex items-center gap-1.5 ${
                testResult.success ? "text-[var(--color-success)]" : "text-[var(--color-error)]"
              }`}
            >
              <span>{testResult.success ? "\u2713" : "\u2717"}</span>
              <span>{testResult.message}</span>
              {testResult.duration_ms > 0 && (
                <span className="text-[#555]">({testResult.duration_ms}ms)</span>
              )}
            </div>
          )}

          {/* Delete confirmation inline */}
          {isConfirmingDelete && (
            <div className="mt-2 flex items-center gap-2 bg-[var(--color-error)]/5 border border-[var(--color-error)]/20 px-2 py-1.5">
              <span className="text-[10px] font-mono text-[var(--color-error)]">Remove this server?</span>
              <button
                onClick={onDeleteConfirm}
                className="text-[10px] font-mono font-bold text-[var(--color-error)] border border-[var(--color-error)]/40 px-2 py-0.5 hover:bg-[var(--color-error)]/10 transition-colors"
              >
                Remove
              </button>
              <button
                onClick={onDeleteCancel}
                className="text-[10px] font-mono text-[#555] hover:text-[#E0E0E0] transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Toggle switch */}
          <button
            onClick={onToggle}
            title={server.enabled ? "Disable" : "Enable"}
            className={`relative inline-flex items-center w-9 h-5 rounded-full transition-colors shrink-0 ${
              server.enabled ? "bg-[var(--color-accent)]" : "bg-[#333]"
            }`}
          >
            <span
              className={`inline-block w-3.5 h-3.5 rounded-full bg-white shadow transition-transform ${
                server.enabled ? "translate-x-[18px]" : "translate-x-[3px]"
              }`}
            />
          </button>

          {/* Test button */}
          <button
            onClick={onTest}
            disabled={isTesting}
            className="text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] transition-colors px-2 py-1 border border-[#333] hover:border-[#555] disabled:opacity-40"
            title="Test connection"
          >
            {isTesting ? (
              <svg
                className="w-3 h-3 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
            ) : (
              "Test"
            )}
          </button>

          {/* Edit button (non-builtin only) */}
          {!server.builtin && (
            <button
              onClick={onEdit}
              className="text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] transition-colors px-2 py-1 border border-[#333] hover:border-[#555]"
              title="Edit"
            >
              Edit
            </button>
          )}

          {/* Remove button (non-builtin only) */}
          {!server.builtin && (
            <button
              onClick={onDeleteRequest}
              className="text-[10px] font-mono text-[#888] hover:text-[var(--color-error)] transition-colors px-2 py-1 border border-[#333] hover:border-[var(--color-error)]/50"
              title="Remove"
            >
              {"\u2715"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MCP Modal (large, main)                                            */
/* ------------------------------------------------------------------ */

export function MCPModal({ projectDir, onClose }: MCPModalProps) {
  /* ---- Server list state ---- */
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [total, setTotal] = useState(0);
  const [enabledCount, setEnabledCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ---- Test state ---- */
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});

  /* ---- Form state ---- */
  const [formMode, setFormMode] = useState<"closed" | "add" | "edit">("closed");
  const [form, setForm] = useState<ServerFormState>(EMPTY_FORM);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validating, setValidating] = useState(false);

  /* ---- Delete confirmation ---- */
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  /* ---- JSON editor ---- */
  const [jsonEditorOpen, setJsonEditorOpen] = useState(false);

  const fetchedRef = useRef(false);

  /* ---------------------------------------------------------------- */
  /*  Data fetching — triggered when modal opens                       */
  /* ---------------------------------------------------------------- */

  const fetchServers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ path: projectDir });
      const res = await fetch(`/api/mcp/servers?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: MCPServerListResponse = await res.json();
      setServers(data.servers || []);
      setTotal(data.total ?? 0);
      setEnabledCount(data.enabled ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MCP servers");
    } finally {
      setLoading(false);
    }
  }, [projectDir]);

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true;
      fetchServers();
    }
  }, [fetchServers]);

  /* Escape key closes modal (only if nested modal is not open) */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && formMode === "closed" && !jsonEditorOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose, formMode, jsonEditorOpen]);

  /* ---------------------------------------------------------------- */
  /*  Toggle enable / disable                                          */
  /* ---------------------------------------------------------------- */

  const toggleServer = useCallback(
    async (name: string, currentlyEnabled: boolean) => {
      const action = currentlyEnabled ? "disable" : "enable";
      const params = new URLSearchParams({ path: projectDir });
      try {
        const res = await fetch(
          `/api/mcp/servers/${encodeURIComponent(name)}/${action}?${params}`,
          { method: "POST" }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setServers((prev) =>
          prev.map((s) =>
            s.name === name ? { ...s, enabled: !currentlyEnabled } : s
          )
        );
        setEnabledCount((c) => (currentlyEnabled ? c - 1 : c + 1));
      } catch {
        // Silently fail — user can retry
      }
    },
    [projectDir]
  );

  /* ---------------------------------------------------------------- */
  /*  Test connection                                                  */
  /* ---------------------------------------------------------------- */

  const testServer = useCallback(
    async (name: string) => {
      setTesting((prev) => ({ ...prev, [name]: true }));
      setTestResults((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      try {
        const params = new URLSearchParams({ path: projectDir });
        const res = await fetch(
          `/api/mcp/servers/${encodeURIComponent(name)}/test?${params}`,
          { method: "POST" }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: TestResult = await res.json();
        setTestResults((prev) => ({ ...prev, [name]: data }));
      } catch {
        setTestResults((prev) => ({
          ...prev,
          [name]: { success: false, message: "Request failed", duration_ms: 0 },
        }));
      } finally {
        setTesting((prev) => ({ ...prev, [name]: false }));
      }
    },
    [projectDir]
  );

  /* ---------------------------------------------------------------- */
  /*  Delete server                                                    */
  /* ---------------------------------------------------------------- */

  const deleteServer = useCallback(
    async (name: string) => {
      const params = new URLSearchParams({ path: projectDir, scope: "project" });
      try {
        const res = await fetch(
          `/api/mcp/servers/${encodeURIComponent(name)}?${params}`,
          { method: "DELETE" }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setServers((prev) => prev.filter((s) => s.name !== name));
        setTotal((t) => t - 1);
        const removed = servers.find((s) => s.name === name);
        if (removed?.enabled) setEnabledCount((c) => c - 1);
      } catch {
        // Silently fail
      } finally {
        setConfirmDelete(null);
      }
    },
    [projectDir, servers]
  );

  /* ---------------------------------------------------------------- */
  /*  Validate config                                                  */
  /* ---------------------------------------------------------------- */

  const validateConfig = useCallback(async () => {
    setValidating(true);
    setValidation(null);
    try {
      const envObj: Record<string, string> = {};
      for (const row of form.envRows) {
        if (row.key.trim()) envObj[row.key.trim()] = row.value;
      }
      const body = {
        name: form.name.trim(),
        command: form.command.trim(),
        args: form.args.trim() ? form.args.trim().split(/\s+/) : [],
        description: form.description.trim(),
        timeout: form.timeout,
        env: envObj,
      };
      const res = await fetch("/api/mcp/servers/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ValidationResult = await res.json();
      setValidation(data);
    } catch {
      setValidation({ valid: false, errors: ["Validation request failed"], warnings: [] });
    } finally {
      setValidating(false);
    }
  }, [form]);

  /* ---------------------------------------------------------------- */
  /*  Save (add / update)                                              */
  /* ---------------------------------------------------------------- */

  const saveServer = useCallback(async () => {
    if (!form.name.trim() || !form.command.trim()) {
      setFormError("Name and command are required.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      const envObj: Record<string, string> = {};
      for (const row of form.envRows) {
        if (row.key.trim()) envObj[row.key.trim()] = row.value;
      }
      const body = {
        name: form.name.trim(),
        command: form.command.trim(),
        args: form.args.trim() ? form.args.trim().split(/\s+/) : [],
        description: form.description.trim(),
        timeout: form.timeout,
        env: envObj,
        enabled: true,
      };

      const params = new URLSearchParams({ path: projectDir });
      if (formMode === "add") {
        params.set("scope", form.scope);
      }

      const url =
        formMode === "edit" && editingName
          ? `/api/mcp/servers/${encodeURIComponent(editingName)}?${params}`
          : `/api/mcp/servers?${params}`;

      const method = formMode === "edit" ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `HTTP ${res.status}`);
      }

      closeForm();
      fetchServers();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [form, formMode, editingName, projectDir, fetchServers]);

  /* ---------------------------------------------------------------- */
  /*  Form helpers                                                     */
  /* ---------------------------------------------------------------- */

  const openAddForm = useCallback(() => {
    setForm(EMPTY_FORM);
    setEditingName(null);
    setFormError(null);
    setValidation(null);
    setFormMode("add");
  }, []);

  const openAddFormWithSuggestion = useCallback(
    (suggestion: { label: string; desc: string; cmd: string }) => {
      setForm({
        ...EMPTY_FORM,
        name: suggestion.cmd.split("/").pop()?.replace("server-", "") || "",
        command: suggestion.cmd.split(" ")[0],
        args: suggestion.cmd.split(" ").slice(1).join(" "),
        description: suggestion.desc,
      });
      setEditingName(null);
      setFormError(null);
      setValidation(null);
      setFormMode("add");
    },
    []
  );

  const openEditForm = useCallback((server: MCPServer) => {
    const envRows: EnvRow[] = Object.entries(server.env || {}).map(([key, value]) => ({
      key,
      value,
    }));
    if (envRows.length === 0) envRows.push({ key: "", value: "" });
    setForm({
      name: server.name,
      command: server.command,
      args: (server.args || []).join(" "),
      description: server.description || "",
      timeout: server.timeout || 60,
      scope: (server.scope === "global" ? "global" : "project") as "project" | "global",
      envRows,
    });
    setEditingName(server.name);
    setFormError(null);
    setValidation(null);
    setFormMode("edit");
  }, []);

  const closeForm = useCallback(() => {
    setFormMode("closed");
    setForm(EMPTY_FORM);
    setEditingName(null);
    setFormError(null);
    setValidation(null);
  }, []);

  const updateForm = useCallback(
    (partial: Partial<ServerFormState>) => {
      setForm((prev) => ({ ...prev, ...partial }));
      setFormError(null);
    },
    []
  );

  const addEnvRow = useCallback(() => {
    setForm((prev) => ({
      ...prev,
      envRows: [...prev.envRows, { key: "", value: "" }],
    }));
  }, []);

  const removeEnvRow = useCallback((idx: number) => {
    setForm((prev) => ({
      ...prev,
      envRows: prev.envRows.filter((_, i) => i !== idx),
    }));
  }, []);

  const updateEnvRow = useCallback((idx: number, field: "key" | "value", val: string) => {
    setForm((prev) => ({
      ...prev,
      envRows: prev.envRows.map((row, i) =>
        i === idx ? { ...row, [field]: val } : row
      ),
    }));
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-[60]"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 flex items-center justify-center z-[60] pointer-events-none">
        <div
          className="w-[700px] max-h-[80vh] bg-[#0C0C0C] border border-[#333] flex flex-col shadow-2xl pointer-events-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <svg
                  className="w-3.5 h-3.5 text-[#555]"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
                  <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
                  <line x1="6" y1="6" x2="6.01" y2="6" />
                  <line x1="6" y1="18" x2="6.01" y2="18" />
                </svg>
                <span className="text-[11px] font-bold text-[#888] uppercase tracking-wider font-mono">
                  MCP Servers
                </span>
              </div>
              <span className="text-[10px] text-[#555] font-mono px-1.5 py-0.5 border border-[#333]">
                {total} servers, {enabledCount} enabled
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchServers}
                className="text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] transition-colors px-1.5 py-0.5 border border-[#333] hover:border-[#555]"
                title="Refresh"
              >
                <svg
                  className="w-3 h-3"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="23 4 23 10 17 10" />
                  <polyline points="1 20 1 14 7 14" />
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
                </svg>
              </button>
              <button
                onClick={() => setJsonEditorOpen(true)}
                className="text-[10px] font-mono border border-[#333] px-2 py-0.5 text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors"
                title="Edit mcp_servers.json directly"
              >
                Edit JSON
              </button>
              <button
                onClick={openAddForm}
                className="text-[10px] font-mono border border-[var(--color-accent)]/50 px-2 py-0.5 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 transition-colors"
              >
                + Add Server
              </button>
              <button
                onClick={onClose}
                className="text-[#555] hover:text-[#E0E0E0] transition-colors p-1"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Body: server list */}
          <div className="flex-1 overflow-y-auto min-h-0 tui-scrollbar">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <span className="text-[11px] text-[#555] font-mono animate-pulse">Loading...</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-48 gap-2 p-4">
                <span className="text-[11px] text-[var(--color-error)] font-mono">{error}</span>
                <button
                  onClick={fetchServers}
                  className="text-[10px] font-mono text-[var(--color-accent)] hover:text-[#E0E0E0] transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : servers.length === 0 ? (
              /* Empty state with quick-add suggestions */
              <div className="p-6 space-y-5">
                <div className="text-center py-6">
                  <svg
                    className="w-10 h-10 text-[#333] mx-auto mb-3"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
                    <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
                    <line x1="6" y1="6" x2="6.01" y2="6" />
                    <line x1="6" y1="18" x2="6.01" y2="18" />
                  </svg>
                  <p className="text-[11px] text-[#888] mb-1 font-mono">No MCP servers configured</p>
                  <p className="text-[10px] text-[#555] font-mono">
                    Add servers to extend agent capabilities with tools, data, and integrations.
                  </p>
                </div>
                <div className="space-y-2">
                  <span className="text-[10px] font-bold text-[#555] uppercase tracking-wider font-mono">
                    Quick Add Suggestions
                  </span>
                  <div className="grid grid-cols-2 gap-2">
                    {QUICK_ADD_SUGGESTIONS.map((suggestion) => (
                      <button
                        key={suggestion.label}
                        onClick={() => openAddFormWithSuggestion(suggestion)}
                        className="text-left bg-[#1A1A1A] border border-[#333] px-3 py-2.5 hover:border-[var(--color-accent)]/50 transition-colors group"
                      >
                        <div className="text-[11px] text-[#E0E0E0] group-hover:text-[var(--color-accent)] transition-colors font-mono">
                          {suggestion.label}
                        </div>
                        <div className="text-[10px] text-[#555] font-mono mt-0.5 truncate">
                          {suggestion.cmd}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              /* Server list */
              <div className="divide-y divide-[#333]/50">
                {servers.map((server) => (
                  <ServerRow
                    key={server.name}
                    server={server}
                    isTesting={testing[server.name] || false}
                    testResult={testResults[server.name] || null}
                    isConfirmingDelete={confirmDelete === server.name}
                    onToggle={() => toggleServer(server.name, server.enabled)}
                    onTest={() => testServer(server.name)}
                    onEdit={() => openEditForm(server)}
                    onDeleteRequest={() => setConfirmDelete(server.name)}
                    onDeleteConfirm={() => deleteServer(server.name)}
                    onDeleteCancel={() => setConfirmDelete(null)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Nested Add/Edit Server Modal */}
      {formMode !== "closed" && (
        <AddServerModal
          mode={formMode}
          editingName={editingName}
          form={form}
          saving={saving}
          formError={formError}
          validation={validation}
          validating={validating}
          onUpdateForm={updateForm}
          onAddEnvRow={addEnvRow}
          onRemoveEnvRow={removeEnvRow}
          onUpdateEnvRow={updateEnvRow}
          onSave={saveServer}
          onValidate={validateConfig}
          onClose={closeForm}
        />
      )}

      {/* JSON Editor Modal */}
      {jsonEditorOpen && (
        <JsonEditorModal
          projectDir={projectDir}
          onClose={() => setJsonEditorOpen(false)}
          onSaved={() => {
            fetchedRef.current = false;
            fetchServers();
          }}
        />
      )}
    </>
  );
}

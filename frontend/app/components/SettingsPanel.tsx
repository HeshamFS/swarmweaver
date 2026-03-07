"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { GlobalSettings, ThemeId } from "../hooks/useGlobalSettings";
import { MODELS, PRESETS } from "../utils/constants";
import { FolderPicker } from "./FolderPicker";
import { Check, XCircle } from "lucide-react";

const THEMES: { id: ThemeId; label: string; color: string }[] = [
  { id: "ember", label: "Ember", color: "#FF5722" },
  { id: "cyan", label: "Cyan", color: "#00E5FF" },
  { id: "verdant", label: "Verdant", color: "#00FF87" },
  { id: "rose", label: "Rose", color: "#FF2D55" },
  { id: "amber", label: "Amber", color: "#FFB300" },
  { id: "violet", label: "Violet", color: "#8B5CF6" },
  { id: "lime", label: "Lime", color: "#84CC16" },
  { id: "teal", label: "Teal", color: "#14B8A6" },
  { id: "fuchsia", label: "Fuchsia", color: "#D946EF" },
  { id: "indigo", label: "Indigo", color: "#6366F1" },
  { id: "copper", label: "Copper", color: "#B45309" },
];

interface ApiKeyStatus {
  configured: boolean;
  masked: string;
}

interface ApiKeysState {
  anthropic_api_key: ApiKeyStatus;
  claude_code_oauth_token: ApiKeyStatus;
  loading: boolean;
  saving: boolean;
  testing: boolean;
  testResult: "success" | "error" | null;
}

interface GitHubStatus {
  installed: boolean;
  authenticated: boolean;
  username: string | null;
  loading: boolean;
}

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  settings: GlobalSettings;
  onUpdate: (partial: Partial<GlobalSettings>) => void;
  syncing: boolean;
  onSync: () => void;
}

export function SettingsPanel({ open, onClose, settings, onUpdate, syncing, onSync }: SettingsPanelProps) {
  const [gh, setGh] = useState<GitHubStatus>({ installed: false, authenticated: false, username: null, loading: false });

  /* API Keys state */
  const [apiKeys, setApiKeys] = useState<ApiKeysState>({
    anthropic_api_key: { configured: false, masked: "" },
    claude_code_oauth_token: { configured: false, masked: "" },
    loading: false,
    saving: false,
    testing: false,
    testResult: null,
  });
  const [editAnthropicKey, setEditAnthropicKey] = useState("");
  const [editOAuthToken, setEditOAuthToken] = useState("");
  const [showKeyInputs, setShowKeyInputs] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const themeRef = useRef<HTMLDivElement>(null);

  /* Close theme dropdown on click outside */
  useEffect(() => {
    if (!themeOpen) return;
    const handle = (e: MouseEvent) => {
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeOpen(false);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [themeOpen]);

  /* Fetch API keys and GitHub status when panel opens */
  useEffect(() => {
    if (!open) return;

    setGh((prev) => ({ ...prev, loading: true }));
    fetch("/api/github/connection")
      .then((r) => r.json())
      .then((data) => {
        setGh({
          installed: data.installed ?? false,
          authenticated: data.authenticated ?? false,
          username: data.username ?? null,
          loading: false,
        });
      })
      .catch(() => {
        setGh({ installed: false, authenticated: false, username: null, loading: false });
      });

    setApiKeys((prev) => ({ ...prev, loading: true }));
    fetch("/api/settings/api-keys")
      .then((r) => r.json())
      .then((data) => {
        setApiKeys((prev) => ({
          ...prev,
          anthropic_api_key: data.anthropic_api_key ?? { configured: false, masked: "" },
          claude_code_oauth_token: data.claude_code_oauth_token ?? { configured: false, masked: "" },
          loading: false,
        }));
      })
      .catch(() => {
        setApiKeys((prev) => ({ ...prev, loading: false }));
      });
  }, [open]);

  const applyPreset = useCallback(
    (presetId: string) => {
      const p = PRESETS.find((x) => x.id === presetId);
      if (!p) return;
      onUpdate({
        defaultModel: p.model,
        defaultParallel: p.parallel,
        approvalGates: p.approvalGates,
        phaseModels: { architect: "", plan: "", code: "" },
      });
    },
    [onUpdate]
  );

  const saveApiKeys = useCallback(async () => {
    setApiKeys((prev) => ({ ...prev, saving: true }));
    try {
      const body: Record<string, string | undefined> = {};
      if (editAnthropicKey) body.anthropic_api_key = editAnthropicKey;
      if (editOAuthToken) body.claude_code_oauth_token = editOAuthToken;
      const res = await fetch("/api/settings/api-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.status === "ok") {
        setEditAnthropicKey("");
        setEditOAuthToken("");
        setShowKeyInputs(false);
        // Refresh keys display
        const refresh = await fetch("/api/settings/api-keys");
        const refreshData = await refresh.json();
        setApiKeys((prev) => ({
          ...prev,
          anthropic_api_key: refreshData.anthropic_api_key ?? prev.anthropic_api_key,
          claude_code_oauth_token: refreshData.claude_code_oauth_token ?? prev.claude_code_oauth_token,
          saving: false,
        }));
      } else {
        setApiKeys((prev) => ({ ...prev, saving: false }));
      }
    } catch {
      setApiKeys((prev) => ({ ...prev, saving: false }));
    }
  }, [editAnthropicKey, editOAuthToken]);

  const testConnection = useCallback(async () => {
    setApiKeys((prev) => ({ ...prev, testing: true, testResult: null }));
    try {
      const res = await fetch("/api/doctor");
      const data = await res.json();
      setApiKeys((prev) => ({
        ...prev,
        testing: false,
        testResult: data.auth?.configured ? "success" : "error",
      }));
    } catch {
      setApiKeys((prev) => ({ ...prev, testing: false, testResult: "error" }));
    }
  }, []);

  const selectClass = "bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] w-full";
  const inputClass = "bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] w-20";

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed top-0 left-0 bottom-0 w-80 bg-[#0C0C0C] border-r border-[#333] z-50 flex flex-col overflow-y-auto tui-scrollbar">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#333]">
          <span className="text-[11px] font-bold text-[#888] uppercase tracking-wider font-mono flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-[#555]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" /><circle cx="12" cy="12" r="3" />
            </svg>
            Global Settings
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

        <div className="flex-1 px-4 py-4 space-y-4">
          {/* Theme - dropdown with color swatches */}
          <Section title="Theme">
            <div ref={themeRef} className="relative">
              <button
                type="button"
                onClick={() => setThemeOpen((o) => !o)}
                className="flex items-center justify-between w-full bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] hover:border-[#555] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
              >
                <span className="flex items-center gap-2">
                  <span
                    className="w-4 h-4 rounded-full shrink-0 ring-1 ring-[#333]"
                    style={{ backgroundColor: THEMES.find((t) => t.id === settings.theme)?.color ?? "#FF5722" }}
                  />
                  <span>{THEMES.find((t) => t.id === settings.theme)?.label ?? "Ember"}</span>
                </span>
                <span className="text-[#555] text-[10px]">{"\u25BC"}</span>
              </button>
              {themeOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 border border-[#333] bg-[#121212] shadow-lg z-50 max-h-48 overflow-y-auto tui-scrollbar">
                  {THEMES.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => {
                        onUpdate({ theme: t.id });
                        setThemeOpen(false);
                      }}
                      className={`flex items-center gap-2 w-full px-3 py-2 text-left text-[11px] font-mono transition-colors ${
                        settings.theme === t.id
                          ? "bg-[var(--color-accent)]/10 text-[#E0E0E0] border-l-2 border-l-[var(--color-accent)]"
                          : "text-[#888] hover:bg-[#1A1A1A] hover:text-[#E0E0E0]"
                      }`}
                    >
                      <span
                        className="w-4 h-4 rounded-full shrink-0 ring-1 ring-[#333]"
                        style={{ backgroundColor: t.color }}
                      />
                      {t.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </Section>

          {/* API Keys */}
          <Section title="API Keys">
            {apiKeys.loading ? (
              <div className="text-[11px] text-[#555] font-mono animate-pulse">Loading...</div>
            ) : (
              <div className="space-y-2">
                {/* Status indicators */}
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] ${apiKeys.anthropic_api_key.configured ? "text-[var(--color-success)]" : "text-[#555]"}`}>
                      {apiKeys.anthropic_api_key.configured ? "\u2713" : "\u2022"}
                    </span>
                    <span className="text-[11px] font-mono text-[#888]">ANTHROPIC_API_KEY</span>
                    {apiKeys.anthropic_api_key.configured && (
                      <span className="text-[10px] font-mono text-[#555]">{apiKeys.anthropic_api_key.masked}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] ${apiKeys.claude_code_oauth_token.configured ? "text-[var(--color-success)]" : "text-[#555]"}`}>
                      {apiKeys.claude_code_oauth_token.configured ? "\u2713" : "\u2022"}
                    </span>
                    <span className="text-[11px] font-mono text-[#888]">CLAUDE_CODE_OAUTH_TOKEN</span>
                    {apiKeys.claude_code_oauth_token.configured && (
                      <span className="text-[10px] font-mono text-[#555]">{apiKeys.claude_code_oauth_token.masked}</span>
                    )}
                  </div>
                </div>

                {/* Edit / Test buttons */}
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowKeyInputs((v) => !v)}
                    className="text-[10px] font-mono border border-[#333] px-2 py-1 text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors"
                  >
                    {showKeyInputs ? "Cancel" : "Edit Keys"}
                  </button>
                  <button
                    onClick={testConnection}
                    disabled={apiKeys.testing}
                    className="text-[10px] font-mono border border-[#333] px-2 py-1 text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors disabled:opacity-40"
                  >
                    {apiKeys.testing ? "Testing..." : "Test Connection"}
                  </button>
                  {apiKeys.testResult === "success" && (
                    <span className="text-[10px] font-mono text-[var(--color-success)] self-center">Connected</span>
                  )}
                  {apiKeys.testResult === "error" && (
                    <span className="text-[10px] font-mono text-[var(--color-error)] self-center">Failed</span>
                  )}
                </div>

                {/* Key input fields */}
                {showKeyInputs && (
                  <div className="space-y-2 mt-2 p-2 bg-[#1A1A1A] border border-[#333]">
                    <label className="block">
                      <span className="text-[10px] text-[#555] mb-1 block font-mono">ANTHROPIC_API_KEY</span>
                      <input
                        type="password"
                        value={editAnthropicKey}
                        onChange={(e) => setEditAnthropicKey(e.target.value)}
                        placeholder={apiKeys.anthropic_api_key.configured ? apiKeys.anthropic_api_key.masked : "sk-ant-..."}
                        className={selectClass}
                      />
                    </label>
                    <label className="block">
                      <span className="text-[10px] text-[#555] mb-1 block font-mono">CLAUDE_CODE_OAUTH_TOKEN</span>
                      <input
                        type="password"
                        value={editOAuthToken}
                        onChange={(e) => setEditOAuthToken(e.target.value)}
                        placeholder={apiKeys.claude_code_oauth_token.configured ? apiKeys.claude_code_oauth_token.masked : "Paste token here"}
                        className={selectClass}
                      />
                    </label>
                    <button
                      onClick={saveApiKeys}
                      disabled={apiKeys.saving || (!editAnthropicKey && !editOAuthToken)}
                      className="text-[10px] font-mono border border-[var(--color-accent)]/50 px-3 py-1 text-[var(--color-accent)] hover:bg-[var(--color-accent)]/10 transition-colors disabled:opacity-40"
                    >
                      {apiKeys.saving ? "Saving..." : "Save"}
                    </button>
                  </div>
                )}
              </div>
            )}
          </Section>

          {/* GitHub Connection */}
          <Section title="GitHub Connection">
            {gh.loading ? (
              <div className="text-[11px] text-[#555] font-mono animate-pulse">Checking...</div>
            ) : gh.authenticated ? (
              <div className="flex items-center gap-2">
                <Check className="w-3.5 h-3.5 text-[var(--color-success)] shrink-0" />
                <span className="text-[11px] font-mono text-[#E0E0E0]">
                  Logged in as <span className="text-[var(--color-accent)]">{gh.username || "unknown"}</span>
                </span>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <XCircle className="w-3.5 h-3.5 text-[var(--color-error)] shrink-0" />
                  <span className="text-[11px] font-mono text-[#888]">
                    {gh.installed ? "Not authenticated" : "gh CLI not found"}
                  </span>
                </div>
                <div className="bg-[#1A1A1A] border border-[#333] p-2 text-[10px] font-mono text-[#888]">
                  {!gh.installed ? (
                    <>Install: <span className="text-[#E0E0E0]">brew install gh</span> or <span className="text-[#E0E0E0]">winget install GitHub.cli</span></>
                  ) : (
                    <>Run: <span className="text-[#E0E0E0]">gh auth login</span></>
                  )}
                </div>
              </div>
            )}
            <Checkbox
              checked={settings.autoPr}
              onChange={(v) => onUpdate({ autoPr: v })}
              label="Auto-create PR"
              hint={!gh.authenticated ? "Requires GitHub authentication" : "Open a pull request on completion"}
              disabled={!gh.authenticated}
            />
          </Section>

          {/* Default Models */}
          <Section title="Default Models">
            <label className="block">
              <span className="text-[10px] text-[#555] mb-1 block font-mono">Default model</span>
              <select
                value={settings.defaultModel}
                onChange={(e) => onUpdate({ defaultModel: e.target.value })}
                className={selectClass}
              >
                {MODELS.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </select>
            </label>
            <div className="flex gap-2 mt-2 flex-wrap">
              {(["architect", "plan", "code"] as const).map((stage) => (
                <label key={stage} className="block flex-1 min-w-[70px]">
                  <span className="text-[10px] text-[#555] mb-1 block capitalize font-mono">{stage}</span>
                  <select
                    value={settings.phaseModels[stage]}
                    onChange={(e) =>
                      onUpdate({
                        phaseModels: { ...settings.phaseModels, [stage]: e.target.value },
                      })
                    }
                    className={selectClass}
                  >
                    <option value="">Default</option>
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </Section>

          {/* Default browse path */}
          <Section title="Default Browse Path">
            <div className="flex gap-2 items-end">
              <label className="flex-1 min-w-0">
                <span className="text-[10px] text-[#555] mb-1 block font-mono">Start folder picker at</span>
                <input
                  type="text"
                  value={settings.defaultBrowsePath ?? ""}
                  onChange={(e) => onUpdate({ defaultBrowsePath: e.target.value.trim() || null })}
                  placeholder="/ or leave empty"
                  className="bg-[#1A1A1A] text-[#E0E0E0] text-[11px] font-mono px-2 py-1.5 border border-[#333] focus:outline-none focus:border-[var(--color-accent)] w-full"
                />
              </label>
              <button
                type="button"
                onClick={() => setShowFolderPicker(true)}
                className="border border-[#333] px-2 py-1.5 text-[10px] font-mono text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors shrink-0"
              >
                Browse
              </button>
            </div>
          </Section>

          {/* Run Defaults */}
          <Section title="Run Defaults">
            <div className="flex gap-2 flex-wrap">
              <label className="block flex-1 min-w-[60px]">
                <span className="text-[10px] text-[#555] mb-1 block font-mono">Workers</span>
                <select
                  value={settings.defaultParallel}
                  onChange={(e) => onUpdate({ defaultParallel: Number(e.target.value) })}
                  className={selectClass}
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label className="block flex-1 min-w-[60px]">
                <span className="text-[10px] text-[#555] mb-1 block font-mono">Budget $</span>
                <input
                  type="text"
                  value={settings.budgetLimit ?? ""}
                  onChange={(e) => {
                    const v = e.target.value.replace(/[^0-9.]/g, "");
                    onUpdate({ budgetLimit: v ? parseFloat(v) : null });
                  }}
                  placeholder="--"
                  className={inputClass + " w-full"}
                />
              </label>
              <label className="block flex-1 min-w-[60px]">
                <span className="text-[10px] text-[#555] mb-1 block font-mono">Max h</span>
                <input
                  type="text"
                  value={settings.maxHours ?? ""}
                  onChange={(e) => {
                    const v = e.target.value.replace(/[^0-9.]/g, "");
                    onUpdate({ maxHours: v ? parseFloat(v) : null });
                  }}
                  placeholder="--"
                  className={inputClass + " w-full"}
                />
              </label>
            </div>
          </Section>

          {/* Safety & Workflow */}
          <Section title="Safety & Workflow">
            <div className="space-y-2">
              <Checkbox
                checked={settings.useWorktree}
                onChange={(v) => onUpdate({ useWorktree: v })}
                label="Use worktree"
                hint="Isolate changes in a git branch (recommended)"
              />
              <Checkbox
                checked={settings.approvalGates}
                onChange={(v) => onUpdate({ approvalGates: v })}
                label="Approval gates"
                hint="Pause between iterations for review"
              />
              <Checkbox
                checked={settings.skipQA}
                onChange={(v) => onUpdate({ skipQA: v })}
                label="Skip Q&A setup"
                hint="Launch directly without interactive setup"
              />
            </div>
          </Section>

          {/* Presets - compact single-line segmented control */}
          <Section title="Presets">
            <div className="flex border border-[#333] bg-[#0C0C0C]">
              {PRESETS.map((p) => {
                const isActive =
                  settings.defaultModel === p.model &&
                  settings.defaultParallel === p.parallel &&
                  settings.approvalGates === p.approvalGates;
                return (
                  <button
                    key={p.id}
                    onClick={() => applyPreset(p.id)}
                    className={`flex-1 min-w-0 px-2 py-1 font-mono text-[10px] transition-colors border-r border-[#333] last:border-r-0 ${
                      isActive
                        ? "text-[#0C0C0C] bg-[#888] font-bold"
                        : "text-[#555] hover:text-[#888]"
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
          </Section>
        </div>

        {/* Footer: Sync */}
        <div className="px-4 py-3 border-t border-[#333] flex items-center justify-between">
          <span className="text-[10px] text-[#555] font-mono">
            {syncing ? "Syncing..." : "localStorage"}
          </span>
          <button
            onClick={onSync}
            disabled={syncing}
            className="text-[11px] font-mono border border-[#333] px-3 py-1 text-[#888] hover:text-[#E0E0E0] hover:border-[#555] transition-colors disabled:opacity-40"
          >
            {syncing ? "..." : "Sync to server"}
          </button>
        </div>
      </div>

      {/* Folder picker for default browse path */}
      {showFolderPicker && (
        <FolderPicker
          onSelect={(path) => {
            onUpdate({ defaultBrowsePath: path });
            setShowFolderPicker(false);
          }}
          onClose={() => setShowFolderPicker(false)}
        />
      )}
    </>
  );
}

/* ── Helpers ── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] font-bold text-[#555] uppercase tracking-wider mb-2 font-mono">
        {title}
      </div>
      {children}
    </div>
  );
}

function Checkbox({
  checked,
  onChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-1.5 text-[11px] font-mono select-none transition-colors ${
        disabled
          ? "text-[#555] opacity-50 cursor-not-allowed"
          : "text-[#888] cursor-pointer hover:text-[#E0E0E0]"
      }`}
      title={hint}
    >
      <span className={`font-bold ${!disabled && checked ? "text-[var(--color-accent)]" : "text-[#555]"}`}>
        {checked && !disabled ? "[x]" : "[ ]"}
      </span>
      <input
        type="checkbox"
        checked={checked && !disabled}
        onChange={(e) => { if (!disabled) onChange(e.target.checked); }}
        disabled={disabled}
        className="sr-only"
      />
      {label}
    </label>
  );
}

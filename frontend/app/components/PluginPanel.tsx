"use client";

import { useState, useEffect } from "react";

interface PluginConfig {
  key: string;
  label: string;
  type: "string" | "number" | "boolean" | "select";
  value: string | number | boolean;
  options?: string[];
  description?: string;
}

interface PluginInfo {
  name: string;
  description: string;
  type: string;
  trigger: string;
  modes: string[];
  enabled: boolean;
  config?: PluginConfig[];
}

const TYPE_COLORS: Record<string, string> = {
  hook: "text-accent bg-accent/10 border-accent/30",
  prompt_fragment: "text-warning bg-warning/10 border-warning/30",
  tool_config: "text-success bg-success/10 border-success/30",
};

export function PluginPanel({ onClose }: { onClose: () => void }) {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedPlugins, setExpandedPlugins] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchPlugins();
  }, []);

  const fetchPlugins = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/plugins");
      const data = await res.json();
      setPlugins(data.plugins || []);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  };

  const togglePlugin = async (name: string) => {
    try {
      await fetch(`/api/plugins/${encodeURIComponent(name)}/toggle`, {
        method: "POST",
      });
      setPlugins((prev) =>
        prev.map((p) =>
          p.name === name ? { ...p, enabled: !p.enabled } : p
        )
      );
    } catch {
      // Ignore
    }
  };

  const updatePluginConfig = async (pluginName: string, key: string, value: string | number | boolean) => {
    try {
      await fetch(`/api/plugins/${encodeURIComponent(pluginName)}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value }),
      });
      setPlugins((prev) =>
        prev.map((p) =>
          p.name === pluginName && p.config
            ? { ...p, config: p.config.map((c) => (c.key === key ? { ...c, value } : c)) }
            : p
        )
      );
    } catch {
      // Ignore
    }
  };

  const toggleExpanded = (name: string) => {
    setExpandedPlugins((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
      />
      {/* Panel */}
      <div className="relative w-96 h-full bg-surface border-l border-border-subtle flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-surface-raised">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-text-primary">
              Plugins
            </span>
            <span className="text-xs text-text-muted font-mono px-1.5 py-0.5 rounded-full border border-border-subtle">
              {plugins.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-sm transition-colors"
          >
            {"\u2715"}
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <span className="text-sm text-text-muted">Loading...</span>
            </div>
          ) : plugins.length === 0 ? (
            <div className="p-4 space-y-3">
              <p className="text-sm text-text-muted text-center">
                No plugins configured.
              </p>
              <div className="rounded-lg border border-border-subtle bg-surface-raised p-3">
                <p className="text-xs text-text-secondary mb-2">
                  Create a plugin config at:
                </p>
                <code className="text-xs text-accent font-mono block">
                  ~/.swarmweaver/plugins.yaml
                </code>
                <p className="text-xs text-text-muted mt-2">
                  or in your project:
                </p>
                <code className="text-xs text-accent font-mono block">
                  .swarmweaver/plugins.yaml
                </code>
              </div>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle/50">
              {plugins.map((plugin) => (
                <div
                  key={plugin.name}
                  className={`px-4 py-3 transition-colors ${
                    plugin.enabled ? "" : "opacity-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-text-primary">
                          {plugin.name}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                            TYPE_COLORS[plugin.type] || TYPE_COLORS.hook
                          }`}
                        >
                          {plugin.type}
                        </span>
                        {plugin.config && plugin.config.length > 0 && (
                          <button
                            onClick={() => toggleExpanded(plugin.name)}
                            className="text-[10px] text-text-muted hover:text-text-secondary transition-colors"
                            title="Toggle config"
                          >
                            {expandedPlugins.has(plugin.name) ? "\u25BC" : "\u2699"}
                          </button>
                        )}
                      </div>
                      <p className="text-xs text-text-secondary mb-1.5">
                        {plugin.description}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {plugin.trigger && (
                          <span className="text-[10px] text-text-muted bg-surface-raised px-1.5 py-0.5 rounded border border-border-subtle font-mono">
                            {plugin.trigger}
                          </span>
                        )}
                        {plugin.modes.map((mode) => (
                          <span
                            key={mode}
                            className="text-[10px] text-text-muted bg-surface-raised px-1.5 py-0.5 rounded border border-border-subtle"
                          >
                            {mode}
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={() => togglePlugin(plugin.name)}
                      className={`relative shrink-0 w-9 h-5 rounded-full transition-colors ${
                        plugin.enabled
                          ? "bg-accent"
                          : "bg-border-subtle"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                          plugin.enabled
                            ? "translate-x-4"
                            : "translate-x-0.5"
                        }`}
                      />
                    </button>
                  </div>
                  {/* Expandable config form */}
                  {expandedPlugins.has(plugin.name) && plugin.config && plugin.config.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border-subtle/50 space-y-2">
                      {plugin.config.map((cfg) => (
                        <div key={cfg.key} className="flex items-center gap-2">
                          <label className="text-[10px] text-text-secondary font-mono w-24 shrink-0 truncate" title={cfg.description || cfg.key}>
                            {cfg.label || cfg.key}
                          </label>
                          {cfg.type === "boolean" ? (
                            <button
                              onClick={() => updatePluginConfig(plugin.name, cfg.key, !cfg.value)}
                              className={`relative shrink-0 w-7 h-4 rounded-full transition-colors ${
                                cfg.value ? "bg-accent" : "bg-border-subtle"
                              }`}
                            >
                              <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-transform ${
                                cfg.value ? "translate-x-3" : "translate-x-0.5"
                              }`} />
                            </button>
                          ) : cfg.type === "select" && cfg.options ? (
                            <select
                              value={String(cfg.value)}
                              onChange={(e) => updatePluginConfig(plugin.name, cfg.key, e.target.value)}
                              className="flex-1 text-[10px] font-mono bg-surface border border-border-subtle rounded px-1.5 py-1 text-text-primary"
                            >
                              {cfg.options.map((opt) => (
                                <option key={opt} value={opt}>{opt}</option>
                              ))}
                            </select>
                          ) : cfg.type === "number" ? (
                            <input
                              type="number"
                              value={Number(cfg.value)}
                              onChange={(e) => updatePluginConfig(plugin.name, cfg.key, Number(e.target.value))}
                              className="flex-1 text-[10px] font-mono bg-surface border border-border-subtle rounded px-1.5 py-1 text-text-primary w-20"
                            />
                          ) : (
                            <input
                              type="text"
                              value={String(cfg.value)}
                              onChange={(e) => updatePluginConfig(plugin.name, cfg.key, e.target.value)}
                              className="flex-1 text-[10px] font-mono bg-surface border border-border-subtle rounded px-1.5 py-1 text-text-primary"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

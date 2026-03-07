"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const REMOVED_THEMES = ["sunset", "sky", "grape", "coral"] as const;

export type ThemeId =
  | "ember" | "cyan" | "verdant" | "rose"
  | "amber" | "violet" | "lime" | "teal"
  | "fuchsia" | "indigo" | "copper";

export interface GlobalSettings {
  defaultModel: string;
  phaseModels: { architect: string; plan: string; code: string };
  useWorktree: boolean;
  approvalGates: boolean;
  autoPr: boolean;
  budgetLimit: number | null;
  maxHours: number | null;
  defaultParallel: number;
  skipQA: boolean;
  theme: ThemeId;
  defaultBrowsePath: string | null;
}

const STORAGE_KEY = "swarmweaver-global-settings";
const OLD_SKIP_QA_KEY = "swarmweaver-skip-qa";

const DEFAULT_SETTINGS: GlobalSettings = {
  defaultModel: "claude-sonnet-4-6",
  phaseModels: { architect: "", plan: "", code: "" },
  useWorktree: true,
  approvalGates: false,
  autoPr: false,
  budgetLimit: null,
  maxHours: null,
  defaultParallel: 1,
  skipQA: false,
  theme: "ember",
  defaultBrowsePath: null,
};

export function useGlobalSettings() {
  const [settings, setSettings] = useState<GlobalSettings>(DEFAULT_SETTINGS);
  const [syncing, setSyncing] = useState(false);
  const initialized = useRef(false);

  /* Load from localStorage on mount (avoids SSR mismatch) */
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<GlobalSettings>;
        /* Migrate removed themes to ember */
        if (parsed.theme && REMOVED_THEMES.includes(parsed.theme as (typeof REMOVED_THEMES)[number])) {
          parsed.theme = "ember" as ThemeId;
          localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...parsed, theme: "ember" }));
        }
        setSettings((prev) => ({ ...prev, ...parsed }));
      }

      /* Migrate standalone skipQA key */
      const oldSkipQA = localStorage.getItem(OLD_SKIP_QA_KEY);
      if (oldSkipQA !== null) {
        const skipQA = oldSkipQA === "true";
        setSettings((prev) => {
          const merged = { ...prev, skipQA };
          localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
          return merged;
        });
        localStorage.removeItem(OLD_SKIP_QA_KEY);
      }
    } catch {
      /* ignore corrupt localStorage */
    }
  }, []);

  /* Persist to localStorage on every change (skip initial) */
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    } catch {
      /* quota exceeded — silently ignore */
    }
  }, [settings]);

  const updateSettings = useCallback((partial: Partial<GlobalSettings>) => {
    setSettings((prev) => ({ ...prev, ...partial }));
  }, []);

  const syncToBackend = useCallback(async () => {
    setSyncing(true);
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
    } catch {
      /* network error — silently ignore */
    } finally {
      setSyncing(false);
    }
  }, [settings]);

  const syncFromBackend = useCallback(async () => {
    setSyncing(true);
    try {
      const res = await fetch("/api/settings");
      if (res.ok) {
        const data = await res.json();
        if (data.settings) {
          const merged = { ...DEFAULT_SETTINGS, ...data.settings };
          if (merged.theme && REMOVED_THEMES.includes(merged.theme as (typeof REMOVED_THEMES)[number])) {
            merged.theme = "ember";
          }
          setSettings(merged);
        }
      }
    } catch {
      /* network error */
    } finally {
      setSyncing(false);
    }
  }, []);

  return { settings, updateSettings, syncing, syncToBackend, syncFromBackend };
}

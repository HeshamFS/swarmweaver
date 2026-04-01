"use client";

import { useState, useCallback, useEffect } from "react";
import { createNewTabMeta, type SessionTabMeta } from "./components/TabBar";
import { SessionSidebar } from "./components/SessionSidebar";
import SessionTab from "./components/SessionTab";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ConfirmModal } from "./components/ConfirmModal";
import { SettingsPanel } from "./components/SettingsPanel";
import { CommandPalette } from "./components/CommandPalette";
import { useGlobalSettings } from "./hooks/useGlobalSettings";

export default function Home() {
  /* ── Global settings ── */
  const { settings: globalSettings, updateSettings, syncing, syncToBackend } = useGlobalSettings();
  const [settingsOpen, setSettingsOpen] = useState(false);

  /* ── Tab state ── */

  const [tabs, setTabs] = useState<SessionTabMeta[]>(() => {
    const initial = createNewTabMeta();
    return [initial];
  });
  const [activeTabId, setActiveTabId] = useState<string>(() => tabs[0].id);

  /* ── Tab operations ── */

  const handleNewTab = useCallback(() => {
    const newTab = createNewTabMeta();
    setTabs((prev) => [...prev, newTab]);
    setActiveTabId(newTab.id);
  }, []);

  const [closeConfirm, setCloseConfirm] = useState<{
    tabId: string;
    label: string;
  } | null>(null);

  const doCloseTab = useCallback(
    (tabId: string) => {
      setTabs((prev) => {
        const remaining = prev.filter((t) => t.id !== tabId);
        if (remaining.length === 0) {
          const fresh = createNewTabMeta();
          setActiveTabId(fresh.id);
          return [fresh];
        }
        if (tabId === activeTabId) {
          const closedIndex = prev.findIndex((t) => t.id === tabId);
          const newActiveIndex = Math.min(closedIndex, remaining.length - 1);
          setActiveTabId(remaining[newActiveIndex].id);
        }
        return remaining;
      });
    },
    [activeTabId]
  );

  const handleCloseTab = useCallback(
    (tabId: string) => {
      const tab = tabs.find((t) => t.id === tabId);
      if (tab && tab.status === "running") {
        setCloseConfirm({ tabId, label: tab.label });
        return;
      }
      doCloseTab(tabId);
    },
    [tabs, doCloseTab]
  );

  const handleMetaChange = useCallback(
    (tabId: string, updates: Partial<SessionTabMeta>) => {
      setTabs((prev) =>
        prev.map((t) => (t.id === tabId ? { ...t, ...updates } : t))
      );
    },
    []
  );

  /* ── Apply theme to document ── */
  useEffect(() => {
    if (globalSettings.theme && globalSettings.theme !== "ember") {
      document.documentElement.dataset.theme = globalSettings.theme;
    } else {
      delete document.documentElement.dataset.theme;
    }
  }, [globalSettings.theme]);

  /* ── Command palette action handler ── */

  const handleCommandPaletteAction = useCallback(
    (action: string) => {
      if (action === "new-tab") {
        handleNewTab();
      } else if (action.startsWith("output-style:")) {
        const style = action.replace("output-style:", "");
        updateSettings({ outputStyle: style });
      } else if (
        action === "show-plan" ||
        action === "toggle-costs" ||
        action === "show-permissions"
      ) {
        // Map command palette actions to drawer section names
        const sectionMap: Record<string, string> = {
          "show-plan": "plan",
          "toggle-costs": "costs",
          "show-permissions": "permissions",
        };
        const section = sectionMap[action];
        if (section) {
          window.dispatchEvent(
            new CustomEvent("swarmweaver:open-drawer", { detail: { section } })
          );
        }
      }
    },
    [handleNewTab, updateSettings]
  );

  /* ── Keyboard shortcut: Ctrl+N for new session ── */

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "n") {
        e.preventDefault();
        handleNewTab();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handleNewTab]);

  /* ── Render ── */

  return (
    <div className="h-screen flex overflow-hidden bg-[#0C0C0C] font-mono text-sm antialiased relative">
      {/* Main app content layer */}
      <div className="relative z-10 flex h-full w-full">
        {/* Session sidebar — permanent left panel */}
        <SessionSidebar
          tabs={tabs}
          activeTabId={activeTabId}
          onSelectTab={setActiveTabId}
          onCloseTab={handleCloseTab}
          onNewTab={handleNewTab}
          onOpenSettings={() => setSettingsOpen(true)}
        />

        {/* Session content — fills remaining space */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {tabs.map((tab) => (
            <ErrorBoundary key={tab.id} fallbackLabel={`Tab ${tab.id}`}>
              <SessionTab
                tabId={tab.id}
                isVisible={tab.id === activeTabId}
                onMetaChange={handleMetaChange}
                globalSettings={globalSettings}
                onUpdateGlobalSettings={updateSettings}
              />
            </ErrorBoundary>
          ))}
        </div>
      </div>

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={globalSettings}
        onUpdate={updateSettings}
        syncing={syncing}
        onSync={syncToBackend}
      />

      <ConfirmModal
        open={!!closeConfirm}
        title="Close session"
        message={
          closeConfirm
            ? `"${closeConfirm.label}" has a running agent. Stop it and close the tab?`
            : ""
        }
        confirmLabel="Stop & close"
        cancelLabel="Cancel"
        variant="warning"
        onConfirm={() => {
          if (closeConfirm) {
            doCloseTab(closeConfirm.tabId);
            setCloseConfirm(null);
          }
        }}
        onCancel={() => setCloseConfirm(null)}
      />

      <CommandPalette onAction={handleCommandPaletteAction} />
    </div>
  );
}

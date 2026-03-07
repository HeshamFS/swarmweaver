"use client";

import { useState, useEffect } from "react";

interface NotificationSettingsProps {
  projectDir: string;
  onClose: () => void;
}

interface NotifConfig {
  enabled: boolean;
  webhook_url: string;
  slack_webhook: string;
  discord_webhook: string;
  notify_on: string[];
}

const EVENT_OPTIONS = [
  { id: "task_completed", label: "Task completed" },
  { id: "all_tasks_done", label: "All tasks done" },
  { id: "error", label: "Error occurred" },
  { id: "agent_stuck", label: "Agent stuck / loop detected" },
];

export function NotificationSettings({
  projectDir,
  onClose,
}: NotificationSettingsProps) {
  const [config, setConfig] = useState<NotifConfig>({
    enabled: true,
    webhook_url: "",
    slack_webhook: "",
    discord_webhook: "",
    notify_on: ["task_completed", "all_tasks_done", "error", "agent_stuck"],
  });
  const [browserEnabled, setBrowserEnabled] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
    // Check browser notification permission
    if ("Notification" in window) {
      setBrowserEnabled(Notification.permission === "granted");
    }
  }, [projectDir]);

  const fetchConfig = async () => {
    if (!projectDir) return;
    try {
      const res = await fetch(
        `/api/notifications/config?path=${encodeURIComponent(projectDir)}`
      );
      const data = await res.json();
      setConfig(data);
    } catch {
      // Ignore
    }
  };

  const saveConfig = async () => {
    if (!projectDir) return;
    setSaving(true);
    try {
      await fetch(
        `/api/notifications/config?path=${encodeURIComponent(projectDir)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        }
      );
    } catch {
      // Ignore
    } finally {
      setSaving(false);
    }
  };

  const requestBrowserPermission = async () => {
    if ("Notification" in window) {
      const permission = await Notification.requestPermission();
      setBrowserEnabled(permission === "granted");
    }
  };

  const sendTest = async () => {
    if (!projectDir) return;
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(
        `/api/notifications/test?path=${encodeURIComponent(projectDir)}`,
        { method: "POST" }
      );
      const data = await res.json();
      const results = data.results || [];
      if (results.length === 0) {
        setTestResult("No webhooks configured");
      } else {
        const successes = results.filter((r: { success: boolean }) => r.success).length;
        setTestResult(
          `${successes}/${results.length} webhooks delivered successfully`
        );
      }
    } catch {
      setTestResult("Failed to send test");
    } finally {
      setTesting(false);
    }
  };

  const toggleEvent = (eventId: string) => {
    setConfig((prev) => ({
      ...prev,
      notify_on: prev.notify_on.includes(eventId)
        ? prev.notify_on.filter((e) => e !== eventId)
        : [...prev.notify_on, eventId],
    }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-md mx-4 rounded-xl border border-border-subtle bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
          <h2 className="text-lg font-semibold text-text-primary">
            Notification Settings
          </h2>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1 rounded transition-colors"
          >
            {"\u2715"}
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Browser notifications */}
          <div>
            <label className="flex items-center justify-between">
              <span className="text-sm text-text-primary font-medium">
                Browser notifications
              </span>
              {browserEnabled ? (
                <span className="text-xs text-success">Enabled</span>
              ) : (
                <button
                  onClick={requestBrowserPermission}
                  className="text-xs text-accent hover:underline"
                >
                  Enable
                </button>
              )}
            </label>
            <p className="text-xs text-text-muted mt-1">
              Get desktop notifications when tasks complete or errors occur
            </p>
          </div>

          {/* Webhook URLs */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-text-secondary mb-1 font-medium">
                Slack Webhook URL
              </label>
              <input
                type="url"
                value={config.slack_webhook}
                onChange={(e) =>
                  setConfig({ ...config, slack_webhook: e.target.value })
                }
                placeholder="https://hooks.slack.com/services/..."
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1 font-medium">
                Discord Webhook URL
              </label>
              <input
                type="url"
                value={config.discord_webhook}
                onChange={(e) =>
                  setConfig({ ...config, discord_webhook: e.target.value })
                }
                placeholder="https://discord.com/api/webhooks/..."
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1 font-medium">
                Generic Webhook URL
              </label>
              <input
                type="url"
                value={config.webhook_url}
                onChange={(e) =>
                  setConfig({ ...config, webhook_url: e.target.value })
                }
                placeholder="https://your-server.com/webhook"
                className="w-full rounded-md border border-border-subtle bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
              />
            </div>
          </div>

          {/* Event checkboxes */}
          <div>
            <span className="text-xs text-text-secondary font-medium block mb-2">
              Notify on
            </span>
            <div className="space-y-2">
              {EVENT_OPTIONS.map((evt) => (
                <label
                  key={evt.id}
                  className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={config.notify_on.includes(evt.id)}
                    onChange={() => toggleEvent(evt.id)}
                    className="rounded border-border-subtle accent-accent"
                  />
                  {evt.label}
                </label>
              ))}
            </div>
          </div>

          {/* Test result */}
          {testResult && (
            <div className="text-xs text-text-secondary bg-surface-raised rounded-md px-3 py-2 border border-border-subtle">
              {testResult}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-4 border-t border-border-subtle">
          <button
            onClick={sendTest}
            disabled={testing}
            className="rounded-md border border-border-subtle px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:border-border-default transition-colors disabled:opacity-50"
          >
            {testing ? "Sending..." : "Test"}
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="rounded-md border border-border-subtle px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                await saveConfig();
                onClose();
              }}
              disabled={saving}
              className="rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover transition-colors disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState, useEffect } from "react";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info" | "warning";
  title: string;
  body?: string;
}

interface ToastProps {
  messages: ToastMessage[];
  onDismiss: (id: string) => void;
}

const TOAST_STYLES: Record<string, string> = {
  success: "border-success/40 bg-success/10",
  error: "border-error/40 bg-error/10",
  info: "border-accent/40 bg-accent/10",
  warning: "border-warning/40 bg-warning/10",
};

const TOAST_ICONS: Record<string, string> = {
  success: "\u2713",
  error: "\u2717",
  info: "\u24D8",
  warning: "\u26A0",
};

const TOAST_TITLE_COLORS: Record<string, string> = {
  success: "text-success",
  error: "text-error",
  info: "text-accent",
  warning: "text-warning",
};

function ToastItem({
  message,
  onDismiss,
}: {
  message: ToastMessage;
  onDismiss: () => void;
}) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm animate-slide-in ${TOAST_STYLES[message.type]}`}
    >
      <span className={`text-sm ${TOAST_TITLE_COLORS[message.type]}`}>
        {TOAST_ICONS[message.type]}
      </span>
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-medium ${TOAST_TITLE_COLORS[message.type]}`}
        >
          {message.title}
        </p>
        {message.body && (
          <p className="text-xs text-text-secondary mt-0.5 truncate">
            {message.body}
          </p>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="text-text-muted hover:text-text-primary text-xs p-0.5"
      >
        {"\u2715"}
      </button>
    </div>
  );
}

export function ToastContainer({ messages, onDismiss }: ToastProps) {
  if (messages.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80">
      {messages.map((msg) => (
        <ToastItem
          key={msg.id}
          message={msg}
          onDismiss={() => onDismiss(msg.id)}
        />
      ))}
    </div>
  );
}

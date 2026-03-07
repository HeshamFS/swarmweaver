"use client";

import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";

type Variant = "danger" | "warning" | "default";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
  onConfirm: () => void;
  onCancel: () => void;
}

const VARIANT_BUTTON_CLASS: Record<Variant, string> = {
  danger:
    "text-[var(--color-error)] border border-[var(--color-error)] hover:bg-[var(--color-error)] hover:text-[#0C0C0C]",
  warning:
    "text-[var(--color-warning)] border border-[var(--color-warning)] hover:bg-[var(--color-warning)] hover:text-[#0C0C0C]",
  default:
    "text-[var(--color-accent)] border border-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-[#0C0C0C]",
};

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "danger",
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const confirmClass = `px-3 py-1 text-[10px] font-mono font-bold uppercase tracking-wider transition-colors ${VARIANT_BUTTON_CLASS[variant]}`;

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      } else if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onConfirm, onCancel]);

  return (
    <AnimatePresence mode="wait">
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md p-4"
          onClick={(e) => e.target === e.currentTarget && onCancel()}
        >
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="w-full max-w-lg bg-[#121212] border border-[#333] border-l-4 border-l-[var(--color-accent)] shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-4 border-b border-[#222] bg-[#0C0C0C]">
              <h2 className="text-xs font-bold text-[#E0E0E0] font-mono uppercase tracking-wider">
                {title}
              </h2>
              <p className="mt-2 text-[12px] text-[#888] font-mono leading-relaxed">
                {message}
              </p>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-4 bg-[#121212] border-t border-[#222]">
              <button
                onClick={onCancel}
                className="px-3 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-[#555] hover:text-[#E0E0E0] hover:border-[#555] transition-colors border border-[#333]"
              >
                {cancelLabel}
              </button>
              <button onClick={onConfirm} className={confirmClass}>
                {confirmLabel}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

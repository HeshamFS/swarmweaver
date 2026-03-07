"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface DrawerSectionProps {
  title: string;
  icon?: React.ReactNode;
  count?: number;
  hasNotification?: boolean;
  defaultOpen?: boolean;
  forceOpen?: boolean;
  children: React.ReactNode;
  onExpand?: () => void;
}

export function DrawerSection({
  title,
  icon,
  count,
  hasNotification,
  defaultOpen = false,
  forceOpen,
  children,
  onExpand,
}: DrawerSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [hasRendered, setHasRendered] = useState(defaultOpen);
  const effectiveOpen = forceOpen ?? open;
  const expandedRef = useRef(false);

  // Lazy render: once opened, keep rendered
  useEffect(() => {
    if (effectiveOpen && !hasRendered) {
      setHasRendered(true);
    }
  }, [effectiveOpen, hasRendered]);

  // Fire onExpand callback on first open
  useEffect(() => {
    if (effectiveOpen && !expandedRef.current) {
      expandedRef.current = true;
      onExpand?.();
    }
    if (!effectiveOpen) {
      expandedRef.current = false;
    }
  }, [effectiveOpen, onExpand]);

  const toggle = useCallback(() => {
    if (forceOpen !== undefined) return;
    setOpen((v) => !v);
  }, [forceOpen]);

  return (
    <div className="border-b border-[#222]">
      {/* Header */}
      <button
        onClick={toggle}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-[#1A1A1A] transition-colors group"
      >
        {/* Icon */}
        {icon && (
          <span className="text-[#555] group-hover:text-[#888] transition-colors shrink-0">
            {icon}
          </span>
        )}

        {/* Title */}
        <span className="text-xs font-mono font-medium text-[#E0E0E0] flex-1 uppercase tracking-wider">
          {title}
        </span>

        {/* Count badge */}
        {count != null && count > 0 && (
          <span className="text-[10px] font-mono text-[#888] bg-[#1A1A1A] border border-[#333] px-1.5 py-0.5 shrink-0">
            {count}
          </span>
        )}

        {/* Notification dot */}
        {hasNotification && (
          <span className="w-1.5 h-1.5 bg-[var(--color-accent)] shrink-0" />
        )}

        {/* Chevron */}
        <span className="text-[#555] text-xs shrink-0">
          {effectiveOpen ? "\u25BC" : "\u25B6"}
        </span>
      </button>

      {/* Content */}
      <AnimatePresence initial={false}>
        {effectiveOpen && hasRendered && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

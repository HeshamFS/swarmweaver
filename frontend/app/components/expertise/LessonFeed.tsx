"use client";

import { SEVERITY_COLORS } from "../ExpertisePanel";

interface LessonEvent {
  type: string;
  timestamp: string;
  data?: Record<string, unknown>;
}

interface LessonFeedProps {
  events: LessonEvent[];
  maxItems?: number;
}

/**
 * Small widget showing real-time MELS lesson creation/propagation
 * during swarm mode. Designed for embedding in ExecutionDashboard.
 */
export function LessonFeed({ events, maxItems = 10 }: LessonFeedProps) {
  const lessonEvents = events
    .filter(
      (e) =>
        e.type === "expertise_lesson_created" ||
        e.type === "expertise_lesson_propagated" ||
        e.type === "expertise_record_promoted"
    )
    .slice(0, maxItems);

  if (lessonEvents.length === 0) {
    return null; // Don't render anything if no lessons
  }

  return (
    <div className="border border-border-subtle rounded-lg p-2 mb-2 bg-surface">
      <div className="text-[10px] text-text-muted font-mono font-medium mb-1 uppercase tracking-wider">
        Live Lessons
      </div>
      <div className="space-y-1 max-h-32 overflow-y-auto">
        {lessonEvents.map((ev, i) => {
          const severity = (ev.data?.severity as string) || "medium";
          const content = (ev.data?.content as string) || "";
          const workerId = ev.data?.worker_id;

          const typeLabel =
            ev.type === "expertise_lesson_propagated"
              ? "PROP"
              : ev.type === "expertise_record_promoted"
              ? "PERM"
              : "NEW";

          const typeColor =
            ev.type === "expertise_record_promoted"
              ? "text-success"
              : ev.type === "expertise_lesson_propagated"
              ? "text-info"
              : "text-warning";

          return (
            <div key={i} className="flex items-start gap-1 text-xs font-mono">
              <span className={`${typeColor} text-[10px] w-8 shrink-0`}>
                {typeLabel}
              </span>
              <span
                className={`text-[10px] shrink-0 ${
                  SEVERITY_COLORS[severity] || "text-text-muted"
                }`}
              >
                {severity[0]?.toUpperCase()}
              </span>
              <span className="text-text-primary truncate flex-1" title={content}>
                {content.slice(0, 80)}
              </span>
              {workerId != null && (
                <span className="text-text-muted text-[10px] shrink-0">
                  w{String(workerId)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

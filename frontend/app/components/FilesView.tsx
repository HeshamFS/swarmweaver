import type { SessionStats } from "../hooks/useSwarmWeaver";

export interface FilesViewProps {
  stats: SessionStats | null;
}

export function FilesView({ stats }: FilesViewProps) {
  const files = stats?.file_touches || {};
  const entries = Object.entries(files).sort(([, a], [, b]) => b - a);

  if (entries.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">No file activity recorded yet.</span>
      </div>
    );
  }

  const maxCount = Math.max(...entries.map(([, c]) => c));

  return (
    <div className="p-2 space-y-1">
      {entries.map(([file, count]) => (
        <div key={file} className="flex items-center gap-2 px-2 py-1">
          <div className="flex-1 min-w-0">
            <span className="text-xs text-text-primary font-mono truncate block">
              {file}
            </span>
          </div>
          <div className="w-24 h-1.5 rounded-full bg-border-subtle overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${(count / maxCount) * 100}%` }}
            />
          </div>
          <span className="text-xs text-text-muted font-mono w-8 text-right">
            {count}
          </span>
        </div>
      ))}
    </div>
  );
}

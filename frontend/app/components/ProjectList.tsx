"use client";

import type { ProjectInfo } from "../hooks/useSwarmWeaver";

interface ProjectListProps {
  projects: ProjectInfo[];
  onSelect: (path: string) => void;
}

export function ProjectList({ projects, onSelect }: ProjectListProps) {
  if (projects.length === 0) {
    return (
      <div className="text-sm text-text-muted py-4 text-center">
        No projects found. Run an agent to create one, or set SWARMWEAVER_PROJECT_DIRS to scan additional directories.
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {projects.map((project) => {
        const pct = project.percentage;
        return (
          <button
            key={project.path}
            onClick={() => onSelect(project.path)}
            className="w-full flex items-center gap-3 rounded-md px-3 py-2 text-left hover:bg-surface-overlay transition-colors group"
          >
            <div className="flex-1 min-w-0">
              <div className="text-sm text-text-primary font-medium truncate">
                {project.name}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                {project.mode && (
                  <span className="text-xs text-accent font-mono">
                    {project.mode}
                  </span>
                )}
                {project.has_tasks && (
                  <span className="text-xs text-text-muted font-mono">
                    {project.done}/{project.total} tasks
                  </span>
                )}
              </div>
            </div>
            {project.has_tasks && project.total > 0 && (
              <div className="w-16">
                <div className="h-1 rounded-full bg-border-subtle overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="text-xs text-text-muted text-right mt-0.5 font-mono">
                  {Math.round(pct)}%
                </div>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

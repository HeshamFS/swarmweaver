import { TaskPanel } from "../TaskPanel";
import { ObservabilityPanel } from "../ObservabilityPanel";
import { ADRPanel } from "../ADRPanel";
import { ExpertisePanel } from "../ExpertisePanel";
import type {
  AgentStatus,
  TaskData,
  AgentEvent,
  SessionStats,
} from "../../hooks/useSwarmWeaver";

type RightPanelTab = "tasks" | "observability" | "adrs" | "expertise" | "notes";

const RIGHT_TABS: { key: RightPanelTab; label: string }[] = [
  { key: "tasks", label: "Tasks" },
  { key: "observability", label: "Observe" },
  { key: "adrs", label: "ADRs" },
  { key: "expertise", label: "Expertise" },
  { key: "notes", label: "Notes" },
];

export interface InspectorPanelProps {
  rightTab: RightPanelTab;
  setRightTab: (tab: RightPanelTab) => void;
  tasks: TaskData | null;
  status: AgentStatus;
  sessionStats: SessionStats | null;
  currentProject: string;
  events: AgentEvent[];
  NotesPanel: React.ComponentType<{ projectDir: string }>;
}

export { RIGHT_TABS };
export type { RightPanelTab };

export function InspectorPanel({
  rightTab,
  setRightTab,
  tasks,
  status,
  sessionStats,
  currentProject,
  events,
  NotesPanel,
}: InspectorPanelProps) {
  return (
    <div className="flex flex-col h-full min-h-0 border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-glass)] backdrop-blur-xl shadow-[-4px_0_15px_rgba(0,0,0,0.1)] relative">
      {/* Tab selector */}
      <div className="flex items-center border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/40 p-2 backdrop-blur-md">
        <div className="flex w-full bg-[var(--color-surface-2)]/30 rounded-xl p-1 border border-[var(--color-border-subtle)]/50">
          {RIGHT_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setRightTab(tab.key)}
              className={`flex-1 px-3 py-1.5 text-[10px] sm:text-xs font-bold uppercase tracking-wider transition-all rounded-lg ${rightTab === tab.key
                  ? "text-[var(--color-accent)] bg-[var(--color-surface-1)] shadow-[0_2px_8px_rgba(0,0,0,0.2)]"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]"
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {rightTab === "tasks" && (
          <TaskPanel
            tasks={tasks}
            status={status}
            currentPhase={sessionStats?.current_phase}
            projectDir={currentProject}
          />
        )}
        {rightTab === "observability" && (
          <ObservabilityPanel
            events={events}
            sessionStats={sessionStats}
            projectDir={currentProject}
            status={status}
          />
        )}
        {rightTab === "adrs" && <ADRPanel projectDir={currentProject} />}
        {rightTab === "expertise" && <ExpertisePanel projectDir={currentProject} />}
        {rightTab === "notes" && <NotesPanel projectDir={currentProject} />}
      </div>
    </div>
  );
}

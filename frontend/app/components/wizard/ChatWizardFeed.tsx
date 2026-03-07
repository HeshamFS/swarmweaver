"use client";

import { useRef, useEffect, useCallback } from "react";
import type {
  WizardStep,
  Mode,
  TaskData,
  RunConfig,
  AgentStatus,
  AgentEvent,
  SessionStats,
  ApprovalRequestData,
  WorktreeInfo,
} from "../../hooks/useSwarmWeaver";

import type { ToolEvent, ArchitectQuestion, ArchitectPhase } from "../../hooks/useArchitectStream";
import type { PlanPhase } from "../../hooks/usePlanStream";
import ThinkingBar from "./ThinkingBar";
import ArchitectResearchPanel from "./ArchitectToolCard";
import ArchitectQABlock from "./ArchitectQABlock";
import PlanAnalysisBlock from "./PlanAnalysisBlock";
import UserMessageBlock from "./chat-blocks/UserMessageBlock";
import QAInlineBlock from "./chat-blocks/QAInlineBlock";
import SpecReviewBlock from "./chat-blocks/SpecReviewBlock";
import TaskReviewBlock from "./chat-blocks/TaskReviewBlock";
import StrategyReviewBlock from "./chat-blocks/StrategyReviewBlock";
import InvestigationReportBlock from "./chat-blocks/InvestigationReportBlock";
import AuditReportBlock from "./chat-blocks/AuditReportBlock";
import SecurityScanBlock from "./chat-blocks/SecurityScanBlock";
import { ExecutionView } from "./ExecutionView";

interface ChatWizardFeedProps {
  wizardStep: WizardStep;
  selectedMode: Mode | null;
  currentProject: string;
  taskInput: string;
  projectDir: string;

  // QA
  qaMode: string;
  onQAComplete: (answers: Record<string, string>) => void;
  onQASkip: () => void;
  hasQA: boolean;
  wizardQAQuestions?: { question: string; context?: string; options: { label: string; description: string }[] }[];
  wizardPhase?: string;

  // Spec / Architect streaming
  isLightweightLoading: boolean;
  generatedSpec: string | null;
  architectTools?: ToolEvent[];
  architectQuestions?: ArchitectQuestion[];
  architectPhase?: ArchitectPhase;
  onArchitectAnswers?: (answers: Record<string, string>) => void;
  onApproveSpec: () => void;
  onRegenerate: (feedback: string) => void;
  onSaveSpec: (projectDir: string, spec: string) => Promise<void>;

  // Plan streaming
  planAnalysisText?: string;
  planPhase?: PlanPhase;
  isPlanRegenerating?: boolean;
  onRegeneratePlan?: (feedback: string) => void;

  // Mode-specific wizard state
  strategyText?: string | null;
  onApproveStrategy?: () => void;
  onRegenerateStrategy?: (feedback: string) => void;
  reportText?: string | null;
  onAcknowledgeReport?: () => void;
  securityFindings?: Record<string, unknown>[] | null;
  onApproveFindings?: (ids: string[], reasons: Record<string, string>) => void;

  // Timing
  wizardElapsedSecs?: number;
  wizardTimings?: Record<string, number>;

  // Tasks
  tasks: TaskData | null;
  onApproveTasks: () => void;
  onBackFromTasks: () => void;

  // Full swarmweaver state for ExecutionView
  swarmweaverState: {
    status: AgentStatus;
    output: string[];
    tasks: TaskData | null;
    currentProject: string;
    selectedMode: Mode | null;
    events: AgentEvent[];
    sessionStats: SessionStats | null;
    approvalRequest: ApprovalRequestData | null;
    worktreeInfo: WorktreeInfo | null;
    wsConnected?: boolean;
    stop: () => void;
    run: (config: RunConfig) => void;
    sendSteering: (message: string, type?: string) => void;
    resolveApproval: (decision: string, feedback?: string) => void;
    mergeWorktree: () => void;
    discardWorktree: () => void;
    goBack: () => void;
    lastConfig?: RunConfig | null;
    workerTokenMap?: Record<number, { input: number; output: number; cacheRead: number; cacheCreation: number }>;
  };
}

const STEP_ORDER: WizardStep[] = ["landing", "qa", "architect-review", "strategy-review", "report-review", "plan-review", "security-review", "execute"];

function stepReached(current: WizardStep, target: WizardStep): boolean {
  return STEP_ORDER.indexOf(current) >= STEP_ORDER.indexOf(target);
}

export default function ChatWizardFeed(props: ChatWizardFeedProps) {
  const {
    wizardStep, selectedMode, currentProject, taskInput, projectDir,
    qaMode, onQAComplete, onQASkip, hasQA, wizardQAQuestions, wizardPhase,
    isLightweightLoading, generatedSpec, architectTools, architectQuestions, architectPhase, onArchitectAnswers, onApproveSpec, onRegenerate, onSaveSpec,
    planAnalysisText, planPhase, isPlanRegenerating, onRegeneratePlan,
    strategyText, onApproveStrategy, onRegenerateStrategy,
    reportText, onAcknowledgeReport,
    securityFindings, onApproveFindings,
    wizardElapsedSecs, wizardTimings,
    tasks, onApproveTasks, onBackFromTasks,
    swarmweaverState,
  } = props;

  const feedRef = useRef<HTMLDivElement>(null);
  const prevStepRef = useRef(wizardStep);

  const scrollToBottom = useCallback((instant?: boolean) => {
    if (!feedRef.current) return;
    feedRef.current.scrollTo({ top: feedRef.current.scrollHeight, behavior: instant ? "instant" : "smooth" });
  }, []);

  useEffect(() => {
    if (wizardStep !== prevStepRef.current) {
      prevStepRef.current = wizardStep;
      setTimeout(scrollToBottom, 150);
    }
  }, [wizardStep, scrollToBottom]);

  // Auto-scroll as streaming spec text arrives (instant — smooth can't keep up with rapid deltas)
  useEffect(() => {
    if (isLightweightLoading && generatedSpec) {
      scrollToBottom(true);
    }
  }, [generatedSpec, isLightweightLoading, scrollToBottom]);

  // Auto-scroll when architect phase changes (questions appear, spec starts, etc.)
  useEffect(() => {
    if (architectPhase && architectPhase !== "idle") {
      setTimeout(scrollToBottom, 150);
    }
  }, [architectPhase, scrollToBottom]);

  // Auto-scroll as plan analysis text streams in
  useEffect(() => {
    if (planAnalysisText) {
      scrollToBottom(true);
    }
  }, [planAnalysisText, scrollToBottom]);

  const mode = selectedMode || "feature";
  const isGreenfield = mode === "greenfield";
  const isSecurity = mode === "security";
  const isRefactor = mode === "refactor";
  const isFix = mode === "fix";
  const isEvolve = mode === "evolve";
  const inExecution = wizardStep === "execute";

  // Determine if any phase past QA has actually started (for gating spec/task sections)
  const specPhaseStarted = wizardPhase === "research" || wizardPhase === "questions"
    || wizardPhase === "generating" || wizardPhase === "spec_complete";
  const planPhaseStarted = wizardPhase === "plan_analyzing" || wizardPhase === "plan_complete";

  // QA is complete only once the wizard phase has moved past QA (not just wizard step)
  const qaComplete = wizardPhase === "qa_complete"
    || specPhaseStarted
    || planPhaseStarted
    || inExecution;

  const specApproved = stepReached(wizardStep, "plan-review") || inExecution;
  const tasksApproved = inExecution;

  // Only show spec section once the research/spec phases have actually started (not just step transition)
  const showSpec = isGreenfield && (specApproved || (wizardStep === "architect-review" && specPhaseStarted));

  // Non-greenfield analysis phases (tool events displayed in research panel)
  const analysisPhaseActive = wizardPhase === "analyzing" || wizardPhase === "investigating"
    || wizardPhase === "auditing" || wizardPhase === "scanning";
  const showAnalysis = !isGreenfield && (analysisPhaseActive || wizardPhase === "questions"
    || wizardPhase === "generating_strategy" || wizardPhase === "strategy_complete"
    || wizardPhase === "generating_report" || wizardPhase === "report_complete"
    || wizardPhase === "generating_security" || wizardPhase === "security_complete"
    || planPhaseStarted || inExecution);

  // Follow-up questions (feature/refactor/evolve — appear after analysis, before plan)
  const showFollowUpQuestions = !isGreenfield && !isSecurity && !isFix
    && (wizardPhase === "questions" || wizardPhase === "generating_strategy" || wizardPhase === "strategy_complete"
      || wizardPhase === "generating_report" || wizardPhase === "report_complete"
      || planPhaseStarted || inExecution);

  // Strategy review (refactor only)
  const showStrategy = isRefactor && (wizardPhase === "generating_strategy" || wizardPhase === "strategy_complete"
    || planPhaseStarted || inExecution);
  const strategyApproved = planPhaseStarted || inExecution;

  // Report (fix/evolve)
  const showReport = (isFix || isEvolve) && (wizardPhase === "generating_report" || wizardPhase === "report_complete"
    || (isEvolve && (wizardPhase === "questions" || planPhaseStarted)) || (isFix && planPhaseStarted) || inExecution);
  const reportAcknowledged = (isFix && planPhaseStarted) || (isEvolve && (wizardPhase === "questions" || planPhaseStarted)) || inExecution;

  // Security findings (security only)
  const showSecurityFindings = isSecurity && (wizardPhase === "generating_security" || wizardPhase === "security_complete"
    || planPhaseStarted || inExecution);
  const securityApproved = planPhaseStarted || inExecution;

  // Only show tasks section once the plan phase has actually started
  const showTasks = tasksApproved || (stepReached(wizardStep, "plan-review") && planPhaseStarted);

  const analysisLabel = isSecurity ? "Security Scan" : isFix ? "Investigation" : isEvolve ? "Audit" : "Analysis";

  // Once we're in execution, render the full ExecutionView which handles
  // StatusBar, ActivityFeed, SteeringBar, Drawer, Terminal, Approval
  if (inExecution) {
    return <ExecutionView state={swarmweaverState} />;
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0C0C0C]">
      <div ref={feedRef} className="flex-1 overflow-y-auto tui-scrollbar">
        <div className="max-w-5xl mx-auto w-full p-6 pt-10">

          {/* 1. User message (with timer on the header bar) */}
          <UserMessageBlock
            text={taskInput}
            mode={mode}
            projectDir={projectDir}
            elapsedSecs={wizardElapsedSecs}
            isLoading={isLightweightLoading}
          />

          {/* 2. QA section */}
          {hasQA && (
            <>
              <ThinkingBar
                agentName="Setup Agent"
                label="Analyzing request..."
                active={wizardPhase === "qa" && (!wizardQAQuestions || wizardQAQuestions.length === 0)}
              />
              {wizardPhase === "qa_questions" && wizardQAQuestions && wizardQAQuestions.length > 0 ? (
                <QAInlineBlock
                  mode={qaMode}
                  taskInput={taskInput}
                  projectDir={projectDir}
                  onComplete={onQAComplete}
                  onSkip={onQASkip}
                  externalQuestions={wizardQAQuestions}
                />
              ) : qaComplete ? (
                <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
                  <div className="flex items-center gap-3 px-4 py-2">
                    <span className="text-[#555]">{"\u2713"}</span>
                    <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Setup Complete</span>
                  </div>
                </div>
              ) : null}
            </>
          )}

          {/* 2.5. Non-greenfield analysis section (reuses ArchitectResearchPanel with mode-specific label) */}
          {showAnalysis && (
            <>
              <ThinkingBar
                agentName={isSecurity ? "Scanner Agent" : isFix ? "Investigator Agent" : isEvolve ? "Auditor Agent" : "Analyzer Agent"}
                label={isSecurity ? "Scanning codebase..." : isFix ? "Investigating bug..." : isEvolve ? "Auditing codebase..." : "Analyzing codebase..."}
                active={analysisPhaseActive && (!architectTools || architectTools.length === 0)}
              />
              {architectTools && architectTools.length > 0 && (
                <ArchitectResearchPanel tools={architectTools} specApproved={strategyApproved || reportAcknowledged || securityApproved || planPhaseStarted} label={analysisLabel} />
              )}
            </>
          )}

          {/* 2.6. Follow-up questions (feature/refactor/evolve — after analysis) */}
          {showFollowUpQuestions && architectQuestions && architectQuestions.length > 0 && onArchitectAnswers && wizardPhase === "questions" && (
            <ArchitectQABlock
              questions={architectQuestions}
              onSubmit={onArchitectAnswers}
            />
          )}

          {/* 2.7. Strategy review (refactor only) */}
          {showStrategy && (
            <>
              <ThinkingBar
                agentName="Architect Agent"
                label="Generating migration strategy..."
                active={wizardPhase === "generating_strategy" && !strategyText}
              />
              {(wizardPhase === "generating_strategy" || wizardPhase === "strategy_complete" || strategyApproved) && (
                <StrategyReviewBlock
                  isLoading={isLightweightLoading && wizardPhase === "generating_strategy"}
                  strategyText={strategyText || null}
                  onApprove={onApproveStrategy || (() => {})}
                  onRegenerate={onRegenerateStrategy || (() => {})}
                  approved={strategyApproved}
                />
              )}
            </>
          )}

          {/* 2.8. Investigation/Audit report (fix/evolve) */}
          {showReport && (
            <>
              <ThinkingBar
                agentName={isFix ? "Investigator Agent" : "Auditor Agent"}
                label={isFix ? "Writing investigation report..." : "Writing audit report..."}
                active={wizardPhase === "generating_report" && !reportText}
              />
              {(wizardPhase === "generating_report" || wizardPhase === "report_complete" || reportAcknowledged) && isFix && (
                <InvestigationReportBlock
                  isLoading={isLightweightLoading && wizardPhase === "generating_report"}
                  reportText={reportText || null}
                  onAcknowledge={onAcknowledgeReport || (() => {})}
                  acknowledged={reportAcknowledged}
                />
              )}
              {(wizardPhase === "generating_report" || wizardPhase === "report_complete" || reportAcknowledged) && isEvolve && (
                <AuditReportBlock
                  isLoading={isLightweightLoading && wizardPhase === "generating_report"}
                  reportText={reportText || null}
                  onAcknowledge={onAcknowledgeReport || (() => {})}
                  acknowledged={reportAcknowledged}
                />
              )}
            </>
          )}

          {/* 2.9. Security findings (security mode) */}
          {showSecurityFindings && (
            <>
              <ThinkingBar
                agentName="Scanner Agent"
                label="Compiling security findings..."
                active={wizardPhase === "generating_security" && !securityFindings}
              />
              {(wizardPhase === "security_complete" || securityApproved) && securityFindings && (
                <SecurityScanBlock
                  isLoading={false}
                  findings={securityFindings as any}
                  onApproveFindings={onApproveFindings || (() => {})}
                  approved={securityApproved}
                />
              )}
            </>
          )}

          {/* 3. Spec section (greenfield only) */}
          {showSpec && (
            <>
              {/* 3a. Research thinking bar — active while researching */}
              <ThinkingBar
                agentName="Architect Agent"
                label="Researching..."
                active={wizardStep === "architect-review" && architectPhase === "research" && !architectTools?.length}
              />

              {/* 3b. Research panel — tool calls from SDK streaming */}
              {architectTools && architectTools.length > 0 && (
                <ArchitectResearchPanel tools={architectTools} specApproved={specApproved} />
              )}

              {/* 3c. Thinking bar — active after visible research tools finish, before questions arrive */}
              {architectPhase === "research" && architectTools && architectTools.filter(t => t.tool !== "StructuredOutput" && t.tool !== "structured_output").length > 0 && architectTools.filter(t => t.tool !== "StructuredOutput" && t.tool !== "structured_output").every(t => t.status === "done") && (
                <ThinkingBar
                  agentName="Architect Agent"
                  label="Analyzing research findings..."
                  active
                />
              )}

              {/* 3d. Architect clarifying questions */}
              {architectPhase === "questions" && architectQuestions && architectQuestions.length > 0 && onArchitectAnswers && (
                <ArchitectQABlock
                  questions={architectQuestions}
                  onSubmit={onArchitectAnswers}
                />
              )}

              {/* 3e. Thinking bar — only render once spec generation phase starts */}
              {(architectPhase === "generating" || architectPhase === "complete") && (
                <ThinkingBar
                  agentName="Architect Agent"
                  label="Writing specification..."
                  active={architectPhase === "generating" && !generatedSpec}
                />
              )}

              {/* 3f. Spec review block — only render once spec generation has started */}
              {(architectPhase === "generating" || architectPhase === "complete" || specApproved) && (
                <SpecReviewBlock
                  isLoading={isLightweightLoading}
                  generatedSpec={generatedSpec}
                  projectDir={currentProject}
                  onApprove={onApproveSpec}
                  onRegenerate={onRegenerate}
                  onSaveSpec={onSaveSpec}
                  approved={specApproved}
                />
              )}
            </>
          )}

          {/* 4. Task list section */}
          {showTasks && (
            <>
              {/* 4a-pre. Info banner when regeneration starts */}
              {isPlanRegenerating && isLightweightLoading && (
                <div className="flex items-start gap-2 px-4 py-2.5 mb-2 border border-[#2A2A2A] bg-[#0C0C0C] rounded font-mono text-[11px] text-[#888]">
                  <span className="text-[var(--color-accent)] shrink-0 mt-px">i</span>
                  <span>
                    The planner is re-evaluating the entire task list with your feedback.
                    This may take a moment.
                  </span>
                </div>
              )}

              {/* 4a. ThinkingBar: active only before any stream output arrives */}
              <ThinkingBar
                agentName={isGreenfield ? "Planner Agent" : isSecurity ? "Scanner Agent" : "Planner Agent"}
                label={
                  isSecurity ? "Scanning for vulnerabilities..." :
                  isPlanRegenerating ? "Regenerating task list based on feedback..." :
                  isGreenfield ? "Generating task list..." :
                  "Analyzing and planning..."
                }
                active={isLightweightLoading && !planAnalysisText && !tasks?.tasks?.length}
              />

              {/* 4b. Plan analysis block: streaming reasoning from SDK */}
              {planAnalysisText && (
                <PlanAnalysisBlock
                  analysisText={planAnalysisText}
                  isStreaming={isLightweightLoading}
                  hasTasks={!!tasks?.tasks?.length}
                />
              )}

              {/* 4c. ThinkingBar: visible while JSON is being generated/parsed (after analysis text appears, before tasks arrive) */}
              {planAnalysisText && !tasks?.tasks?.length && isLightweightLoading && (
                <ThinkingBar
                  agentName="Planner Agent"
                  label="Building task list..."
                  active
                />
              )}

              {/* 4d. Task review block */}
              <TaskReviewBlock
                isLoading={isLightweightLoading}
                tasks={tasks}
                onApprove={onApproveTasks}
                onBack={onBackFromTasks}
                approved={tasksApproved}
                onRegenerate={onRegeneratePlan}
              />
            </>
          )}

          {/* Bottom spacer */}
          <div className="h-16" />
        </div>
      </div>
    </div>
  );
}

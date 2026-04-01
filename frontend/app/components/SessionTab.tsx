"use client";

import { useEffect, useCallback, useRef, useState } from "react";

import { useSwarmWeaver } from "../hooks/useSwarmWeaver";
import type { SessionTabMeta } from "./TabBar";
import type { GlobalSettings } from "../hooks/useGlobalSettings";
import { ToastContainer } from "./Toast";
import LandingStep from "./wizard/LandingStep";
// @deprecated SecurityReportReview replaced by SecurityScanBlock in ChatWizardFeed
// import SecurityReportReview from "./wizard/SecurityReportReview";
import ChatWizardFeed from "./wizard/ChatWizardFeed";

/* ── Output style instructions (prepended to task_input when non-default) ── */

const OUTPUT_STYLE_INSTRUCTIONS: Record<string, string> = {
  verbose: "",  // default — no extra instructions
  concise: "\n[Output Style: Be concise. Key information only, minimal explanations.]\n",
  structured: "\n[Output Style: Use organized headers, bullets, and clear sections.]\n",
  minimal: "\n[Output Style: Bare essentials only — just code and critical notes.]\n",
};

function applyOutputStyle(
  config: import("../hooks/useSwarmWeaver").RunConfig,
  outputStyle: string | undefined,
): import("../hooks/useSwarmWeaver").RunConfig {
  const instruction = OUTPUT_STYLE_INSTRUCTIONS[outputStyle || "verbose"] || "";
  if (!instruction) return config;
  return { ...config, task_input: instruction + config.task_input };
}

/* ── Props ── */

interface SessionTabProps {
  tabId: string;
  isVisible: boolean;
  onMetaChange: (tabId: string, updates: Partial<SessionTabMeta>) => void;
  globalSettings?: GlobalSettings;
  onUpdateGlobalSettings?: (partial: Partial<GlobalSettings>) => void;
}

/* ── Component ── */

export default function SessionTab({ tabId, isVisible, onMetaChange, globalSettings, onUpdateGlobalSettings }: SessionTabProps) {
  const sw = useSwarmWeaver();
  const {
    // Wizard state
    wizardStep,
    setWizardStep,
    selectedMode,
    cliMode,
    setCliMode,
    generatedSpec,
    goBack,
    goToLanding,
    qaAnswers,
    setQaAnswers,
    // Wizard run helpers
    runArchitectOnly,
    runPlanOnly,
    runScanOnly,
    approveAndRun,
    approveSpecAndInitialize,
    handleApproveSecurityFindings,
    runDirect,
    resumeProject,
    removeProject,
    clearAllProjects,
    // Agent state
    status,
    output,
    projects,
    tasks,
    currentProject,
    events,
    sessionStats,
    toasts,
    approvalRequest,
    securityReport,
    worktreeInfo,
    isLightweightLoading,
    architectTools,
    architectQuestions,
    architectPhase,
    sendArchitectAnswers,
    planAnalysisText,
    planPhase,
    isPlanRegenerating,
    regeneratePlan,
    wsConnected,
    // Actions
    run,
    stop,
    reset,
    fetchProjects,
    fetchSpec,
    saveSpec,
    checkProjectStatus,
    fetchProjectSettings,
    saveProjectSettings,
    dismissToast,
    sendSteering,
    resolveApproval,
    mergeWorktree,
    discardWorktree,
    triageResults,
  } = sw;

  /* ── Push metadata changes up to TabBar ── */

  useEffect(() => {
    let tabStatus: SessionTabMeta["status"] = "idle";
    if (status === "running" || status === "starting") tabStatus = "running";
    else if (status === "completed") tabStatus = "completed";
    else if (status === "error") tabStatus = "error";
    else if (wizardStep !== "landing") tabStatus = "configuring";

    let label = "New Session";
    if (currentProject) {
      const segments = currentProject.replace(/\\/g, "/").split("/");
      label = segments[segments.length - 1] || currentProject;
    } else if (selectedMode) {
      label = selectedMode.charAt(0).toUpperCase() + selectedMode.slice(1);
    }

    onMetaChange(tabId, { label, mode: selectedMode, status: tabStatus });
  }, [tabId, wizardStep, selectedMode, status, currentProject, onMetaChange]);

  /* ── Keyboard shortcut: Ctrl+K (only when visible) ── */

  useEffect(() => {
    if (!isVisible) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCliMode((prev: boolean) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isVisible, setCliMode]);

  /* ── Regenerate spec with feedback (uses existing wizard WS — no subprocess spawn) ── */

  const { wizardStream: wStream, setGeneratedSpec: setSpec, setIsLightweightLoading: setLwLoading } = sw;

  const handleRegenerate = useCallback(
    (feedback: string) => {
      if (wStream) {
        wStream.regenerateSpec(feedback);
        setSpec(null);
        // Ensure loading state is active so completion watcher triggers correctly
        setLwLoading(true);
      }
    },
    [wStream, setSpec, setLwLoading]
  );

  /* ── Q&A config storage ── */
  const qaConfigRef = useRef<import("../hooks/useSwarmWeaver").RunConfig | null>(null);

  // Track the original task input and project dir for the chat feed
  const [chatTaskInput, setChatTaskInput] = useState("");
  const [chatProjectDir, setChatProjectDir] = useState("");

  /* ── Q&A completion handler (called when user answers wizard QA questions) ── */

  const handleQAComplete = useCallback(
    (answers: Record<string, string>) => {
      setQaAnswers(answers);
      // Send answers through the wizard WS — backend continues to next phase
      sw.sendWizardQAAnswers(answers);
    },
    [setQaAnswers, sw.sendWizardQAAnswers]
  );

  const handleQASkip = useCallback(() => {
    // Tell wizard WS to skip QA — backend continues to next phase
    sw.skipWizardQA();
  }, [sw.skipWizardQA]);

  /* ── Start QA handler (called from Omnibar via LandingStep) ── */
  /* Now starts the wizard WS directly — QA is Turn 0 of the unified conversation */

  const handleStartQA = useCallback(
    (config: import("../hooks/useSwarmWeaver").RunConfig) => {
      const styled = applyOutputStyle(config, globalSettings?.outputStyle);
      qaConfigRef.current = styled;
      setChatTaskInput(config.task_input);
      setChatProjectDir(config.project_dir);
      setWizardStep("qa");

      // Start wizard WS immediately — QA is the first turn
      if (styled.mode === "greenfield") {
        runArchitectOnly(styled);
      } else {
        // All non-greenfield modes (feature, refactor, fix, evolve, security)
        // go through the unified wizard WS with mode-specific streaming phases
        runPlanOnly(styled);
      }
    },
    [setWizardStep, runArchitectOnly, runPlanOnly, globalSettings?.outputStyle]
  );

  /* ── Plan mode gate ── */
  const [pendingPlanConfig, setPendingPlanConfig] = useState<import("../hooks/useSwarmWeaver").RunConfig | null>(null);

  const handlePlanApprove = useCallback(() => {
    if (!pendingPlanConfig) return;
    const config = pendingPlanConfig;
    setPendingPlanConfig(null);
    // Use approveAndRun so artifacts are prepared on disk before execution
    approveAndRun(config);
  }, [pendingPlanConfig, approveAndRun]);

  const handlePlanReject = useCallback(() => {
    setPendingPlanConfig(null);
    goBack();
  }, [goBack]);

  /** Wraps approveAndRun to intercept with plan mode gate when enabled */
  const handleApproveAndRun = useCallback(() => {
    if (globalSettings?.planModeEnabled && sw.lastConfig) {
      // Hold the config for plan review before execution
      setPendingPlanConfig(sw.lastConfig);
      setWizardStep("execute");
      return;
    }
    approveAndRun();
  }, [globalSettings?.planModeEnabled, approveAndRun, sw.lastConfig, setWizardStep]);

  /* ── Direct launch handlers that also capture taskInput for chat feed ── */

  const handleRunDirect = useCallback(
    (config: import("../hooks/useSwarmWeaver").RunConfig) => {
      const styled = applyOutputStyle(config, globalSettings?.outputStyle);
      setChatTaskInput(config.task_input);
      setChatProjectDir(config.project_dir);

      // Plan mode gate: show plan in drawer before running
      if (globalSettings?.planModeEnabled) {
        setPendingPlanConfig(styled);
        setWizardStep("execute");
        return;
      }

      runDirect(styled);
    },
    [runDirect, globalSettings?.outputStyle, globalSettings?.planModeEnabled, setWizardStep]
  );

  const handleRunArchitectOnly = useCallback(
    (config: import("../hooks/useSwarmWeaver").RunConfig) => {
      setChatTaskInput(config.task_input);
      setChatProjectDir(config.project_dir);
      setWizardStep("qa");
      runArchitectOnly(applyOutputStyle(config, globalSettings?.outputStyle));
    },
    [runArchitectOnly, setWizardStep, globalSettings?.outputStyle]
  );

  const handleRunPlanOnly = useCallback(
    (config: import("../hooks/useSwarmWeaver").RunConfig) => {
      setChatTaskInput(config.task_input);
      setChatProjectDir(config.project_dir);
      setWizardStep("qa");
      runPlanOnly(applyOutputStyle(config, globalSettings?.outputStyle));
    },
    [runPlanOnly, setWizardStep, globalSettings?.outputStyle]
  );

  const handleRunScanOnly = useCallback(
    (config: import("../hooks/useSwarmWeaver").RunConfig) => {
      setChatTaskInput(config.task_input);
      setChatProjectDir(config.project_dir);
      runScanOnly(applyOutputStyle(config, globalSettings?.outputStyle));
    },
    [runScanOnly, globalSettings?.outputStyle]
  );

  // QA is active when wizard stream is in QA phase or user has answered
  const wizardPhase = sw.wizardPhase;
  const hasQA = wizardStep === "qa"
    || wizardPhase === "qa" || wizardPhase === "qa_questions" || wizardPhase === "qa_complete"
    || Object.keys(qaAnswers).length > 0;

  /* ── Render ── */

  const isInChatFlow = wizardStep !== "landing";

  return (
    <div
      className={`flex-1 flex flex-col overflow-hidden ${isInChatFlow ? "min-h-0" : ""}`}
      style={{ display: isVisible ? "flex" : "none" }}
    >
      {/* Landing page */}
      {wizardStep === "landing" && (
        <LandingStep
          projects={projects}
          onResumeProject={resumeProject}
          onRemoveProject={removeProject}
          onClearAllProjects={clearAllProjects}
          fetchProjects={fetchProjects}
          checkProjectStatus={checkProjectStatus}
          fetchProjectSettings={fetchProjectSettings}
          saveProjectSettings={saveProjectSettings}
          onRunDirect={handleRunDirect}
          onRunArchitectOnly={handleRunArchitectOnly}
          onRunPlanOnly={handleRunPlanOnly}
          onRunScanOnly={handleRunScanOnly}
          onStartQA={handleStartQA}
          globalSettings={globalSettings}
          onUpdateGlobalSettings={onUpdateGlobalSettings}
        />
      )}

      {/* Chat wizard flow: qa -> architect-review -> [strategy/report/security review] -> plan-review -> execute */}
      {isInChatFlow && (
        <div className="flex-1 min-h-0 flex flex-col">
          <ChatWizardFeed
              wizardStep={wizardStep}
              selectedMode={selectedMode}
              currentProject={currentProject}
              taskInput={chatTaskInput || sw.lastConfig?.task_input || ""}
              projectDir={chatProjectDir || sw.lastConfig?.project_dir || currentProject}
              qaMode={qaConfigRef.current?.mode || selectedMode || "feature"}
              onQAComplete={handleQAComplete}
              onQASkip={handleQASkip}
              hasQA={hasQA}
              wizardQAQuestions={sw.wizardQAQuestions}
              wizardPhase={sw.wizardPhase}
              isLightweightLoading={isLightweightLoading}
              generatedSpec={generatedSpec}
              architectTools={architectTools}
              architectQuestions={architectQuestions}
              architectPhase={architectPhase}
              onArchitectAnswers={sendArchitectAnswers}
              onApproveSpec={approveSpecAndInitialize}
              onRegenerate={handleRegenerate}
              onSaveSpec={saveSpec}
              planAnalysisText={planAnalysisText}
              planPhase={planPhase}
              isPlanRegenerating={isPlanRegenerating}
              onRegeneratePlan={regeneratePlan}
              wizardElapsedSecs={sw.wizardStream?.elapsedSecs}
              wizardTimings={sw.wizardStream?.timings}
              tasks={tasks}
              onApproveTasks={handleApproveAndRun}
              onBackFromTasks={goBack}
              swarmweaverState={sw}
              strategyText={sw.strategyText}
              onApproveStrategy={sw.handleApproveStrategy}
              onRegenerateStrategy={sw.handleRegenerateStrategy}
              reportText={sw.reportText}
              onAcknowledgeReport={sw.handleAcknowledgeReport}
              securityFindings={sw.securityFindings}
              onApproveFindings={sw.handleApproveWizardFindings}
              pendingPlanConfig={pendingPlanConfig}
              onPlanApprove={handlePlanApprove}
              onPlanReject={handlePlanReject}
            />
        </div>
      )}

      {/* Toast notifications (per-tab) */}
      <ToastContainer messages={toasts} onDismiss={dismissToast} />
    </div>
  );
}

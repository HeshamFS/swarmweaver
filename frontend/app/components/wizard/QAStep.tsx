"use client";

import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { fetchQAQuestions, type QAQuestion, type QAResponse } from "../../utils/qaQuestions";

interface QAStepProps {
  mode: string;
  taskInput: string;
  projectDir: string;
  onComplete: (answers: Record<string, string>) => void;
  onSkip: () => void;
}

type Phase = "loading" | "questions" | "summary" | "error";

function getLoadingMessages(mode: string): string[] {
  switch (mode) {
    case "greenfield":
      return [
        "Analyzing your request...",
        "Understanding project requirements...",
        "Evaluating architecture options...",
        "Mapping technology choices...",
        "Considering deployment targets...",
        "Reviewing framework compatibility...",
        "Assessing project complexity...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    case "feature":
      return [
        "Analyzing your request...",
        "Reviewing feature scope...",
        "Considering integration points...",
        "Evaluating implementation approaches...",
        "Checking for edge cases...",
        "Mapping component dependencies...",
        "Assessing testing strategy...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    case "security":
      return [
        "Analyzing your request...",
        "Reviewing security scope...",
        "Identifying threat vectors...",
        "Mapping attack surfaces...",
        "Evaluating compliance requirements...",
        "Checking common vulnerability patterns...",
        "Assessing risk levels...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    case "refactor":
      return [
        "Analyzing your request...",
        "Assessing migration complexity...",
        "Evaluating refactoring strategies...",
        "Identifying breaking changes...",
        "Reviewing dependency impacts...",
        "Mapping module boundaries...",
        "Planning incremental steps...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    case "fix":
      return [
        "Analyzing your request...",
        "Reviewing bug description...",
        "Considering root causes...",
        "Identifying reproduction steps...",
        "Mapping affected components...",
        "Evaluating fix approaches...",
        "Planning investigation steps...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    case "evolve":
      return [
        "Analyzing your request...",
        "Evaluating improvement areas...",
        "Assessing current quality...",
        "Identifying optimization targets...",
        "Reviewing test coverage...",
        "Mapping performance bottlenecks...",
        "Prioritizing enhancements...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
    default:
      return [
        "Analyzing your request...",
        "Understanding requirements...",
        "Evaluating options...",
        "Identifying key decisions...",
        "Preparing clarifying questions...",
        "Almost ready...",
      ];
  }
}

export default function QAStep({ mode, taskInput, projectDir, onComplete, onSkip }: QAStepProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [questions, setQuestions] = useState<QAQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [otherActive, setOtherActive] = useState<Record<number, boolean>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});
  const [errorMessage, setErrorMessage] = useState("");
  const [skipToast, setSkipToast] = useState("");
  const [loadingStep, setLoadingStep] = useState(0);
  const advanceTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchedRef = useRef(false);
  const otherInputRef = useRef<HTMLInputElement>(null);
  const loadingMessages = useRef(getLoadingMessages(mode)).current;

  // Advance loading messages every 2.5s — stop at the last one (no looping)
  useEffect(() => {
    if (phase !== "loading") return;
    const interval = setInterval(() => {
      setLoadingStep((s) => {
        if (s >= loadingMessages.length - 1) {
          clearInterval(interval);
          return s;
        }
        return s + 1;
      });
    }, 4000);
    return () => clearInterval(interval);
  }, [phase, loadingMessages.length]);

  useEffect(() => {
    // Guard against React Strict Mode double-invocation.
    // fetchedRef persists across unmount/remount so only the first
    // mount fires the fetch. No AbortController or cancelled flag —
    // those get tripped by Strict Mode cleanup and discard valid responses.
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    (async () => {
      setPhase("loading");
      try {
        const data: QAResponse = await fetchQAQuestions(mode, taskInput, projectDir);

        if (data.skip_reason) {
          setSkipToast(data.skip_reason);
          setTimeout(() => onSkip(), 1200);
          return;
        }

        if (!data.questions || data.questions.length === 0) {
          onSkip();
          return;
        }

        setQuestions(data.questions);
        setPhase("questions");
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Failed to generate questions");
        setPhase("error");
      }
    })();

    return () => {
      if (advanceTimeout.current) clearTimeout(advanceTimeout.current);
    };
  }, [mode, taskInput, projectDir, onSkip]);

  const handleSelect = (questionText: string, optionLabel: string) => {
    const next = { ...answers, [questionText]: optionLabel };
    setAnswers(next);

    // Clear "Other" state for this question since a predefined option was picked
    setOtherActive((prev) => ({ ...prev, [currentIndex]: false }));
    setOtherText((prev) => ({ ...prev, [currentIndex]: "" }));

    if (advanceTimeout.current) clearTimeout(advanceTimeout.current);

    advanceTimeout.current = setTimeout(() => {
      if (currentIndex < questions.length - 1) {
        setCurrentIndex((i) => i + 1);
      } else {
        setPhase("summary");
      }
    }, 300);
  };

  const handleOtherToggle = () => {
    setOtherActive((prev) => ({ ...prev, [currentIndex]: true }));
    // Clear any predefined selection for this question
    const q = questions[currentIndex];
    if (q) {
      const next = { ...answers };
      delete next[q.question];
      setAnswers(next);
    }
    // Focus the input after render
    setTimeout(() => otherInputRef.current?.focus(), 50);
  };

  const handleOtherSubmit = () => {
    const text = (otherText[currentIndex] || "").trim();
    if (!text) return;

    const q = questions[currentIndex];
    if (!q) return;

    // Store the user's custom text as the answer (not "Other")
    const next = { ...answers, [q.question]: text };
    setAnswers(next);

    if (advanceTimeout.current) clearTimeout(advanceTimeout.current);

    advanceTimeout.current = setTimeout(() => {
      if (currentIndex < questions.length - 1) {
        setCurrentIndex((i) => i + 1);
        // Reset "Other" state for next question
        setOtherActive((prev) => ({ ...prev, [currentIndex]: false }));
      } else {
        setPhase("summary");
      }
    }, 300);
  };

  const handleBack = () => {
    if (currentIndex > 0) {
      setCurrentIndex((i) => i - 1);
    }
  };

  const handleGoBackFromSummary = () => {
    setCurrentIndex(questions.length - 1);
    setPhase("questions");
  };

  const handleSkipRemaining = () => {
    setPhase("summary");
  };

  // Auto-skip toast overlay
  if (skipToast) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex items-center gap-3 px-6 py-4 rounded-2xl bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)] shadow-lg"
        >
          <svg className="w-5 h-5 text-[var(--color-success)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-[var(--color-text-secondary)] text-sm">{skipToast}</span>
        </motion.div>
      </div>
    );
  }

  // Loading state
  if (phase === "loading") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-6">
        <div className="relative w-10 h-10">
          <div className="absolute inset-0 rounded-full border-2 border-[var(--color-border-subtle)]" />
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-[var(--color-accent)] animate-spin" />
        </div>
        {/* Step progress dots */}
        <div className="flex gap-1.5 w-48">
          {loadingMessages.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-all duration-700 ${
                i < loadingStep ? "bg-[var(--color-accent)]"
                : i === loadingStep ? "bg-[var(--color-accent)]/60 animate-pulse"
                : "bg-[var(--color-surface-raised)]"
              }`}
            />
          ))}
        </div>
        {/* Rotating status message */}
        <p
          key={loadingStep}
          className="text-sm text-[var(--color-text-muted)] animate-[fadeIn_0.4s_ease-out]"
        >
          {loadingMessages[loadingStep]}
        </p>
      </div>
    );
  }

  // Error state
  if (phase === "error") {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <div className="w-12 h-12 rounded-full bg-[var(--color-error)]/10 flex items-center justify-center">
          <svg className="w-6 h-6 text-[var(--color-error)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        <p className="text-sm text-[var(--color-text-secondary)] max-w-md text-center">{errorMessage}</p>
        <button
          onClick={onSkip}
          className="px-5 py-2.5 rounded-xl text-sm font-medium bg-[var(--color-surface-raised)] border border-[var(--color-border-default)] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-overlay)] transition-colors"
        >
          Skip and Continue
        </button>
      </div>
    );
  }

  // Summary state
  if (phase === "summary") {
    return (
      <div className="max-w-2xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold text-[var(--color-text-primary)] mb-1">Review Your Preferences</h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            {Object.keys(answers).length} of {questions.length} questions answered
          </p>
        </div>

        {/* Q&A pairs */}
        <div className="space-y-3 mb-8">
          {questions.map((q, i) => {
            const answer = answers[q.question];
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-start gap-3 px-4 py-3 rounded-xl bg-[var(--color-surface-raised)] border border-[var(--color-border-subtle)]"
              >
                <span className="mt-0.5 w-5 h-5 rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)] flex items-center justify-center text-xs font-semibold shrink-0">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[var(--color-accent)] truncate">{q.question}</p>
                  <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
                    {answer || <span className="italic text-[var(--color-text-muted)]">Skipped</span>}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleGoBackFromSummary}
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            Go Back
          </button>
          <button
            onClick={() => onComplete(answers)}
            className="px-6 py-2.5 rounded-xl text-sm font-semibold bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] transition-colors shadow-[0_0_20px_var(--color-accent-glow)]"
          >
            Start Agent
          </button>
        </div>
      </div>
    );
  }

  // Questions state
  const question = questions[currentIndex];

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      {/* Breadcrumb + Skip */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-[var(--color-text-muted)]">Setup</span>
          <svg className="w-3.5 h-3.5 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-[var(--color-text-primary)] font-medium">
            Question {currentIndex + 1} of {questions.length}
          </span>
        </div>
        <button
          onClick={onSkip}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors px-3 py-1 rounded-lg hover:bg-[var(--color-surface-raised)]"
        >
          Skip
        </button>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1 rounded-full bg-[var(--color-surface-raised)] mb-8 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-[var(--color-accent)]"
          initial={false}
          animate={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        />
      </div>

      {/* Question */}
      <AnimatePresence mode="wait">
        <motion.div
          key={currentIndex}
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -30 }}
          transition={{ duration: 0.25 }}
        >
          {/* Question heading */}
          <h3 className="text-lg font-semibold text-[var(--color-accent)] mb-2">
            {question.question}
          </h3>
          {question.context && (
            <p className="text-sm text-[var(--color-text-muted)] mb-6">{question.context}</p>
          )}

          {/* Options */}
          <div className="space-y-3">
            {question.options.map((opt, optIdx) => {
              const isSelected = answers[question.question] === opt.label && !otherActive[currentIndex];
              return (
                <motion.button
                  key={optIdx}
                  onClick={() => handleSelect(question.question, opt.label)}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                  className={`w-full text-left px-4 py-3.5 rounded-xl border transition-all duration-200 flex items-start gap-3 ${
                    isSelected
                      ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5 shadow-[0_0_12px_var(--color-accent-glow)]"
                      : "border-[var(--color-border-subtle)] bg-[var(--color-surface-raised)] hover:border-[var(--color-border-default)] hover:bg-[var(--color-surface-overlay)]"
                  }`}
                >
                  <span
                    className={`mt-0.5 w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 transition-colors ${
                      isSelected
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] border border-[var(--color-border-default)]"
                    }`}
                  >
                    {optIdx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm font-medium ${isSelected ? "text-[var(--color-accent)]" : "text-[var(--color-text-primary)]"}`}>
                      {opt.label}
                    </p>
                    {opt.description && (
                      <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{opt.description}</p>
                    )}
                  </div>
                  {isSelected && (
                    <svg className="w-5 h-5 text-[var(--color-accent)] shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </motion.button>
              );
            })}

            {/* "Other" free-text option */}
            {otherActive[currentIndex] ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full px-4 py-3.5 rounded-xl border border-[var(--color-accent)] bg-[var(--color-accent)]/5 shadow-[0_0_12px_var(--color-accent-glow)]"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 bg-[var(--color-accent)] text-white">
                    ?
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-[var(--color-accent)] mb-2">Your answer</p>
                    <div className="flex gap-2">
                      <input
                        ref={otherInputRef}
                        type="text"
                        value={otherText[currentIndex] || ""}
                        onChange={(e) => setOtherText((prev) => ({ ...prev, [currentIndex]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === "Enter") handleOtherSubmit(); }}
                        placeholder="Type your own answer..."
                        className="flex-1 px-3 py-2 rounded-lg text-sm bg-[var(--color-surface-base)] border border-[var(--color-border-default)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)] transition-colors"
                      />
                      <button
                        onClick={handleOtherSubmit}
                        disabled={!(otherText[currentIndex] || "").trim()}
                        className="px-4 py-2 rounded-lg text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Submit
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            ) : (
              <motion.button
                onClick={handleOtherToggle}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                className="w-full text-left px-4 py-3.5 rounded-xl border border-dashed border-[var(--color-border-default)] bg-[var(--color-surface-raised)] hover:border-[var(--color-border-default)] hover:bg-[var(--color-surface-overlay)] transition-all duration-200 flex items-start gap-3"
              >
                <span className="mt-0.5 w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 bg-[var(--color-surface-overlay)] text-[var(--color-text-muted)] border border-[var(--color-border-default)]">
                  ?
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-[var(--color-text-secondary)]">Other</p>
                  <p className="text-xs text-[var(--color-text-muted)] mt-0.5">Type your own answer</p>
                </div>
              </motion.button>
            )}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Bottom navigation */}
      <div className="flex items-center justify-between mt-8 pt-6 border-t border-[var(--color-border-subtle)]">
        <button
          onClick={handleBack}
          disabled={currentIndex === 0}
          className={`text-sm transition-colors ${
            currentIndex === 0
              ? "text-[var(--color-text-muted)]/40 cursor-not-allowed"
              : "text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]"
          }`}
        >
          Previous
        </button>
        <button
          onClick={handleSkipRemaining}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
        >
          Skip remaining
        </button>
      </div>
    </div>
  );
}

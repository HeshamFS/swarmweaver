"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { BrainCog } from "lucide-react";
import { fetchQAQuestions, type QAQuestion, type QAResponse } from "../../../utils/qaQuestions";

interface QAInlineBlockProps {
  mode: string;
  taskInput: string;
  projectDir: string;
  onComplete: (answers: Record<string, string>) => void;
  onSkip: () => void;
  /** When provided, skip the POST fetch and use these questions directly */
  externalQuestions?: { question: string; context?: string; options: { label: string; description: string }[] }[];
}

type Phase = "loading" | "questions" | "summary" | "complete" | "error" | "skipped";

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

export default function QAInlineBlock({ mode, taskInput, projectDir, onComplete, onSkip, externalQuestions }: QAInlineBlockProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [questions, setQuestions] = useState<QAQuestion[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [otherActive, setOtherActive] = useState<Record<number, boolean>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});
  const [errorMessage, setErrorMessage] = useState("");
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
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    // If external questions provided (from wizard WS), use them directly — no POST
    if (externalQuestions && externalQuestions.length > 0) {
      setQuestions(externalQuestions.map(q => ({
        question: q.question,
        context: q.context,
        options: q.options,
      })));
      setPhase("questions");
      return;
    }

    // Legacy: fetch via POST (fallback when not using wizard WS)
    (async () => {
      setPhase("loading");
      try {
        const data: QAResponse = await fetchQAQuestions(mode, taskInput, projectDir);
        if (data.skip_reason || !data.questions || data.questions.length === 0) {
          setPhase("skipped");
          setTimeout(() => onSkip(), 800);
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
  }, [mode, taskInput, projectDir, onSkip, externalQuestions]);

  const handleSelect = useCallback((questionText: string, optionLabel: string) => {
    // Clear "Other" state since a predefined option was picked
    setOtherActive((prev) => ({ ...prev, [currentIndex]: false }));
    setOtherText((prev) => ({ ...prev, [currentIndex]: "" }));

    setAnswers((prev) => {
      const next = { ...prev, [questionText]: optionLabel };
      if (advanceTimeout.current) clearTimeout(advanceTimeout.current);
      advanceTimeout.current = setTimeout(() => {
        setCurrentIndex((i) => {
          if (i < questions.length - 1) return i + 1;
          setPhase("summary");
          return i;
        });
      }, 300);
      return next;
    });
  }, [questions.length, currentIndex]);

  const handleOtherToggle = useCallback(() => {
    setOtherActive((prev) => ({ ...prev, [currentIndex]: true }));
    const q = questions[currentIndex];
    if (q) {
      setAnswers((prev) => {
        const next = { ...prev };
        delete next[q.question];
        return next;
      });
    }
    setTimeout(() => otherInputRef.current?.focus(), 50);
  }, [currentIndex, questions]);

  const handleOtherSubmit = useCallback(() => {
    const text = (otherText[currentIndex] || "").trim();
    if (!text) return;
    const q = questions[currentIndex];
    if (!q) return;

    setAnswers((prev) => ({ ...prev, [q.question]: text }));

    if (advanceTimeout.current) clearTimeout(advanceTimeout.current);
    advanceTimeout.current = setTimeout(() => {
      setOtherActive((prev) => ({ ...prev, [currentIndex]: false }));
      setCurrentIndex((i) => {
        if (i < questions.length - 1) return i + 1;
        setPhase("summary");
        return i;
      });
    }, 300);
  }, [currentIndex, otherText, questions]);

  const handleProceed = useCallback(() => {
    setPhase("complete");
    onComplete(answers);
  }, [answers, onComplete]);

  if (phase === "loading") {
    return (
      <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
          <BrainCog className="w-3.5 h-3.5 text-[var(--color-accent)] animate-pulse shrink-0" />
          <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Setup</span>
          <span className="text-[#555] text-xs ml-auto">{"\u203A"} Thinking</span>
        </div>
        {/* Step progress dots */}
        <div className="px-4 pt-3">
          <div className="flex gap-1.5">
            {loadingMessages.map((_, i) => (
              <div
                key={i}
                className={`h-1 flex-1 rounded-full transition-all duration-700 ${
                  i < loadingStep ? "bg-[var(--color-accent)]"
                  : i === loadingStep ? "bg-[var(--color-accent)]/60 animate-pulse"
                  : "bg-[#222]"
                }`}
              />
            ))}
          </div>
        </div>
        {/* Rotating status message */}
        <div className="px-4 py-3 min-h-[36px] flex items-center">
          <span
            key={loadingStep}
            className="text-[#888] text-xs animate-[fadeIn_0.4s_ease-out]"
          >
            {loadingMessages[loadingStep]}
          </span>
        </div>
      </div>
    );
  }

  if (phase === "skipped") {
    return (
      <div className="border border-[#333] bg-[#121212] mb-3 font-mono p-4">
        <div className="flex items-center gap-3">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs">Setup skipped</span>
        </div>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="border border-[var(--color-error)] bg-[#121212] mb-3 font-mono p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-[var(--color-error)]">!</span>
            <span className="text-[var(--color-error)] text-xs">{errorMessage}</span>
          </div>
          <button
            onClick={onSkip}
            className="border border-[#333] px-3 py-1 text-[10px] text-[#888] hover:text-[#E0E0E0] hover:border-[#555] uppercase tracking-wider transition-colors"
          >
            Skip
          </button>
        </div>
      </div>
    );
  }

  if (phase === "complete") {
    return (
      <div className="border border-[#222] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
          <span className="text-[#555]">{"\u2713"}</span>
          <span className="text-[#555] text-xs font-bold uppercase tracking-wider">Setup Complete</span>
          <span className="text-[#555] text-xs ml-auto">{Object.keys(answers).length}/{questions.length} answered</span>
        </div>
        <div className="p-3 space-y-1">
          {questions.map((q, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <span className="text-[#555] shrink-0">Q{i + 1}:</span>
              <span className="text-[#888] truncate">{answers[q.question] || "Skipped"}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (phase === "summary") {
    return (
      <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
          <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
          <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Review Preferences</span>
          <span className="text-[#555] text-xs ml-auto">{Object.keys(answers).length}/{questions.length}</span>
        </div>
        <div className="p-3 space-y-2">
          {questions.map((q, i) => (
            <div key={i} className="flex items-start gap-3 px-2 py-1.5 border border-[#222] bg-[#0C0C0C]">
              <span className="text-[var(--color-accent)] text-xs shrink-0">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-[var(--color-accent)] text-xs truncate">{q.question}</div>
                <div className="text-[#888] text-xs mt-0.5">
                  {answers[q.question] || <span className="text-[#555] italic">Skipped</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-t border-[#222]">
          <button
            onClick={() => { setCurrentIndex(questions.length - 1); setPhase("questions"); }}
            className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono"
          >
            {"\u2190"} Go Back
          </button>
          <button
            onClick={handleProceed}
            className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
          >
            Continue {"\u2192"}
          </button>
        </div>
      </div>
    );
  }

  // Questions phase: show answered questions collapsed + current question active
  const question = questions[currentIndex];
  const answeredQuestions = questions.slice(0, currentIndex);
  const progress = `${currentIndex + 1}/${questions.length}`;

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Setup</span>
        <span className="text-[#555] text-xs">{"\u203A"} Question {progress}</span>
        <button
          onClick={onSkip}
          className="ml-auto text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors"
        >
          Skip All
        </button>
      </div>

      {/* Progress bar */}
      <div className="px-4 pt-2">
        <div className="flex gap-px">
          {questions.map((_, i) => (
            <div
              key={i}
              className={`h-0.5 flex-1 transition-colors ${
                i < currentIndex ? "bg-[var(--color-accent)]"
                : i === currentIndex ? "bg-[var(--color-accent)]/50"
                : "bg-[#222]"
              }`}
            />
          ))}
        </div>
      </div>

      {/* Previously answered (collapsed) */}
      {answeredQuestions.length > 0 && (
        <div className="px-4 pt-2 space-y-1">
          {answeredQuestions.map((q, i) => (
            <div key={i} className="flex items-center gap-2 text-xs text-[#555]">
              <span className="text-[#555]">{"\u2713"}</span>
              <span className="truncate">{q.question}</span>
              <span className="text-[#888] ml-auto shrink-0">{answers[q.question]}</span>
            </div>
          ))}
          <div className="h-px bg-[#222] my-1" />
        </div>
      )}

      {/* Current question */}
      <div className="p-4">
        <h4 className="text-[var(--color-accent)] text-sm font-bold mb-1">{question.question}</h4>
        {question.context && (
          <p className="text-[#555] text-xs mb-3">{question.context}</p>
        )}
        <div className="space-y-1.5">
          {question.options.map((opt, optIdx) => {
            const isSelected = answers[question.question] === opt.label && !otherActive[currentIndex];
            return (
              <button
                key={optIdx}
                onClick={() => handleSelect(question.question, opt.label)}
                className={`w-full text-left px-3 py-2 border transition-colors flex items-start gap-3 ${
                  isSelected
                    ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5"
                    : "border-[#222] bg-[#0C0C0C] hover:border-[#444]"
                }`}
              >
                <span className={`text-xs font-bold shrink-0 w-5 text-center ${isSelected ? "text-[var(--color-accent)]" : "text-[#555]"}`}>
                  {isSelected ? "\u2713" : String(optIdx + 1)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className={`text-xs font-bold ${isSelected ? "text-[var(--color-accent)]" : "text-[#E0E0E0]"}`}>
                    {opt.label}
                  </div>
                  {opt.description && (
                    <div className="text-[#555] text-[10px] mt-0.5">{opt.description}</div>
                  )}
                </div>
              </button>
            );
          })}

          {/* "Other" free-text option */}
          {otherActive[currentIndex] ? (
            <div className="w-full px-3 py-2 border border-[var(--color-accent)] bg-[var(--color-accent)]/5">
              <div className="flex items-start gap-3">
                <span className="text-xs font-bold shrink-0 w-5 text-center text-[var(--color-accent)]">?</span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-bold text-[var(--color-accent)] mb-1.5">Your answer</div>
                  <div className="flex gap-2">
                    <input
                      ref={otherInputRef}
                      type="text"
                      value={otherText[currentIndex] || ""}
                      onChange={(e) => setOtherText((prev) => ({ ...prev, [currentIndex]: e.target.value }))}
                      onKeyDown={(e) => { if (e.key === "Enter") handleOtherSubmit(); }}
                      placeholder="Type your own answer..."
                      className="flex-1 px-2 py-1.5 text-xs bg-[#0C0C0C] border border-[#333] text-[#E0E0E0] placeholder:text-[#555] focus:outline-none focus:border-[var(--color-accent)] transition-colors font-mono"
                    />
                    <button
                      onClick={handleOtherSubmit}
                      disabled={!(otherText[currentIndex] || "").trim()}
                      className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider bg-[var(--color-accent)] text-[#0C0C0C] hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-mono"
                    >
                      Submit
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <button
              onClick={handleOtherToggle}
              className="w-full text-left px-3 py-2 border border-dashed border-[#333] bg-[#0C0C0C] hover:border-[#444] transition-colors flex items-start gap-3"
            >
              <span className="text-xs font-bold shrink-0 w-5 text-center text-[#555]">?</span>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-bold text-[#888]">Other</div>
                <div className="text-[#555] text-[10px] mt-0.5">Type your own answer</div>
              </div>
            </button>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-[#222]">
        <button
          onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
          disabled={currentIndex === 0}
          className={`text-[10px] uppercase tracking-wider transition-colors font-mono ${
            currentIndex === 0 ? "text-[#333] cursor-not-allowed" : "text-[#555] hover:text-[#888]"
          }`}
        >
          {"\u2190"} Previous
        </button>
        <button
          onClick={() => setPhase("summary")}
          className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono"
        >
          Skip remaining
        </button>
      </div>
    </div>
  );
}

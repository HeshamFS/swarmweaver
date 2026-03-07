"use client";

import { useState, useCallback, useRef } from "react";
import type { ArchitectQuestion } from "../../hooks/useArchitectStream";

interface ArchitectQABlockProps {
  questions: ArchitectQuestion[];
  onSubmit: (answers: Record<string, string>) => void;
}

export default function ArchitectQABlock({ questions, onSubmit }: ArchitectQABlockProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [otherActive, setOtherActive] = useState<Record<number, boolean>>({});
  const [otherText, setOtherText] = useState<Record<number, string>>({});
  const [showSummary, setShowSummary] = useState(false);
  const advanceTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const otherInputRef = useRef<HTMLInputElement>(null);

  const handleSelect = useCallback((questionText: string, optionLabel: string) => {
    setOtherActive((prev) => ({ ...prev, [currentIndex]: false }));
    setOtherText((prev) => ({ ...prev, [currentIndex]: "" }));

    setAnswers((prev) => {
      const next = { ...prev, [questionText]: optionLabel };
      if (advanceTimeout.current) clearTimeout(advanceTimeout.current);
      advanceTimeout.current = setTimeout(() => {
        setCurrentIndex((i) => {
          if (i < questions.length - 1) return i + 1;
          setShowSummary(true);
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
        setShowSummary(true);
        return i;
      });
    }, 300);
  }, [currentIndex, otherText, questions]);

  const handleProceed = useCallback(() => {
    onSubmit(answers);
  }, [answers, onSubmit]);

  if (questions.length === 0) return null;

  // Summary view
  if (showSummary) {
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
            onClick={() => { setCurrentIndex(questions.length - 1); setShowSummary(false); }}
            className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono"
          >
            {"\u2190"} Go Back
          </button>
          <button
            onClick={handleProceed}
            className="bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-[#0C0C0C] px-6 py-1.5 font-bold text-xs uppercase tracking-wider transition-colors font-mono"
          >
            Generate Spec {"\u2192"}
          </button>
        </div>
      </div>
    );
  }

  // Question view
  const question = questions[currentIndex];
  const answeredQuestions = questions.slice(0, currentIndex);
  const progress = `${currentIndex + 1}/${questions.length}`;

  return (
    <div className="border border-[#333] bg-[#121212] mb-3 font-mono">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-[#222] bg-[#0C0C0C]">
        <span className="text-[var(--color-accent)]">{"\u25A0"}</span>
        <span className="text-[#E0E0E0] text-xs font-bold uppercase tracking-wider">Architect</span>
        <span className="text-[#555] text-xs">{"\u203A"} Question {progress}</span>
        <button
          onClick={handleProceed}
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
              <span>{"\u2713"}</span>
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
          onClick={() => setShowSummary(true)}
          className="text-[10px] text-[#555] hover:text-[#888] uppercase tracking-wider transition-colors font-mono"
        >
          Skip remaining
        </button>
      </div>
    </div>
  );
}

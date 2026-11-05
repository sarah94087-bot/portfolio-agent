"use client";

import { forwardRef, useId } from "react";

import { Button } from "@/components/ui/Button";
import { BackIcon, DocumentIcon, SendIcon } from "@/components/ui/icons";

export type ComposerMode = "question" | "job";

export const LIMITS: Record<ComposerMode, number> = { question: 1000, job: 8000 };

// The counter appears from 92% of the limit (the design's "near-limit" state).
const NEAR_LIMIT = 0.92;

export type ComposerStrings = {
  questionLabel: string;
  questionPlaceholder: string;
  jobLabel: string;
  jobPlaceholder: string;
  pasteJob: string;
  backToQuestion: string;
  send: string;
  counter: string; // "{n} of {max} characters"
  overLimit: string;
};

type Props = {
  lang: string;
  t: ComposerStrings;
  mode: ComposerMode;
  value: string;
  onModeChange: (mode: ComposerMode) => void;
  onChange: (value: string) => void;
  onSubmit?: (value: string, mode: ComposerMode) => void;
  disabled?: boolean;
};

export const Composer = forwardRef<HTMLTextAreaElement, Props>(function Composer(
  { lang, t, mode, value, onModeChange, onChange, onSubmit, disabled },
  ref,
) {
  const id = useId();
  const limit = LIMITS[mode];
  const length = value.length;
  const near = length >= limit * NEAR_LIMIT;
  const over = length > limit;
  const canSend = !disabled && value.trim().length > 0 && !over;
  const fmt = (n: number) => n.toLocaleString(lang);

  function submit() {
    if (canSend) onSubmit?.(value.trim(), mode);
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="flex flex-col gap-2.5 rounded-lg border-[1.5px] border-border-strong bg-surface-raised px-3.5 pb-3 pt-3 md:px-4 md:pt-3.5"
    >
      <label htmlFor={id} className="sr-only">
        {mode === "job" ? t.jobLabel : t.questionLabel}
      </label>
      <textarea
        ref={ref}
        id={id}
        dir="auto"
        rows={mode === "job" ? 6 : 2}
        value={value}
        disabled={disabled}
        placeholder={mode === "job" ? t.jobPlaceholder : t.questionPlaceholder}
        aria-describedby={near ? `${id}-count` : undefined}
        aria-invalid={over || undefined}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // A question sends on Enter. A job posting is multi-line, so Enter stays a newline there.
          if (mode === "question" && e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        className="w-full resize-none bg-transparent text-[16px] leading-[1.7] text-text outline-offset-[6px] placeholder:text-text-muted md:text-[19px]"
      />
      <div className="flex items-center gap-3">
        {mode === "question" ? (
          <Button variant="ghost" className="text-[14px]" onClick={() => onModeChange("job")}>
            <DocumentIcon />
            {t.pasteJob}
          </Button>
        ) : (
          <Button variant="ghost" className="text-[14px]" onClick={() => onModeChange("question")}>
            <BackIcon />
            {t.backToQuestion}
          </Button>
        )}

        {near && (
          <span id={`${id}-count`} className={`mono ms-auto text-[12.5px] ${over ? "font-medium text-text" : "text-text-muted"}`}>
            {t.counter.replace("{n}", fmt(length)).replace("{max}", fmt(limit))}
          </span>
        )}
        {/* Announced once when the text crosses the limit, not on every keystroke. */}
        <span role="status" className="sr-only">
          {over ? t.overLimit : ""}
        </span>

        <Button type="submit" variant="icon" aria-label={t.send} disabled={!canSend} className={near ? "" : "ms-auto"}>
          <SendIcon />
        </Button>
      </div>
    </form>
  );
});

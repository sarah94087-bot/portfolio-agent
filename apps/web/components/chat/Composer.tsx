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
  jobMode: string;
  jobHint: string;
  runMatch: string;
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
  busy?: boolean; // an answer is streaming: typing goes on, sending waits
  // In a conversation a question gets one line, as on board A-S2, so the composer does not cover
  // the answers on a short screen. A job posting keeps the full layout.
  compact?: boolean;
};

export const Composer = forwardRef<HTMLTextAreaElement, Props>(function Composer(
  { lang, t, mode, value, onModeChange, onChange, onSubmit, disabled, busy, compact },
  ref,
) {
  const id = useId();
  const limit = LIMITS[mode];
  const length = value.length;
  const near = length >= limit * NEAR_LIMIT;
  const over = length > limit;
  const canSend = !disabled && !busy && value.trim().length > 0 && !over;
  const fmt = (n: number) => n.toLocaleString(lang);

  function submit() {
    if (canSend) onSubmit?.(value.trim(), mode);
  }

  const keyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // A question sends on Enter. A job posting is multi-line, so Enter stays a newline there.
    if (mode === "question" && e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  if (compact && mode === "question") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex items-end gap-3 rounded-lg border-[1.5px] border-border-strong bg-surface-raised p-2.5 md:p-3"
      >
        <Button variant="ghost" className="size-10 flex-none p-0!" aria-label={t.pasteJob} onClick={() => onModeChange("job")}>
          <DocumentIcon />
        </Button>
        <label htmlFor={id} className="sr-only">
          {t.questionLabel}
        </label>
        <textarea
          ref={ref}
          id={id}
          dir="auto"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={t.questionPlaceholder}
          aria-describedby={near ? `${id}-count` : undefined}
          aria-invalid={over || undefined}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={keyDown}
          className="max-h-40 min-h-10 flex-1 resize-none self-center bg-transparent py-1.5 text-[16px] leading-[1.6] text-text outline-offset-[6px] [field-sizing:content] placeholder:text-text-muted md:text-[18px]"
        />
        {near && (
          <span id={`${id}-count`} className={`mono self-center text-[12.5px] ${over ? "font-medium text-text" : "text-text-muted"}`}>
            {t.counter.replace("{n}", fmt(length)).replace("{max}", fmt(limit))}
          </span>
        )}
        <span role="status" className="sr-only">
          {over ? t.overLimit : ""}
        </span>
        <Button type="submit" variant="icon" aria-label={t.send} disabled={!canSend} className="flex-none">
          <SendIcon />
        </Button>
      </form>
    );
  }

  // Board S4-Report, "job-posting mode": the limit is always in view, and the hint says that the
  // text is data before anything is pasted.
  if (mode === "job") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex flex-col gap-2.5 rounded-[14px] border-[1.5px] border-accent bg-surface-raised px-3.5 py-3 md:px-4 md:py-3.5"
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="inline-flex items-center rounded-full bg-accent px-[9px] py-px text-[12px] font-bold text-on-accent">{t.jobMode}</span>
          <span id={`${id}-hint`} className="text-[13px] text-text-muted">{t.jobHint}</span>
          <span className={`mono ms-auto text-[12.5px] ${over ? "font-medium text-text" : "text-text-muted"}`}>
            {fmt(length)} / {fmt(limit)}
          </span>
        </div>
        <label htmlFor={id} className="sr-only">{t.jobLabel}</label>
        <textarea
          ref={ref}
          id={id}
          dir="auto"
          rows={5}
          value={value}
          disabled={disabled}
          placeholder={t.jobPlaceholder}
          aria-describedby={`${id}-hint`}
          aria-invalid={over || undefined}
          onChange={(e) => onChange(e.target.value)}
          className="w-full resize-none rounded-[10px] border border-border-input bg-surface px-3 py-2.5 text-[16px] leading-[1.6] text-text placeholder:text-text-muted md:text-[15px]"
        />
        <span role="status" className="sr-only">{over ? t.overLimit : ""}</span>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button type="submit" className="min-h-10" disabled={!canSend}>{t.runMatch}</Button>
          <Button variant="ghost" className="min-h-10" onClick={() => onModeChange("question")}>
            <BackIcon />
            {t.backToQuestion}
          </Button>
        </div>
      </form>
    );
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
        {t.questionLabel}
      </label>
      <textarea
        ref={ref}
        id={id}
        dir="auto"
        rows={2}
        value={value}
        disabled={disabled}
        placeholder={t.questionPlaceholder}
        aria-describedby={near ? `${id}-count` : undefined}
        aria-invalid={over || undefined}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={keyDown}
        className="w-full resize-none bg-transparent text-[16px] leading-[1.7] text-text outline-offset-[6px] placeholder:text-text-muted md:text-[19px]"
      />
      <div className="flex items-center gap-3">
        <Button variant="ghost" className="text-[14px]" onClick={() => onModeChange("job")}>
          <DocumentIcon />
          {t.pasteJob}
        </Button>

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

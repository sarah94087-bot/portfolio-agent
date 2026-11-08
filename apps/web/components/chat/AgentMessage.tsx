"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { CheckIcon, ChevronIcon, RetryIcon, SpinnerIcon, SwapIcon } from "@/components/ui/icons";
import { blocks, spoken } from "@/lib/answer";
import type { Source, Turn } from "@/lib/chat";
import { jobStages, type Stage } from "@/lib/job";
import { Feedback } from "./Feedback";
import { JobReport } from "./JobReport";
import { Bidi, Cite, fill, Inlines, plural, sectionLabel, SourcePopover, tone, type ChatStrings } from "./sources";

export type { ChatStrings };

function JobProgress({ stages, t, lang }: { stages: Stage[]; t: ChatStrings; lang: string }) {
  const note = (s: Stage) => {
    if (s.key === "evidence" && s.done !== undefined && s.total !== undefined) {
      return `${s.done.toLocaleString(lang)} / ${s.total.toLocaleString(lang)}`;
    }
    return s.key === "extract" && s.total !== undefined ? plural(lang, t.job.found, s.total) : "";
  };
  return (
    <div aria-hidden="true" className="rounded-[14px] border border-border bg-surface-raised px-4 py-3.5">
      <ol className="m-0 flex list-none flex-col gap-2.5 p-0 text-[15px]">
        {stages.map((s) => (
          <li key={s.key} className={`flex items-center gap-3 ${s.state === "wait" ? "text-text-muted" : "text-text"} ${s.state === "run" ? "font-bold" : ""}`}>
            <span className="flex size-[22px] flex-none items-center justify-center text-accent">
              {s.state === "done" && <CheckIcon size={18} />}
              {s.state === "run" && <SpinnerIcon size={18} />}
              {s.state === "wait" && <span className="size-2.5 rounded-full border-[1.5px] border-text-muted" />}
            </span>
            {t.job.stages[s.key]}
            <span className="mono ms-auto text-[12.5px] font-normal text-text-muted">{note(s)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function status(turn: Turn, t: ChatStrings): string | null {
  if (turn.status === "sending") return t.thinking;
  if (turn.status !== "streaming") return null;
  if (turn.job && !turn.report) {
    const run = jobStages(turn.steps).find((s) => s.state === "run");
    return run ? t.job.stages[run.key] : t.thinking;
  }
  const last = turn.steps.at(-1);
  if (last?.status === "restart") return t.restarting;
  if (last?.kind === "tool_call" && last.status === "start") {
    return last.name === "get_project" ? t.opening : t.searching;
  }
  return turn.parts.length === 0 ? t.thinking : null;
}

function errorText(turn: Turn, t: ChatStrings): string {
  const e = turn.error!;
  switch (e.code) {
    case "disconnected":
      return t.errors.disconnected;
    case "unreachable":
      return t.errors.unreachable;
    case "rate_limited":
      if (e.limit === "minute") return fill(t.errors.minute, e.retryAfter ?? 60);
      if (e.limit === "conversation") return t.errors.conversation;
      return t.errors.day;
    case "quota_exhausted":
    case "provider_unavailable":
      return t.errors.unavailable;
    case "input_too_long":
      return turn.job ? t.job.tooLong : t.errors.tooLong;
    default:
      return t.errors.internal;
  }
}

type TraceLineProps = {
  turn: Turn;
  lang: string;
  t: ChatStrings;
  open: boolean;
  onOpen: (from: HTMLButtonElement) => void;
};

function TraceLine({ turn, lang, t, open, onOpen }: TraceLineProps) {
  const u = turn.usage ?? {};
  const num = (k: string) => (typeof u[k] === "number" ? (u[k] as number) : 0);
  const tokens = num("input_tokens") + num("output_tokens");
  const model = typeof u.model === "string" ? u.model.split("/").at(-1) : null;
  const steps = turn.steps.filter((s) => s.kind !== "guard").length;
  const items = [
    plural(lang, t.steps, steps),
    fill(t.seconds, (num("total_ms") / 1000).toLocaleString(lang, { maximumFractionDigits: 1 })),
    ...(tokens ? [fill(t.tokens, tokens.toLocaleString(lang))] : []),
    ...(model ? [model] : []),
    plural(lang, t.sourcesCount, turn.sources.length),
  ];
  return (
    <div className="mono flex flex-wrap items-center gap-x-2.5 gap-y-1 border-y border-border py-2.5 text-[12px] text-text-muted md:text-small">
      {items.map((item, i) => (
        <span key={i} className="contents">
          {i > 0 && <span aria-hidden="true">·</span>}
          <span>{item}</span>
        </span>
      ))}
      {u.fallback === true && (
        <Tag tone="fallback">
          <SwapIcon />
          <span className="font-sans">{t.fallback}</span>
        </Tag>
      )}
      {(u.cached === true || u.replay === true) && (
        <Tag tone="removed">
          <span className="font-sans">{t.cached}</span>
        </Tag>
      )}
      {typeof u.dropped === "number" && u.dropped > 0 && (
        <Tag tone="removed">
          <span className="font-sans">{t.trace.removedTag}</span>
        </Tag>
      )}
      <button
        type="button"
        aria-expanded={open}
        onClick={(e) => onOpen(e.currentTarget)}
        className={`ms-auto flex items-center gap-1.5 rounded-[6px] px-2.5 py-1 font-sans text-[13px] font-bold text-accent hover:bg-surface-sunken ${open ? "bg-surface-sunken" : ""}`}
      >
        {t.trace.details}
        <ChevronIcon size={12} className={open ? "rotate-180" : ""} />
      </button>
    </div>
  );
}

type Props = {
  turn: Turn;
  lang: string;
  t: ChatStrings;
  agentName: string;
  agentLine: string; // the first line of a printed report
  onRetry: () => void;
  traceOpen: boolean;
  // S3 opens from the details button, or at a chunk's row from a source
  onTrace: (from: HTMLElement, chunkId?: string) => void;
};

export function AgentMessage({ turn, lang, t, agentName, agentLine, onRetry, traceOpen, onTrace }: Props) {
  const [open, setOpen] = useState<{ n: number; top: number; from: HTMLButtonElement } | null>(null);
  const [showSources, setShowSources] = useState(false);
  const [quiet, setQuiet] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  const streaming = turn.status === "sending" || turn.status === "streaming";

  // One announcement per answer, when it ends (US-11.3): the streamed text is aria-hidden until
  // then, and the status region holds only the tool status. The announcement is cleared after
  // a few seconds, so reading the page later does not find the answer twice.
  const done = turn.status === "done";
  useEffect(() => {
    if (!done) return;
    const id = setTimeout(() => setQuiet(true), 4000);
    return () => clearTimeout(id);
  }, [done]);
  const announce = done && !quiet
    ? turn.report ? `${t.job.level[turn.report.overall]}. ${turn.report.summary}` : spoken(turn.parts)
    : "";

  const byIndex = new Map<number, Source>();
  for (const p of turn.parts) {
    if (p.kind !== "cite") continue;
    const s = turn.sources.find((x) => x.chunkId === p.chunkId);
    if (s) byIndex.set(p.index, s);
  }
  const numbered = [...byIndex.entries()].sort((a, b) => a[0] - b[0]); // the server sends cited ones only

  function openCite(n: number, el: HTMLButtonElement) {
    if (open?.n === n) return close();
    const box = body.current!.getBoundingClientRect();
    const at = el.getBoundingClientRect();
    setOpen({ n, top: at.bottom - box.top + 8, from: el });
  }
  function close() {
    open?.from.focus();
    setOpen(null);
  }

  const cite = (n: number, key: number) => (
    <Cite key={key} n={n} label={fill(t.source, n)} open={open?.n === n} ready={byIndex.has(n)} onOpen={openCite} />
  );
  const shown = blocks(turn.parts);
  const now = status(turn, t);

  return (
    <article aria-label={t.answerLabel} className="flex flex-col gap-3.5">
      <div className="flex items-center gap-2.5 text-[14px] font-bold text-text-muted">
        <span aria-hidden="true" className="size-2 rounded-[2px] bg-accent" />
        {agentName}
      </div>

      <div role="status" className={now && !(turn.job && turn.status === "streaming") ? "flex items-center gap-2.5 text-ui text-text-muted" : "sr-only"}>
        {now ? (
          turn.job && !turn.report && turn.status !== "sending" ? (
            <span className="sr-only">{now}</span>
          ) : (
            <>
              <SpinnerIcon />
              {now}
            </>
          )
        ) : (
          announce
        )}
      </div>

      {turn.job && streaming && turn.steps.length > 0 && !turn.report && (
        <JobProgress stages={jobStages(turn.steps)} t={t} lang={lang} />
      )}

      {turn.report && (
        <JobReport
          report={turn.report}
          markdown={turn.markdown}
          sources={turn.sources}
          lang={lang}
          t={t}
          agentLine={agentLine}
          onFound={turn.steps.some((s) => s.name === "search_portfolio") ? (from, chunkId) => onTrace(from, chunkId) : undefined}
        />
      )}

      {shown.length > 0 && (
        <div ref={body} className="relative">
          <div dir="auto" aria-hidden={streaming || undefined} className="text-body">
          {shown.map((b, i) => {
            const inner = <Inlines inlines={b.inlines} cite={cite} />;
            const last = i === shown.length - 1 && turn.status === "streaming";
            const caret = last && (
              <span aria-hidden="true" className="ms-0.5 inline-block h-[1.1em] w-0.5 bg-accent align-[-3px] motion-safe:animate-pulse" />
            );
            if (b.kind === "li")
              return (
                <p key={i} className="relative mb-2 ps-5 before:absolute before:start-1 before:content-['•']">
                  {inner}
                  {caret}
                </p>
              );
            if (b.kind === "h")
              return (
                <p key={i} className="mb-2 mt-4 font-extrabold first:mt-0">
                  {inner}
                  {caret}
                </p>
              );
            return (
              <p key={i} className="mb-3 last:mb-0">
                {inner}
                {caret}
              </p>
            );
          })}
          </div>
          {open && byIndex.get(open.n) && (
            <SourcePopover
              n={open.n}
              source={byIndex.get(open.n)!}
              top={open.top}
              t={t}
              onClose={close}
              onFound={turn.steps.some((s) => s.name === "search_portfolio") ? () => {
                const from = open.from;
                setOpen(null);
                onTrace(from, byIndex.get(open.n)!.chunkId);
              } : undefined}
            />
          )}
        </div>
      )}

      {turn.status === "error" && turn.error && (
        <div className="flex flex-col items-start gap-3 rounded-md bg-danger-bg px-4 py-3 text-ui text-danger">
          <p dir="auto" className="m-0">{errorText(turn, t)}</p>
          {turn.error.retryable && (
            <Button variant="secondary" onClick={onRetry} className="text-[14px]">
              <RetryIcon />
              {t.retry}
            </Button>
          )}
        </div>
      )}

      {turn.status === "done" && numbered.length > 0 && (
        <div className="border-t border-border pt-2.5">
          <button
            type="button"
            aria-expanded={showSources}
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-2 text-[14px] font-bold text-text-muted"
          >
            {t.sources} · {numbered.length.toLocaleString(lang)}
            <ChevronIcon className={showSources ? "rotate-180" : ""} />
          </button>
          {showSources && (
            <ol className="mt-2.5 flex list-none flex-col gap-2 p-0 text-ui">
              {numbered.map(([n, s]) => (
                <li key={n} className="flex items-center gap-3">
                  <span className={`mono inline-flex h-5 min-w-5 items-center justify-center rounded-sm px-1 text-[12px] font-medium ${tone(n)}`}>{n}</span>
                  <span dir="auto"><Bidi text={sectionLabel(s)} /></span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {!turn.restored && (turn.status === "done" || (turn.status === "error" && turn.usage)) && (
        <TraceLine turn={turn} lang={lang} t={t} open={traceOpen} onOpen={(from) => onTrace(from)} />
      )}

      {turn.status === "done" && turn.messageId && !turn.restored && (
        <Feedback key={turn.messageId} messageId={turn.messageId} lang={lang} t={t.feedback} />
      )}
    </article>
  );
}

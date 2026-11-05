"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { Dictionary } from "@/app/[lang]/dictionaries";
import { Button } from "@/components/ui/Button";
import { Tag } from "@/components/ui/Tag";
import { ChevronIcon, CloseIcon, RetryIcon, SpinnerIcon, SwapIcon } from "@/components/ui/icons";
import { blocks, runs, spoken, type Inline } from "@/lib/answer";
import type { Source, Turn } from "@/lib/chat";
import { Feedback } from "./Feedback";

export type ChatStrings = Dictionary["chat"];

// One tone per source number, cycling: rose, stone, salmon (board A-S2).
const TONES = ["bg-tint-rose text-on-rose", "bg-tint-stone text-on-stone", "bg-tint-salmon text-on-salmon"];
const tone = (n: number) => TONES[(n - 1) % TONES.length];

const fill = (s: string, n: number | string) => s.replace("{n}", String(n));

function plural(lang: string, forms: { one: string; other: string }, n: number) {
  const rule = new Intl.PluralRules(lang).select(n);
  return fill(rule === "one" ? forms.one : forms.other, n.toLocaleString(lang));
}

/** Text with Latin words isolated: in Hebrew, "ב-pgvector" keeps its order. */
function Bidi({ text }: { text: string }) {
  return (
    <>
      {runs(text).map((r, i) => (r.latin ? <bdi key={i}>{r.text}</bdi> : r.text))}
    </>
  );
}

type CiteProps = {
  n: number;
  label: string;
  open: boolean;
  ready: boolean;
  onOpen: (n: number, el: HTMLButtonElement) => void;
};

function Cite({ n, label, open, ready, onOpen }: CiteProps) {
  return (
    <button
      type="button"
      data-cite={n}
      aria-label={label}
      aria-expanded={ready ? open : undefined}
      aria-haspopup={ready ? "dialog" : undefined}
      disabled={!ready} // the sources arrive at the end of the answer
      onClick={(e) => onOpen(n, e.currentTarget)}
      className={`mono mx-[3px] inline-flex h-5 min-w-5 items-center justify-center rounded-sm px-1 align-[2px] text-[12px] font-medium disabled:cursor-default ${tone(n)} ${open ? "outline-2 outline-offset-1 outline-text" : ""}`}
    >
      {n}
    </button>
  );
}

function Inlines({ inlines, cite }: { inlines: Inline[]; cite: (n: number, key: number) => React.ReactNode }) {
  return (
    <>
      {inlines.map((i, k) => {
        if (i.kind === "break") return <br key={k} />;
        if (i.kind === "cite") return cite(i.index, k);
        return i.bold ? <strong key={k}><Bidi text={i.text} /></strong> : <Bidi key={k} text={i.text} />;
      })}
    </>
  );
}

function sectionLabel(s: Source) {
  return s.section && s.section !== "all" ? `${s.recordTitle} · ${s.section}` : s.recordTitle;
}

type PopoverProps = {
  n: number;
  source: Source;
  top: number;
  t: ChatStrings;
  onClose: () => void;
};

// The source of one citation: a popover under the line on desktop, a bottom sheet on mobile
// (boards A-S2 and S2-Mobile). Esc, the close button or a click outside closes it, and focus
// goes back to the citation.
function SourcePopover({ n, source, top, t, onClose }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    ref.current?.focus();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const click = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!ref.current?.contains(target) && !target.closest("[data-cite]")) onClose();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", click);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("mousedown", click);
    };
  }, [onClose]);

  return (
    <>
      <div aria-hidden="true" className="fixed inset-0 z-20 bg-black/45 md:hidden" />
      <div
        ref={ref}
        role="dialog"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ "--top": `${top}px` } as React.CSSProperties}
        className="fixed inset-x-0 bottom-0 z-30 flex max-h-[70vh] flex-col overflow-hidden rounded-t-[18px] border-t-[1.5px] border-border-strong bg-surface-raised pb-[max(16px,env(safe-area-inset-bottom))] text-[15px] leading-[1.6] shadow-pop outline-none md:absolute md:inset-x-auto md:bottom-auto md:start-10 md:top-(--top) md:max-h-none md:w-[372px] md:rounded-lg md:border-[1.5px] md:pb-0"
      >
        <div className="flex justify-center pt-2 md:hidden" aria-hidden="true">
          <span className="h-1 w-10 rounded-[2px] bg-text-muted" />
        </div>
        <div className={`flex items-center gap-3 px-4 py-2.5 md:py-3 ${tone(n)}`}>
          <h2 id={titleId} className="flex-1 text-[16px] font-extrabold md:text-[15px]">
            {n} · <Bidi text={sectionLabel(source)} />
          </h2>
          <button type="button" onClick={onClose} aria-label={t.close} className="-me-2 flex size-11 items-center justify-center rounded-md md:size-8">
            <CloseIcon />
          </button>
        </div>
        {/* A chunk can be a whole record (C4), so the quote scrolls inside a bounded window;
            focusable, so the keyboard can scroll it too. Records are Markdown, rendered as the
            answer is. */}
        <blockquote
          dir="auto"
          tabIndex={0}
          aria-label={sectionLabel(source)}
          className="m-0 overflow-y-auto px-4 py-3.5 text-[16px] leading-[1.7] md:max-h-72 md:text-[15px] md:leading-[1.6]"
        >
          {blocks([{ kind: "text", text: source.text }]).map((b, i) => (
            <p key={i} className={`mb-2 last:mb-0 ${b.kind === "li" ? "relative ps-4 before:absolute before:start-0.5 before:content-['•']" : ""} ${b.kind === "h" ? "font-extrabold" : ""}`}>
              <Inlines inlines={b.inlines} cite={() => null} />
            </p>
          ))}
        </blockquote>
      </div>
    </>
  );
}

function status(turn: Turn, t: ChatStrings): string | null {
  if (turn.status === "sending") return t.thinking;
  if (turn.status !== "streaming") return null;
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
      return t.errors.tooLong;
    default:
      return t.errors.internal;
  }
}

function TraceLine({ turn, lang, t }: { turn: Turn; lang: string; t: ChatStrings }) {
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
    </div>
  );
}

type Props = { turn: Turn; lang: string; t: ChatStrings; agentName: string; onRetry: () => void };

export function AgentMessage({ turn, lang, t, agentName, onRetry }: Props) {
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
  const announce = done && !quiet ? spoken(turn.parts) : "";

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

      <div role="status" className={now ? "flex items-center gap-2.5 text-ui text-text-muted" : "sr-only"}>
        {now ? (
          <>
            <SpinnerIcon />
            {now}
          </>
        ) : (
          announce
        )}
      </div>

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
            <SourcePopover n={open.n} source={byIndex.get(open.n)!} top={open.top} t={t} onClose={close} />
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

      {(turn.status === "done" || (turn.status === "error" && turn.usage)) && (
        <TraceLine turn={turn} lang={lang} t={t} />
      )}

      {turn.status === "done" && turn.messageId && (
        <Feedback key={turn.messageId} messageId={turn.messageId} lang={lang} t={t.feedback} />
      )}
    </article>
  );
}

"use client";

import { useEffect, useId, useRef } from "react";

import type { Dictionary } from "@/app/[lang]/dictionaries";
import { CloseIcon } from "@/components/ui/icons";
import { blocks, runs, type Inline } from "@/lib/answer";
import type { Source } from "@/lib/chat";

export type ChatStrings = Dictionary["chat"];

// One tone per source number, cycling: rose, stone, salmon (board A-S2).
const TONES = ["bg-tint-rose text-on-rose", "bg-tint-stone text-on-stone", "bg-tint-salmon text-on-salmon"];
export const tone = (n: number) => TONES[(n - 1) % TONES.length];

export const fill = (s: string, n: number | string) => s.replace("{n}", String(n));

export function plural(lang: string, forms: { one: string; other: string }, n: number) {
  const rule = new Intl.PluralRules(lang).select(n);
  return fill(rule === "one" ? forms.one : forms.other, n.toLocaleString(lang));
}

/** Text with Latin words isolated: in Hebrew, "ב-pgvector" keeps its order. */
export function Bidi({ text }: { text: string }) {
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

export function Cite({ n, label, open, ready, onOpen }: CiteProps) {
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

export function Inlines({ inlines, cite }: { inlines: Inline[]; cite: (n: number, key: number) => React.ReactNode }) {
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

export function sectionLabel(s: Source) {
  return s.section && s.section !== "all" ? `${s.recordTitle} · ${s.section}` : s.recordTitle;
}

type PopoverProps = {
  n: number;
  source: Source;
  top: number;
  t: ChatStrings;
  onClose: () => void;
  onFound?: () => void; // "how was this chunk found?": the chunk's row in S3
};

// The source of one citation: a popover under the line on desktop, a bottom sheet on mobile
// (boards A-S2 and S2-Mobile). Esc, the close button or a click outside closes it, and focus
// goes back to the citation.
export function SourcePopover({ n, source, top, t, onClose, onFound }: PopoverProps) {
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
        {onFound && (
          <div className="border-t border-border px-4 py-2.5">
            <button type="button" onClick={onFound} className="text-[14px] font-bold text-accent underline underline-offset-2">
              {t.trace.howFound}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

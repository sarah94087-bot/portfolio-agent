"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/Button";
import { DownloadIcon } from "@/components/ui/icons";
import type { Source } from "@/lib/chat";
import { gapsOf, reportFile, sourceNumbers, type JobReport as Report, type JobRequirement, type Level, type Strength } from "@/lib/job";
import { Bidi, sectionLabel, SourcePopover, tone, type ChatStrings } from "./sources";

// S4 (boards S4-Report, S4-EN, S4-Mobile-EN-Dark, S4-Print). Strength is carried by shape, word
// and color together, so it reads in black and white too. A gap is neutral and dashed, never red.

type T = ChatStrings["job"];
type IconKind = "strong" | "partial" | "gap";

function Mark({ kind, size = 15 }: { kind: IconKind; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" className="flex-none">
      {kind === "strong" && (
        <>
          <circle cx="8" cy="8" r="7" fill="currentColor" />
          <path d="M4.8 8.2 7 10.4l4.2-4.6" stroke="var(--match-strong-bg)" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </>
      )}
      {kind === "partial" && (
        <>
          <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M8 1.8a6.2 6.2 0 0 1 0 12.4z" fill="currentColor" />
        </>
      )}
      {kind === "gap" && <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.4 2.2" />}
    </svg>
  );
}

const strengthIcon: Record<Strength, IconKind> = { strong: "strong", partial: "partial", none: "gap" };
const levelIcon: Record<Level, IconKind> = { high: "strong", partial: "partial", low: "gap" };
const strengthStyle: Record<Strength, string> = {
  strong: "bg-match-strong-bg text-match-strong",
  partial: "bg-match-partial-bg text-match-partial",
  none: "border border-dashed border-match-gap bg-match-gap-bg text-match-gap",
};
const levelStyle: Record<Level, string> = {
  high: strengthStyle.strong,
  partial: strengthStyle.partial,
  low: strengthStyle.none,
};

function Kind({ kind, t, onGap }: { kind: JobRequirement["kind"]; t: T; onGap?: boolean }) {
  const style = kind === "must"
    ? onGap ? "bg-match-gap text-match-gap-bg" : "bg-text text-surface"
    : onGap ? "border border-match-gap" : "border border-border-input text-text-muted";
  return <span className={`inline-flex flex-none items-center rounded-full px-[9px] py-px text-[12px] font-bold ${style}`}>{t.kind[kind]}</span>;
}

function StrengthBadge({ strength, t }: { strength: Strength; t: T }) {
  return (
    <span className={`inline-flex items-center gap-[7px] whitespace-nowrap rounded-[8px] px-2.5 py-1 text-[13.5px] font-bold ${strengthStyle[strength]}`}>
      <Mark kind={strengthIcon[strength]} />
      {t.strength[strength]}
    </span>
  );
}

const Note = ({ children }: { children: React.ReactNode }) => (
  <span className="mt-1.5 inline-flex rounded-[6px] border border-border bg-surface-sunken px-2 py-0.5 text-[12.5px] font-semibold text-text-muted">{children}</span>
);

const yearsText = (t: T, r: JobRequirement, lang: string) =>
  t.years.replace("{required}", (r.yearsRequired ?? 0).toLocaleString(lang)).replace("{covered}", (r.yearsCovered ?? 0).toLocaleString(lang));

function Notes({ r, t, lang }: { r: JobRequirement; t: T; lang: string }) {
  return (
    <>
      {r.cvOnly && <Note>{t.cvOnly}</Note>}
      {r.yearsRequired !== null && <Note>{yearsText(t, r, lang)}</Note>}
    </>
  );
}

function fill(s: string, n: number, lang: string) {
  return s.replace("{n}", n.toLocaleString(lang));
}

function plural(lang: string, forms: { one: string; other: string }, n: number) {
  return fill(new Intl.PluralRules(lang).select(n) === "one" ? forms.one : forms.other, n, lang);
}

function mustNote(gaps: JobRequirement[], t: T, lang: string) {
  const musts = gaps.filter((g) => g.kind === "must").length;
  if (musts === 0) return "";
  if (gaps.length === 1) return t.mustOnly;
  return musts === gaps.length ? t.mustAll : plural(lang, t.mustSome, musts);
}

function save(text: string, name: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

const today = () => new Date().toISOString().slice(0, 10);

type Open = { chunkId: string; n: number; top: number; from: HTMLButtonElement };

type Props = {
  report: Report;
  markdown?: string;
  sources: Source[];
  lang: string;
  t: ChatStrings;
  agentLine: string;
  onFound?: (from: HTMLElement, chunkId: string) => void;
};

export function JobReport({ report, markdown, sources, lang, t, agentLine, onFound }: Props) {
  const j = t.job;
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const [printing, setPrinting] = useState(false);
  const numbers = sourceNumbers(report);
  const gaps = gapsOf(report);
  const source = open && sources.find((s) => s.chunkId === open.chunkId);

  function close() {
    open?.from.focus();
    setOpen(null);
  }

  function openCite(chunkId: string, n: number, el: HTMLButtonElement) {
    if (open?.chunkId === chunkId && open.from === el) return close();
    const a = box.current!.getBoundingClientRect();
    setOpen({ chunkId, n, top: el.getBoundingClientRect().bottom - a.top + 8, from: el });
  }

  // The print layout is on the page only while the browser prints it (globals.css).
  useEffect(() => {
    if (!printing) return;
    const title = document.title;
    document.title = reportFile(report, today(), "pdf").replace(/\.pdf$/, "");
    const done = () => {
      document.title = title;
      setPrinting(false);
    };
    window.addEventListener("afterprint", done, { once: true });
    window.print();
    return () => window.removeEventListener("afterprint", done);
  }, [printing, report]);

  const cites = (r: JobRequirement) =>
    r.evidence.length === 0 ? (
      <span className="text-text-muted">—</span>
    ) : (
      r.evidence.map((c) => {
        const n = numbers.get(c)!;
        return (
          <button
            key={c}
            type="button"
            data-cite={n}
            aria-label={t.source.replace("{n}", String(n))}
            aria-haspopup="dialog"
            aria-expanded={open?.chunkId === c}
            disabled={!sources.some((s) => s.chunkId === c)}
            onClick={(e) => openCite(c, n, e.currentTarget)}
            className={`mono me-1 inline-flex h-5 min-w-5 items-center justify-center rounded-sm px-1 text-[12px] font-medium ${tone(n)}`}
          >
            {n}
          </button>
        );
      })
    );

  return (
    <div ref={box} className="relative">
      <article aria-label={j.kicker} className="flex flex-col gap-5 rounded-[16px] border-[1.5px] border-border-strong bg-surface-raised p-4 md:p-6">
        <header className="flex flex-wrap items-start gap-3.5">
          <div className="min-w-[200px] flex-1">
            <p className="text-[12.5px] text-text-muted">{j.kicker}</p>
            <h2 dir="auto" className="mt-0.5 text-[24px] font-extrabold leading-[1.3]">
              <Bidi text={report.roleTitle || j.untitled} />
            </h2>
          </div>
          <div className="flex flex-col items-start gap-0.5">
            <span className="text-[12px] text-text-muted">{j.overall}</span>
            <span className={`inline-flex items-center gap-2 rounded-[10px] px-3.5 py-1.5 text-[18px] font-extrabold ${levelStyle[report.overall]}`}>
              <Mark kind={levelIcon[report.overall]} size={18} />
              {j.level[report.overall]}
            </span>
          </div>
        </header>

        {gaps.length > 0 ? (
          <section aria-label={j.gapsLabel} className="rounded-[12px] border-[1.5px] border-dashed border-match-gap bg-match-gap-bg px-4 py-3.5 text-match-gap">
            <h3 className="mb-1 text-[16px] font-extrabold">{plural(lang, j.gapsTitle, gaps.length)}</h3>
            <p className="mb-2.5 text-[13.5px] leading-[1.55]">
              {j.gapsSub} {mustNote(gaps, j, lang)}
            </p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {gaps.map((g) => (
                <li key={g.id} className="flex items-center gap-2.5 text-[14.5px] font-semibold">
                  <Kind kind={g.kind} t={j} onGap />
                  <span dir="auto"><Bidi text={g.text} /></span>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <p className="rounded-[12px] border-[1.5px] border-border px-4 py-3 text-[14.5px] font-semibold">{j.noGaps}</p>
        )}

        {/* Desktop: a table. A phone: one card per requirement, with the same content. */}
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[640px] border-collapse">
            <caption className="sr-only">{j.tableCaption}</caption>
            <thead>
              <tr className="text-[12px] font-bold text-text-muted">
                <th scope="col" className="w-[30%] border-b-[1.5px] border-border-strong px-2.5 py-2 text-start">{j.columns.requirement}</th>
                <th scope="col" className="w-[16%] border-b-[1.5px] border-border-strong px-2.5 py-2 text-start">{j.columns.strength}</th>
                <th scope="col" className="border-b-[1.5px] border-border-strong px-2.5 py-2 text-start">{j.columns.rationale}</th>
                <th scope="col" className="w-[12%] border-b-[1.5px] border-border-strong px-2.5 py-2 text-start">{j.columns.sources}</th>
              </tr>
            </thead>
            <tbody>
              {report.requirements.map((r) => (
                <tr key={r.id} className="align-top text-[14px] leading-[1.55]">
                  <th scope="row" dir="auto" className="border-b border-border px-2.5 py-3 text-start font-bold">
                    <Bidi text={r.text} />
                    <br />
                    <Kind kind={r.kind} t={j} />
                  </th>
                  <td className="border-b border-border px-2.5 py-3"><StrengthBadge strength={r.strength} t={j} /></td>
                  <td dir="auto" className="border-b border-border px-2.5 py-3">
                    <Bidi text={r.rationale} />
                    {(r.cvOnly || r.yearsRequired !== null) && <div><Notes r={r} t={j} lang={lang} /></div>}
                  </td>
                  <td className="border-b border-border px-2.5 py-3">{cites(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="m-0 flex list-none flex-col gap-2.5 p-0 md:hidden">
          {report.requirements.map((r) => (
            <li key={r.id} className="flex flex-col gap-2 rounded-[12px] border border-border px-3.5 py-3">
              <div className="flex items-start gap-2">
                <h3 dir="auto" className="flex-1 text-[15px] font-bold leading-[1.4]"><Bidi text={r.text} /></h3>
                <Kind kind={r.kind} t={j} />
              </div>
              <div><StrengthBadge strength={r.strength} t={j} /></div>
              <p dir="auto" className="text-[14px] leading-[1.55]"><Bidi text={r.rationale} /></p>
              {(r.cvOnly || r.yearsRequired !== null) && <div className="-mt-1.5"><Notes r={r} t={j} lang={lang} /></div>}
              {r.evidence.length > 0 && <div>{cites(r)}</div>}
            </li>
          ))}
        </ul>

        <section aria-label={j.summary}>
          <h3 className="mb-1.5 text-[16px] font-extrabold">{j.summary}</h3>
          <p dir="auto" className="text-[16.5px] leading-[1.65] [:lang(he)_&]:text-[17.5px] [:lang(he)_&]:leading-[1.8]"><Bidi text={report.summary} /></p>
        </section>

        <footer className="flex flex-wrap items-center gap-2.5 border-t border-border pt-3.5">
          {markdown && (
            <Button variant="secondary" className="min-h-10" onClick={() => save(markdown, reportFile(report, today(), "md"))}>
              <DownloadIcon size={16} />
              {j.downloadMd}
            </Button>
          )}
          <Button variant="secondary" className="min-h-10" onClick={() => setPrinting(true)}>
            <DownloadIcon size={16} />
            {j.downloadPdf}
          </Button>
          <span className="ms-auto text-[12.5px] text-text-muted">{j.honest}</span>
        </footer>
      </article>

      {open && source && (
        <SourcePopover
          n={open.n}
          source={source}
          top={open.top}
          t={t}
          onClose={close}
          onFound={onFound ? () => {
            const { from, chunkId } = open;
            setOpen(null);
            onFound(from, chunkId);
          } : undefined}
        />
      )}

      {printing && createPortal(
        <PrintReport report={report} sources={sources} numbers={numbers} gaps={gaps} lang={lang} j={j} agentLine={agentLine} />,
        document.body,
      )}
    </div>
  );
}

const GLYPH: Record<Strength | Level, string> = { strong: "●", partial: "◐", none: "○", high: "●", low: "○" };

// Board S4-Print: black on white, and the strength as a character and a word.
function PrintReport({ report, sources, numbers, gaps, lang, j, agentLine }: {
  report: Report; sources: Source[]; numbers: Map<string, number>; gaps: JobRequirement[]; lang: string; j: T; agentLine: string;
}) {
  const commit = sources.find((s) => s.commit)?.commit?.slice(0, 7);
  const titled = new Map(sources.map((s) => [s.chunkId, s]));
  return (
    <div id="report-print" lang={lang} dir={lang === "he" ? "rtl" : "ltr"}>
      <div className="print-head">
        <span>{agentLine}</span>
        <span className="mono">{commit ? `kb@${commit} · ` : ""}{today()}</span>
      </div>
      <p className="print-kicker">{j.kicker}</p>
      <h1 dir="auto">{report.roleTitle || j.untitled}</h1>
      <p className="print-overall">{j.overall}: {GLYPH[report.overall]} {j.level[report.overall]}</p>
      <div className="print-gaps">
        {gaps.length > 0 ? (
          <>
            <b>{plural(lang, j.gapsTitle, gaps.length)}.</b>{" "}
            {gaps.map((g) => `○ ${g.text} (${j.kind[g.kind]})`).join(" · ")}. {j.gapsSub}
          </>
        ) : j.noGaps}
      </div>
      <table>
        <thead>
          <tr>
            <th>{j.columns.requirement}</th>
            <th>{j.columns.strength}</th>
            <th>{j.columns.rationale}</th>
            <th>{j.columns.sources}</th>
          </tr>
        </thead>
        <tbody>
          {report.requirements.map((r) => (
            <tr key={r.id}>
              <td dir="auto"><b>{r.text}</b> ({j.kind[r.kind]})</td>
              <td>{GLYPH[r.strength]} {j.strength[r.strength]}</td>
              <td dir="auto">
                {r.rationale}
                {r.cvOnly ? ` (${j.cvOnly})` : ""}
                {r.yearsRequired !== null ? ` (${yearsText(j, r, lang)})` : ""}
              </td>
              <td className="mono">{r.evidence.map((c) => `[${numbers.get(c)}]`).join("") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>{j.summary}</h2>
      <p dir="auto" className="print-summary">{report.summary}</p>
      <div className="print-foot">
        {numbers.size > 0 && (
          <p>
            <b>{j.columns.sources}:</b>{" "}
            {[...numbers].map(([c, n]) => {
              const s = titled.get(c);
              return `[${n}] ${s ? sectionLabel(s) : c}`;
            }).join(" · ")}
          </p>
        )}
        <p>{j.printNote}</p>
      </div>
    </div>
  );
}

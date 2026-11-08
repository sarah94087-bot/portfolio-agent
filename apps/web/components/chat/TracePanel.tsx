"use client";

import { useEffect, useRef, useState } from "react";

import { CloseIcon } from "@/components/ui/icons";
import type { Turn } from "@/lib/chat";
import { buildTrace, score, type Row, type TimelineItem, type TraceEvent, type TraceView } from "@/lib/trace";
import type { ChatStrings } from "./AgentMessage";

// S3, "how this answer was built" (boards S3-Trace, S3-Tablet, S3-Mobile). From 1100px it sits
// beside the conversation and pushes it (globals.css, [data-trace]); from 768px it opens over the
// conversation at the inline end, under the header; on a phone it is a sheet from the bottom
// that leaves the top of the conversation in view (US-4.4). Everything in it comes from the
// turn's events (lib/trace.ts).

const REPO = "https://github.com/sarah94087-bot/portfolio-agent";
const FIRST_ROWS = 8;

type T = ChatStrings["trace"];

const fill = (s: string, vals: Record<string, string | number>) =>
  s.replace(/\{(\w+)\}/g, (m, k: string) => (k in vals ? String(vals[k]) : m));

function plural(lang: string, forms: { one: string; other: string; zero?: string }, n: number) {
  if (n === 0 && forms.zero) return forms.zero;
  const form = new Intl.PluralRules(lang).select(n) === "one" ? forms.one : forms.other;
  return fill(form, { n: n.toLocaleString(lang) });
}

const short = (model?: string) => model?.split("/").at(-1);

/** Latin names (tools, models, queries) kept in their own direction inside Hebrew text. */
const Code = ({ children }: { children: React.ReactNode }) => (
  <bdi className="mono text-[0.92em]">{children}</bdi>
);

/** A sentence from the dictionary with Latin values set apart. */
function Sentence({ text, vals }: { text: string; vals: Record<string, string> }) {
  const parts = text.split(/(\{\w+\})/);
  return (
    <>
      {parts.map((p, i) => {
        const k = /^\{(\w+)\}$/.exec(p)?.[1];
        return k && k in vals ? <Code key={i}>{vals[k]}</Code> : p;
      })}
    </>
  );
}

function seconds(ms: number | undefined, lang: string, t: ChatStrings) {
  if (ms === undefined) return null;
  return fill(t.seconds, { n: (ms / 1000).toLocaleString(lang, { maximumFractionDigits: 2 }) });
}

function Section({ id, title, sub, children }: { id: string; title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="border-b border-border py-[18px] last:border-b-0">
      <h3 id={id} className="mb-1 text-[14px] font-extrabold">{title}</h3>
      {sub && <p className="mb-2.5 text-[12.5px] leading-[1.5] text-text-muted">{sub}</p>}
      {children}
    </section>
  );
}

function stepText(item: TimelineItem, lang: string, t: ChatStrings): { name: React.ReactNode; meta: string | null; text: React.ReactNode } {
  const tr = t.trace;
  const fellBack = "restart" in item && item.restart;
  const restart = fellBack ? (
    <> <Sentence text={tr.restartText} vals={{ failed: short(fellBack.failed) ?? "?", to: short(fellBack.to) ?? "?" }} /></>
  ) : null;
  switch (item.kind) {
    case "model":
      return {
        name: fellBack ? `${tr.model} · ${tr.fallbackSuffix}` : tr.model,
        meta: seconds(item.ms, lang, t),
        text: <><Sentence text={tr.modelText} vals={{ tools: item.tools.join(", ") }} />{restart}</>,
      };
    case "answer":
      return {
        name: fellBack ? `${tr.answer} · ${tr.fallbackSuffix}` : tr.answer,
        meta: seconds(item.ms, lang, t),
        text: <>{plural(lang, tr.answerText, item.citations)}{restart}</>,
      };
    case "tool_call":
      return {
        name: <>{tr.toolCall} · <Code>{item.tool}</Code></>,
        meta: seconds(item.ms, lang, t),
        text: item.tool === "search_portfolio"
          ? item.method === "R1" ? tr.searchR1 : item.method === "R4" ? tr.searchR4 : tr.searchR3
          : <Sentence text={tr.projectText} vals={{ record: item.record ?? "" }} />,
      };
    case "tool_result":
      return {
        name: tr.toolResult,
        meta: item.candidates !== undefined ? fill(tr.candidates, { n: item.candidates.toLocaleString(lang) }) : null,
        text: item.candidates !== undefined
          ? fill(tr.resultText, { k: item.selected.toLocaleString(lang), n: item.candidates.toLocaleString(lang) })
          : plural(lang, tr.resultShort, item.selected),
      };
    case "guard":
      return { name: tr.guard, meta: null, text: tr.guardText };
    case "job": {
      const stage = item.stage as keyof typeof tr.jobStage;
      return {
        name: tr.jobStage[stage] ?? item.stage,
        meta: seconds(item.ms, lang, t),
        text: fill(tr.jobText[stage] ?? "", {
          capped: (item.capped ?? 0).toLocaleString(lang),
          dropped: (item.dropped ?? 0).toLocaleString(lang),
        }),
      };
    }
  }
}

function argsText(args: Record<string, unknown>) {
  return Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
}

function SelectedMark({ row, t }: { row: Row; t: T }) {
  if (!row.selected) return null;
  return (
    <span title={t.selected} className="mono flex-none rounded-[4px] bg-accent px-1 text-[10.5px] font-bold leading-4 text-on-accent">
      <span aria-hidden="true">✓</span>
      <span className="sr-only">{t.selected}</span>
      {row.cite !== undefined && <> {row.cite}</>}
    </span>
  );
}

function Candidates({ search, highlight, rowId, lang, t }: {
  search: TraceView["searches"][number]; highlight?: string; rowId: (chunkId: string) => string; lang: string; t: T;
}) {
  const [all, setAll] = useState(false);
  const wanted = highlight ? search.rows.findIndex((r) => r.chunkId === highlight) : -1;
  const shown = all || wanted >= FIRST_ROWS ? search.rows : search.rows.slice(0, FIRST_ROWS);
  const cols = [t.lexical, t.vector, "RRF", t.rerank];
  const values = (r: Row) => [score(r.lexical, 3), score(r.vector, 2), score(r.rrf, 3), score(r.rerank, 0)];
  const mark = (r: Row) => (r.chunkId === highlight ? "outline-2 -outline-offset-2 outline-accent" : "");

  return (
    <>
      {search.query && (
        <p className="mb-2 text-[12.5px] text-text-muted"><Sentence text={t.retrievalQuery} vals={{ q: search.query }} /></p>
      )}
      {/* md and up: a table */}
      <table className="hidden w-full table-fixed border-collapse max-md:hidden md:table">
        <caption className="sr-only">{t.retrieval}</caption>
        <colgroup>
          <col className="w-[22px]" /><col /><col className="w-[48px]" /><col className="w-[44px]" /><col className="w-[48px]" /><col className="w-[52px]" />
        </colgroup>
        <thead>
          <tr className="text-[11px] font-semibold text-text-muted">
            <th scope="col" className="border-b border-border-strong px-1.5 py-1 text-start">#</th>
            <th scope="col" className="border-b border-border-strong px-1.5 py-1 text-start">{t.excerpt}</th>
            {cols.map((c) => <th key={c} scope="col" className="border-b border-border-strong px-1.5 py-1 text-end">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.chunkId} id={rowId(r.chunkId)} tabIndex={-1} className={`text-[11.5px] align-top ${r.selected ? "bg-tint-rose" : ""} ${mark(r)}`}>
              <td className="mono border-b border-border px-1.5 py-[7px] text-text-muted">{r.rank}</td>
              <td className="border-b border-border px-1.5 py-[7px]">
                <div className="flex items-start gap-1.5">
                  <SelectedMark row={r} t={t} />
                  <span dir="auto" title={r.excerpt} className={`min-w-0 truncate ${r.selected ? "font-semibold" : ""}`}>{r.excerpt}</span>
                </div>
              </td>
              {values(r).map((v, i) => (
                <td key={i} className={`mono border-b border-border px-1.5 py-[7px] text-end ${i === 2 ? "font-bold" : ""}`}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {/* phones: cards */}
      <ol className="flex list-none flex-col gap-2 p-0 md:hidden">
        {shown.map((r) => (
          <li key={r.chunkId} id={`${rowId(r.chunkId)}-card`} tabIndex={-1}
            className={`rounded-[10px] border p-2.5 ${r.selected ? "border-accent" : "border-border"} ${mark(r)}`}>
            <div className="mb-1.5 flex items-center gap-2">
              {r.selected ? (
                <span className="mono rounded-[4px] bg-accent px-1.5 text-[11px] font-bold leading-[18px] text-on-accent">
                  ✓ {t.selected}{r.cite !== undefined && <> · {fill(t.citation, { n: r.cite })}</>}
                </span>
              ) : (
                <span className="mono rounded-[4px] border border-border px-1.5 text-[11px] leading-[18px] text-text-muted">{t.notSelected}</span>
              )}
              <span className="mono ms-auto text-[11.5px] text-text-muted">#{r.rank}</span>
            </div>
            <p dir="auto" className={`mb-2 text-[13.5px] leading-[1.5] ${r.selected ? "" : "text-text-muted"}`}>{r.excerpt}</p>
            <dl className="mono grid grid-cols-4 gap-1.5 text-[11px]">
              {cols.map((c, i) => (
                <div key={c} className="flex flex-col rounded-[6px] bg-surface-sunken px-1.5 py-1">
                  <dt className="text-text-muted">{c}</dt>
                  <dd className="m-0 font-bold">{values(r)[i]}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ol>

      <p className="mt-2 text-[12.5px] text-text-muted">
        {search.rows.length > FIRST_ROWS && (
          <>
            {fill(t.showing, { k: shown.length.toLocaleString(lang), n: search.rows.length.toLocaleString(lang) })}{" "}
            <button type="button" onClick={() => setAll((v) => !v)} className="font-bold text-accent underline">
              {all ? t.showLess : t.showAll}
            </button>{" "}
          </>
        )}
        {search.rows.every((r) => r.rerank === undefined) && t.noRerank}
      </p>
    </>
  );
}

function Waterfall({ w, lang, t }: { w: NonNullable<TraceView["waterfall"]>; lang: string; t: T }) {
  const bars = [
    w.setup !== undefined && { name: t.setup, start: 0, ms: w.setup, color: "bg-match-gap" },
    w.retrieval && { name: t.retrievalBar, start: w.retrieval.start, ms: w.retrieval.ms, color: "bg-on-rose" },
    w.ttft !== undefined && { name: t.ttft, start: 0, ms: w.ttft, color: "bg-on-stone" },
    w.generation && { name: t.generation, start: w.generation.start, ms: w.generation.ms, color: "bg-on-salmon" },
  ].filter((b): b is { name: string; start: number; ms: number; color: string } => Boolean(b));
  const pct = (v: number) => `${Math.min(100, (v / w.total) * 100)}%`;
  const ms = (v: number) => fill(t.ms, { n: v.toLocaleString(lang) });
  const label = [...bars.map((b) => `${b.name} ${ms(b.ms)}`), `${t.total} ${ms(w.total)}`].join(", ");

  return (
    <>
      <div role="img" aria-label={label} className="flex flex-col gap-[7px]">
        {bars.map((b) => (
          <div key={b.name} aria-hidden="true" className="grid grid-cols-[104px_1fr] items-center gap-2.5 text-[12px]">
            <span>{b.name}</span>
            <div className="flex items-center gap-2">
              <div className="relative h-4 flex-1 overflow-hidden rounded-[4px] bg-surface-sunken">
                <span className={`absolute inset-y-0 min-w-[3px] rounded-[3px] ${b.color}`}
                  style={{ insetInlineStart: pct(b.start), width: pct(b.ms) }} />
              </div>
              <span dir="ltr" className="mono w-16 whitespace-nowrap text-end text-text-muted">{ms(b.ms)}</span>
            </div>
          </div>
        ))}
      </div>
      <p className="mono mt-2 text-[12px] text-text-muted">{t.total} <span dir="ltr">{ms(w.total)}</span></p>
    </>
  );
}

function eventText(e: TraceEvent, lang: string, t: T): { title: string; text: React.ReactNode; tone: "fallback" | "removed" | "plain" } {
  switch (e.kind) {
    case "fallback":
      return {
        title: t.fallback,
        tone: "fallback",
        text: e.failed && e.to
          ? <Sentence text={t.fallbackText} vals={{ failed: short(e.failed)!, to: short(e.to)!, reason: e.reason ?? "?" }} />
          : t.fallbackPlain,
      };
    case "dropped":
      return { title: t.dropped, tone: "removed", text: plural(lang, t.droppedText, e.n) };
    case "redacted":
      return { title: t.redacted, tone: "removed", text: t.redactedText };
    case "blocked":
      return { title: t.blocked, tone: "removed", text: t.blockedText };
    case "cached":
      return { title: t.cached, tone: "plain", text: t.cachedText };
    case "replay":
      return { title: t.replay, tone: "plain", text: t.replayText };
  }
}

function Events({ events, lang, t }: { events: TraceEvent[]; lang: string; t: T }) {
  const tones = {
    fallback: "bg-fallback-bg text-fallback",
    removed: "border border-dashed border-removed",
    plain: "bg-surface-sunken",
  };
  return (
    <ul className="flex list-none flex-col gap-2.5 p-0">
      {events.map((e, i) => {
        const v = eventText(e, lang, t);
        return (
          <li key={i} className={`grid grid-cols-[auto_1fr] gap-2.5 rounded-[10px] px-3 py-2.5 text-[13px] leading-[1.55] ${tones[v.tone]}`}>
            <b className={v.tone === "removed" ? "text-removed" : ""}>{v.title}</b>
            <span>{v.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

type Props = {
  turn: Turn;
  index: number; // the answer's number in the conversation, from 1
  lang: string;
  t: ChatStrings;
  highlight?: string; // a chunk to show in the table, from "how was this chunk found?"
  onClose: () => void;
};

export function TracePanel({ turn, index, lang, t, highlight, onClose }: Props) {
  const tr = t.trace;
  const view = buildTrace(turn);
  const closeRef = useRef<HTMLButtonElement>(null);
  const ids = `trace-${turn.key}`;
  const rowId = (chunkId: string) => `${ids}-row-${chunkId.replace(/[^\w-]/g, "_")}`;

  useEffect(() => {
    closeRef.current?.focus();
  }, [turn.key]);

  useEffect(() => {
    if (!highlight) return;
    const id = rowId(highlight);
    // the table from md up, the cards on phones: whichever is shown
    const el = [document.getElementById(id), document.getElementById(`${id}-card`)].find((x) => x?.offsetParent);
    el?.scrollIntoView({ block: "center" });
    el?.focus({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight, turn.key]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const model = short(view.model);
  const timeline = view.timeline.map((item) => stepText(item, lang, t));
  const events = (
    <Section id={`${ids}-ev`} title={tr.events} sub={view.events.length ? tr.eventsSub : undefined}>
      {view.events.length ? (
        <Events events={view.events} lang={lang} t={tr} />
      ) : (
        <p className="rounded-[8px] bg-surface-sunken px-3 py-2.5 text-[13.5px] leading-[1.6] text-text-muted">{tr.noEvents}</p>
      )}
    </Section>
  );

  return (
    <>
      {/* phones: a backdrop that closes the sheet; the conversation stays in view above it */}
      <div aria-hidden="true" onClick={onClose} className="fixed inset-0 top-14 z-30 md:hidden" />
      <aside
        role="dialog"
        aria-labelledby={`${ids}-title`}
        className="fixed inset-x-0 bottom-0 z-40 flex max-h-[70vh] flex-col rounded-t-[18px] border-t-[1.5px] border-border-strong bg-surface-raised shadow-pop
          md:inset-x-auto md:end-0 md:top-[68px] md:max-h-none md:w-[400px] md:rounded-none md:border-t-0 md:border-s-[1.5px]
          min-[68.75rem]:w-[460px] min-[68.75rem]:border-s min-[68.75rem]:shadow-none"
      >
        <div aria-hidden="true" className="flex justify-center pb-1 pt-2 md:hidden">
          <span className="h-1 w-10 rounded-[2px] bg-text-muted" />
        </div>
        <div className="flex items-center gap-2.5 border-b border-border px-4 pb-3 pt-1.5 md:px-5 md:py-4 min-[68.75rem]:px-[22px]">
          <div>
            <h2 id={`${ids}-title`} className="text-[17px] font-extrabold md:text-[18px]">{tr.title}</h2>
            <p className="mono mt-0.5 text-[12px] text-text-muted">
              {fill(tr.answerN, { n: index.toLocaleString(lang) })}{model && <> · {model}</>}
            </p>
          </div>
          <button ref={closeRef} type="button" aria-label={tr.close} onClick={onClose}
            className="ms-auto flex size-11 items-center justify-center rounded-[8px] text-text hover:bg-surface-sunken md:size-9 md:border md:border-border">
            <CloseIcon />
          </button>
        </div>

        <div className="overflow-y-auto overscroll-contain px-4 pb-10 md:px-5 min-[68.75rem]:px-[22px]">
          {view.events.length > 0 && events}

          <Section id={`${ids}-tl`} title={tr.timeline} sub={tr.timelineSub}>
            <ol className="flex list-none flex-col p-0">
              {timeline.map((s, i) => (
                <li key={i} className="grid grid-cols-[26px_1fr] gap-x-2.5 py-2">
                  <span className="mono mt-px flex size-6 items-center justify-center rounded-full bg-text text-[11px] text-surface">
                    {(i + 1).toLocaleString(lang)}
                  </span>
                  <div>
                    <h4 className="flex items-baseline gap-2 text-[14px] font-bold">
                      <span>{s.name}</span>
                      {s.meta && <span className="mono ms-auto text-[12px] font-medium text-text-muted">{s.meta}</span>}
                    </h4>
                    <p className="mt-0.5 text-[13px] leading-[1.55] text-text-muted">{s.text}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Section>

          <Section id={`${ids}-md`} title={tr.decision}>
            {view.decisions.length ? (
              view.decisions.map((d, i) => (
                <div key={i} className="mt-1.5">
                  <p className="mb-2 text-[13.5px] leading-[1.6]">
                    {typeof d.args.query === "string" ? (
                      <Sentence text={tr.decisionText} vals={{ tool: d.tool, query: d.args.query }} />
                    ) : (
                      <Sentence text={tr.decisionTool} vals={{ tool: d.tool }} />
                    )}
                  </p>
                  <code dir="ltr" className="mono block rounded-[8px] border border-border bg-surface-sunken px-3 py-2 text-start text-[12.5px] [overflow-wrap:anywhere]">
                    {d.tool}({argsText(d.args)})
                  </code>
                </div>
              ))
            ) : (
              <p className="text-[13.5px] text-text-muted">{tr.decisionNone}</p>
            )}
          </Section>

          {view.searches.map((s) => (
            <Section key={s.stepId} id={`${ids}-rt-${s.stepId}`} title={tr.retrieval} sub={tr.retrievalSub}>
              <Candidates search={s} highlight={highlight} rowId={rowId} lang={lang} t={tr} />
            </Section>
          ))}

          {view.waterfall && (
            <Section id={`${ids}-wf`} title={tr.waterfall} sub={tr.waterfallSub}>
              <Waterfall w={view.waterfall} lang={lang} t={tr} />
            </Section>
          )}

          {view.tokens.length > 0 && (
            <Section id={`${ids}-tk`} title={tr.tokens}>
              <table className="mt-1.5 w-full border-collapse text-[11.5px]">
                <thead>
                  <tr className="text-[11px] font-semibold text-text-muted">
                    <th scope="col" className="border-b border-border-strong px-1.5 py-1 text-start">{tr.call}</th>
                    <th scope="col" className="border-b border-border-strong px-1.5 py-1 text-end">{tr.input}</th>
                    <th scope="col" className="border-b border-border-strong px-1.5 py-1 text-end">{tr.output}</th>
                  </tr>
                </thead>
                <tbody>
                  {view.tokens.map((c, i) => (
                    <tr key={i}>
                      <td className="border-b border-border px-1.5 py-[7px]">{c.stage ? `${(i + 1).toLocaleString(lang)} · ${tr.jobStage[c.stage as keyof typeof tr.jobStage] ?? c.stage}` : fill(c.decision ? tr.callDecision : tr.callAnswer, { n: i + 1 })}</td>
                      <td className="mono border-b border-border px-1.5 py-[7px] text-end">{c.input.toLocaleString(lang)}</td>
                      <td className="mono border-b border-border px-1.5 py-[7px] text-end">{c.output.toLocaleString(lang)}</td>
                    </tr>
                  ))}
                  <tr className="font-bold">
                    <td className="px-1.5 py-[7px]">{tr.total}</td>
                    <td className="mono px-1.5 py-[7px] text-end">{view.tokens.reduce((a, c) => a + c.input, 0).toLocaleString(lang)}</td>
                    <td className="mono px-1.5 py-[7px] text-end">{view.tokens.reduce((a, c) => a + c.output, 0).toLocaleString(lang)}</td>
                  </tr>
                </tbody>
              </table>
            </Section>
          )}

          <Section id={`${ids}-pv`} title={tr.provenance}>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              {model && (<><dt className="text-text-muted">{tr.modelId}</dt><dd className="mono m-0"><bdi>{view.model}</bdi></dd></>)}
              {view.promptVersion && (
                <>
                  <dt className="text-text-muted">{tr.promptVersion}</dt>
                  <dd className="mono m-0">
                    <a href={`${REPO}/blob/main/backend/portfolio_agent/agent/prompts/${view.promptVersion}.md`} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
                      <bdi>{view.promptVersion}</bdi>
                    </a>
                  </dd>
                </>
              )}
              {view.commit && (
                <>
                  <dt className="text-text-muted">{tr.kbCommit}</dt>
                  <dd className="mono m-0">
                    <a href={`${REPO}/tree/${view.commit}`} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2">
                      <bdi>{view.commit.slice(0, 7)}</bdi>
                    </a>
                  </dd>
                </>
              )}
            </dl>
            {(view.promptVersion || view.commit) && <p className="mt-1.5 text-[12.5px] text-text-muted">{tr.links}</p>}
          </Section>

          {view.events.length === 0 && events}
        </div>
      </aside>
    </>
  );
}

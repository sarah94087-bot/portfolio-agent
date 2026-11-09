"use client";

import dynamic from "next/dynamic";
import { useRef, useState } from "react";

import { ChevronIcon } from "@/components/ui/icons";
import { figureOf, type Cards, type Metric } from "@/lib/cards";
import type { Source } from "@/lib/chat";
import { Bidi, SourcePopover, tone, type ChatStrings } from "./sources";

// S5 (boards S5-Project, S5-EN, S5-Mobile-EN-Dark). The labels are in the page's language; the
// values are the record's own words, in English, and are marked as such (ADR-0018).

const Diagram = dynamic(() => import("./Diagram").then((m) => m.Diagram), { ssr: false });

type T = ChatStrings["card"];

function MetricRow({ metric, t }: { metric: Metric; t: T }) {
  const [open, setOpen] = useState(false);
  const figure = figureOf(metric);
  return (
    <li className={`flex flex-col rounded-[12px] border px-3.5 ${open ? "border-accent" : "border-border"}`}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-11 w-full flex-wrap items-center gap-x-2.5 gap-y-1 py-2.5 text-start text-[15px]"
      >
        {figure && (
          <span className="mono text-[20px] font-medium">
            {"value" in figure ? (
              <bdi>{figure.value}</bdi>
            ) : (
              <>
                <span aria-hidden="true" dir="ltr">{figure.from} → {figure.to}</span>
                <span className="sr-only">{t.fromTo.replace("{from}", figure.from).replace("{to}", figure.to)}</span>
              </>
            )}
          </span>
        )}
        <span lang="en" dir="auto" className="min-w-[60%] flex-1">{metric.label}</span>
        <span className="flex items-center gap-1 text-[13px] font-bold text-accent">
          {t.how}
          <ChevronIcon size={12} className={open ? "rotate-180" : ""} />
        </span>
      </button>
      {open && (
        <p lang="en" dir="auto" className="mb-2.5 border-t border-border pt-1.5 text-[13.5px] leading-[1.6] text-text-muted">
          {metric.howMeasured}
        </p>
      )}
    </li>
  );
}

type Open = { top: number; from: HTMLButtonElement };

type Props = {
  cards: Cards;
  sources: Source[];
  citeOf: (chunkId: string) => number | undefined; // its number in the answer, if it was cited
  lang: string;
  t: ChatStrings;
  onFound?: (from: HTMLElement, chunkId: string) => void;
};

export function ProjectCard({ cards, sources, citeOf, lang, t, onFound }: Props) {
  const c = t.card;
  const { project, diagram } = cards;
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<Open | null>(null);
  const main = project ?? diagram!;
  const title = lang === "he" ? main.title.he : main.title.en;
  const source = project && sources.find((s) => s.chunkId === project.source);
  const n = source ? citeOf(source.chunkId) : undefined;

  function close() {
    open?.from.focus();
    setOpen(null);
  }

  function openSource(el: HTMLButtonElement) {
    if (open) return close();
    setOpen({ top: el.getBoundingClientRect().bottom - box.current!.getBoundingClientRect().top + 8, from: el });
  }

  return (
    <div ref={box} className="relative">
      <article aria-label={project ? c.kicker : c.diagramKicker} className="flex flex-col gap-4 rounded-[16px] border-[1.5px] border-border-strong bg-surface-raised p-4 md:p-7">
        <header>
          <p className="text-[12.5px] text-text-muted">{project ? c.kicker : c.diagramKicker}</p>
          <h2 dir="auto" className="mt-1 text-[22px] font-extrabold leading-[1.3]"><Bidi text={title} /></h2>
          {project && (
            <dl className="mt-2.5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[14px]">
              <dt className="text-text-muted">{c.role}</dt>
              <dd lang="en" dir="auto" className="m-0">{project.role}</dd>
              <dt className="text-text-muted">{c.period}</dt>
              <dd lang="en" dir="auto" className="mono m-0 text-[13px]">{project.period}</dd>
            </dl>
          )}
        </header>

        {project && (
          <>
            <section>
              <h3 className="mb-2 text-[13px] font-bold text-text-muted">{c.stack}</h3>
              <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {project.tech.map((name) => (
                  <li key={name} lang="en" dir="ltr" className="mono rounded-[6px] border border-border bg-surface-sunken px-[9px] py-0.5 text-[12.5px]">{name}</li>
                ))}
              </ul>
            </section>

            {project.metrics.length > 0 && (
              <section>
                <h3 className="mb-2 text-[13px] font-bold text-text-muted">{c.metrics}</h3>
                <ul className="m-0 flex list-none flex-col gap-2 p-0">
                  {project.metrics.map((m) => <MetricRow key={m.label} metric={m} t={c} />)}
                </ul>
              </section>
            )}

            {source && (
              <p className="flex flex-wrap items-center gap-2.5 text-[14px] font-semibold">
                <span className="font-normal text-text-muted">{c.source}</span>
                <button
                  type="button"
                  data-cite={n ?? "card"}
                  aria-haspopup="dialog"
                  aria-expanded={open !== null}
                  onClick={(e) => openSource(e.currentTarget)}
                  className="flex min-h-6 items-center gap-1.5 text-accent underline underline-offset-2"
                >
                  {n !== undefined && (
                    <span className={`mono inline-flex h-5 min-w-5 items-center justify-center rounded-sm px-1 text-[12px] font-medium no-underline ${tone(n)}`}>{n}</span>
                  )}
                  {c.wholeRecord}
                </button>
              </p>
            )}
          </>
        )}

        {diagram && (
          <div className={project ? "border-t border-border pt-3.5" : ""}>
            <Diagram data={diagram} lang={lang} t={c} />
          </div>
        )}
      </article>

      {open && source && (
        <SourcePopover
          n={n ?? null}
          source={source}
          top={open.top}
          t={t}
          onClose={close}
          onFound={onFound ? () => {
            const from = open.from;
            setOpen(null);
            onFound(from, source.chunkId);
          } : undefined}
        />
      )}
    </div>
  );
}

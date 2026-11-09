"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";

import { SpinnerIcon } from "@/components/ui/icons";
import { MIN_SCALE, safeSvg, type DiagramData, type SvgNode } from "@/lib/cards";
import type { ChatStrings } from "./sources";

// The architecture diagram of S5: English and LTR in both languages (docs/design/README.md).
// Mermaid's chunk is about 266 KB gzipped, so it is imported only when a diagram is on screen.
// The source was built on the server from the record; `strict` and `htmlLabels: false` keep every
// label text, and the result joins the page as parsed nodes that passed `safeSvg`, or not at all.

const DARK = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void) {
  const query = window.matchMedia(DARK);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const isDark = () => window.matchMedia(DARK).matches;

// The colors Mermaid draws with, read from the design tokens (board Handoff).
function themeVariables() {
  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => css.getPropertyValue(`--${name}`).trim();
  return {
    fontFamily: getComputedStyle(document.body).fontFamily,
    fontSize: "14px",
    background: token("surface-raised"),
    primaryColor: token("tint-rose"),
    primaryTextColor: token("on-rose"),
    primaryBorderColor: token("accent"),
    secondaryColor: token("tint-stone"),
    tertiaryColor: token("tint-salmon"),
    lineColor: token("text"),
    textColor: token("text"),
    nodeBorder: token("accent"),
    clusterBkg: token("surface"),
    clusterBorder: token("border"),
    edgeLabelBackground: token("surface-raised"),
  };
}

// Mermaid keeps one global configuration, so drawings take turns.
let turn: Promise<unknown> = Promise.resolve();

function draw(id: string, source: string): Promise<string> {
  const job = turn.then(async () => {
    const { default: mermaid } = await import("mermaid");
    await document.fonts.ready; // labels are measured when they are drawn
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      htmlLabels: false,
      suppressErrorRendering: true,
      theme: "base",
      themeVariables: themeVariables(),
      flowchart: { htmlLabels: false, useMaxWidth: true },
    });
    return (await mermaid.render(id, source)).svg;
  });
  turn = job.catch(() => undefined);
  return job;
}

/** The checked drawing as DOM nodes, or null when it is not one we are willing to show. */
function parsed(svg: string): SVGSVGElement | null {
  const root = new DOMParser().parseFromString(svg, "image/svg+xml").documentElement;
  if (root.tagName !== "svg" || !safeSvg(root as unknown as SvgNode)) return null;
  return document.importNode(root, true) as unknown as SVGSVGElement;
}

export function Diagram({ data, lang, t }: { data: DiagramData; lang: string; t: ChatStrings["card"] }) {
  const dark = useSyncExternalStore(subscribe, isDark, () => false);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [view, setView] = useState<"diagram" | "text">("diagram");
  const [scrolls, setScrolls] = useState(false);
  const canvas = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const raw = useId();

  useEffect(() => {
    let current = true;
    // Mermaid uses this as an element id and a CSS selector.
    draw(`diagram-${raw.replace(/[^\w-]/g, "")}`, data.mermaid)
      .then((svg) => {
        if (!current || !canvas.current) return;
        const node = parsed(svg);
        if (!node) return setState("failed");
        const natural = node.viewBox.baseVal.width;
        if (natural) node.style.minWidth = `${Math.round(natural * MIN_SCALE)}px`;
        node.setAttribute("aria-hidden", "true");
        canvas.current.replaceChildren(node);
        setState("ready");
      })
      .catch(() => current && setState("failed"));
    return () => {
      current = false;
    };
  }, [data.mermaid, dark, raw]);

  // A frame that scrolls has to be reachable by keyboard, and only then.
  useEffect(() => {
    const el = frame.current;
    if (!el || state !== "ready") return;
    const measure = () => setScrolls(el.scrollWidth > el.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [state, view]);

  const title = lang === "he" ? data.title.he : data.title.en;
  const failed = state === "failed";
  const showText = view === "text" || failed;
  const toggle = (name: "diagram" | "text", label: string) => (
    <button
      type="button"
      aria-pressed={view === name}
      onClick={() => setView(name)}
      className={`min-h-9 px-3 py-[5px] ${view === name ? "bg-text text-surface" : "bg-transparent text-text"}`}
    >
      {label}
    </button>
  );

  return (
    <figure className="m-0">
      <figcaption className="mb-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <span className="text-[14px] font-extrabold">{t.diagram}</span>
        <span dir="ltr" lang="en" className="mono text-[11.5px] text-text-muted">Mermaid · EN · LTR</span>
        {!failed && (
          <span role="group" aria-label={t.viewLabel} className="ms-auto flex overflow-hidden rounded-[8px] border border-border text-[13px] font-bold">
            {toggle("diagram", t.viewDiagram)}
            {toggle("text", t.viewText)}
          </span>
        )}
      </figcaption>

      {!failed && (
        <div
          ref={frame}
          hidden={view === "text"}
          tabIndex={scrolls ? 0 : undefined}
          role={scrolls ? "group" : undefined}
          aria-label={scrolls ? t.scroll : undefined}
          dir="ltr"
          className="overflow-x-auto rounded-[12px] border border-border bg-surface-raised p-3"
        >
          {state === "loading" && (
            <p dir="auto" className="flex min-h-40 items-center justify-center gap-2.5 text-ui text-text-muted">
              <SpinnerIcon />
              {t.loading}
            </p>
          )}
          <div ref={canvas} role="img" aria-label={t.imgLabel.replace("{title}", title)} lang="en" className="[&>svg]:mx-auto [&>svg]:block [&_.edgeLabel_text]:[paint-order:stroke] [&_.edgeLabel_text]:[stroke-width:5px] [&_.edgeLabel_text]:[stroke:var(--surface-raised)]" />
        </div>
      )}

      {failed && <p className="mb-2 text-[13.5px] text-text-muted">{t.failed}</p>}
      {!failed && view === "diagram" && <p className="mt-2 text-[12.5px] leading-[1.6] text-text-muted">{t.note}</p>}

      {/* Always in the page: read once by a screen reader, and shown by the text view. */}
      <ul dir="ltr" lang="en" className={showText ? "m-0 flex list-none flex-col gap-1.5 rounded-[10px] bg-surface-sunken px-3.5 py-2.5 text-start text-[14px] leading-[1.7]" : "sr-only"}>
        {data.text.map((line, i) => <li key={i}>{line}</li>)}
      </ul>
    </figure>
  );
}

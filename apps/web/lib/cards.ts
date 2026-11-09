// S5: a project card and its architecture diagram (docs/07, section 3; ADR-0018). Everything here
// was built on the server from the record, and is still treated as untrusted: it is parsed field
// by field, shown as text, and the SVG Mermaid draws is checked before it joins the page.

export type Title = { he: string; en: string };

export type Metric = { label: string; before?: string; after?: string; value?: string; howMeasured: string };

export type ProjectData = {
  recordId: string;
  title: Title;
  role: string;
  period: string;
  tech: string[];
  metrics: Metric[];
  source: string; // the chunk behind the card
};

export type DiagramData = { recordId: string; title: Title; mermaid: string; text: string[] };

/** One turn shows one project, each kind once (backend/portfolio_agent/tools/cards.py). */
export type Cards = { project?: ProjectData; diagram?: DiagramData };

const str = (v: unknown) => (typeof v === "string" ? v : undefined);
const obj = (v: unknown) =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined;
const strings = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function title(v: unknown): Title | undefined {
  const o = obj(v);
  const en = str(o?.en);
  return en === undefined ? undefined : { en, he: str(o?.he) ?? en };
}

function metrics(v: unknown): Metric[] {
  return (Array.isArray(v) ? v : []).flatMap((m) => {
    const o = obj(m);
    const label = str(o?.label);
    if (!o || label === undefined) return [];
    return [{ label, before: str(o.before), after: str(o.after), value: str(o.value), howMeasured: str(o.how_measured) ?? "" }];
  });
}

function parseProject(data: Record<string, unknown>): ProjectData | undefined {
  const recordId = str(data.record_id);
  const t = title(data.title);
  if (recordId === undefined || t === undefined) return undefined;
  return {
    recordId,
    title: t,
    role: str(data.role) ?? "",
    period: str(data.period) ?? "",
    tech: strings(data.tech),
    metrics: metrics(data.metrics),
    source: str(data.source) ?? "",
  };
}

function parseDiagram(data: Record<string, unknown>): DiagramData | undefined {
  const recordId = str(data.record_id);
  const t = title(data.title);
  const mermaid = str(data.mermaid);
  if (recordId === undefined || t === undefined || mermaid === undefined) return undefined;
  return { recordId, title: t, mermaid, text: strings(data.text) };
}

/** The turn's cards with this event added. Anything malformed leaves them as they were. */
export function addCard(cards: Cards | undefined, kind: unknown, data: unknown): Cards | undefined {
  const d = obj(data);
  if (!d) return cards;
  if (kind === "project") {
    const project = parseProject(d);
    return project ? { ...cards, project } : cards;
  }
  if (kind === "diagram") {
    const diagram = parseDiagram(d);
    return diagram ? { ...cards, diagram } : cards;
  }
  return cards;
}

export type Figure = { from: string; to: string } | { value: string } | null;

/** A metric's number: one value, or before and after. */
export function figureOf(m: Metric): Figure {
  if (m.value) return { value: m.value };
  if (m.before && m.after) return { from: m.before, to: m.after };
  const one = m.after ?? m.before;
  return one ? { value: one } : null;
}

// What Mermaid's flowchart draws with `htmlLabels: false`. No foreignObject, no images, no links.
const TAGS = new Set([
  "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
  "title", "desc", "defs", "marker", "style", "filter", "fedropshadow",
]);

export type SvgNode = {
  tagName: string;
  getAttributeNames(): string[];
  getAttribute(name: string): string | null;
  children: ArrayLike<SvgNode>;
  textContent: string | null;
};

const FORBIDDEN = /javascript:|data:|expression\(|@import|url\(\s*['"]?(?!#)/i;

/** Last check before the drawing joins the page: known elements, no handlers, nothing external. */
export function safeSvg(node: SvgNode): boolean {
  const tag = node.tagName.toLowerCase();
  if (!TAGS.has(tag)) return false;
  if (tag === "style" && FORBIDDEN.test(node.textContent ?? "")) return false;
  for (const name of node.getAttributeNames()) {
    const lower = name.toLowerCase();
    const value = node.getAttribute(name) ?? "";
    if (lower.startsWith("on") || FORBIDDEN.test(value)) return false;
    if ((lower === "href" || lower.endsWith(":href")) && !value.startsWith("#")) return false;
  }
  return Array.from(node.children).every(safeSvg);
}

/** How wide the drawing has to stay for its text to be readable, on a phone too. */
export const MIN_SCALE = 0.75;

// What S3, the trace panel, shows for one answer (docs/08-transparency.md, section 2; US-4.1 to
// US-4.4), built only from the turn's SSE events. Pure and language-free: the panel adds the
// words. Only what happened is here, never anything the model "thought".

import type { Restart, Step, Turn } from "./chat.ts";

const obj = (v: unknown) =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined;
const num = (v: unknown) => (typeof v === "number" ? v : undefined);
const str = (v: unknown) => (typeof v === "string" ? v : undefined);

export type TimelineItem =
  | { kind: "model"; ms?: number; tools: string[]; restart?: Restart }
  | { kind: "answer"; ms?: number; citations: number; restart?: Restart }
  | { kind: "tool_call"; tool: string; ms?: number; method?: string; record?: string }
  | { kind: "tool_result"; tool: string; candidates?: number; selected: number }
  | { kind: "job"; stage: string; ms?: number; capped?: number; dropped?: number }
  | { kind: "card"; tool: string; ms?: number; record?: string; card?: string; error?: string; repeated: boolean;
      tech?: number; metrics?: number; components?: number; edges?: number }
  | { kind: "guard"; blocked: boolean };

export type Row = {
  rank: number; // in fused order, 1 first
  chunkId: string;
  title: string;
  excerpt: string;
  lexical?: number;
  vector?: number;
  rrf?: number;
  rerank?: number;
  selected: boolean;
  cite?: number; // its number in the answer, when it was cited
};

export type Search = { stepId: string; query: string; method?: string; rows: Row[] };

export type Waterfall = {
  total: number;
  setup?: number; // before the model started: the database work
  retrieval?: { start: number; ms: number };
  ttft?: number;
  generation?: { start: number; ms: number };
};

export type TraceEvent =
  | { kind: "fallback"; failed?: string; to?: string; reason?: string }
  | { kind: "dropped"; n: number }
  | { kind: "redacted"; n: number }
  | { kind: "blocked" }
  | { kind: "cached" }
  | { kind: "replay" };

export type TraceView = {
  timeline: TimelineItem[];
  decisions: { tool: string; args: Record<string, unknown> }[];
  searches: Search[];
  waterfall?: Waterfall;
  tokens: { decision: boolean; input: number; output: number; stage?: string }[];
  model?: string;
  promptVersion?: string;
  commit?: string;
  events: TraceEvent[];
};

function citeNumbers(turn: Turn): Map<string, number> {
  const out = new Map<string, number>();
  for (const p of turn.parts) if (p.kind === "cite" && !out.has(p.chunkId)) out.set(p.chunkId, p.index);
  return out;
}

function rows(step: Step, cites: Map<string, number>): Row[] {
  const list = Array.isArray(step.summary?.candidates) ? step.summary.candidates : [];
  return list.flatMap((c, i) => {
    const o = obj(c);
    const chunkId = str(o?.chunk_id);
    if (!o || !chunkId) return [];
    const s = obj(o.scores) ?? {};
    return [{
      rank: i + 1,
      chunkId,
      title: str(o.record_title) ?? chunkId,
      excerpt: str(o.excerpt) ?? "",
      lexical: num(s.lexical),
      vector: num(s.vector),
      rrf: num(s.rrf),
      rerank: num(s.rerank),
      selected: o.selected === true,
      cite: cites.get(chunkId),
    }];
  });
}

export function buildTrace(turn: Turn): TraceView {
  const u = turn.usage ?? {};
  const cites = citeNumbers(turn);
  const restartOf = new Map(turn.restarts.map((r) => [r.stepId, r]));
  const timeline: TimelineItem[] = [];
  const decisions: TraceView["decisions"] = [];
  const searches: Search[] = [];
  const tokens: TraceView["tokens"] = [];
  let beforeTools = 0; // model time before the first tool ran, for the waterfall
  let retrieval: Waterfall["retrieval"];
  let blocked = false;

  for (const step of turn.steps) {
    const s = step.summary ?? {};
    const stage = step.name?.startsWith("job.") ? step.name.slice(4) : undefined;
    if (stage && step.status === "end" && stage !== "requirements") {
      // A stage of the job match pipeline (lib/job.ts): a model call, or the code's enforcement.
      const capped = Array.isArray(s.capped) ? s.capped.length : undefined;
      timeline.push({ kind: "job", stage, ms: step.durationMs, capped, dropped: num(s.dropped) });
      const usage = obj(s.usage);
      if (usage) tokens.push({ decision: false, input: num(usage.input_tokens) ?? 0, output: num(usage.output_tokens) ?? 0, stage });
      if (!retrieval) beforeTools += step.durationMs ?? 0;
    } else if (stage) {
      continue;
    } else if (step.kind === "llm") {
      const tools = Array.isArray(s.tool_calls) ? s.tool_calls.filter((x): x is string => typeof x === "string") : [];
      const restart = restartOf.get(step.id);
      timeline.push(tools.length
        ? { kind: "model", ms: step.durationMs, tools, restart }
        : { kind: "answer", ms: step.durationMs, citations: cites.size, restart });
      const usage = obj(s.usage);
      if (usage) tokens.push({ decision: tools.length > 0, input: num(usage.input_tokens) ?? 0, output: num(usage.output_tokens) ?? 0 });
      if (!retrieval) beforeTools += step.durationMs ?? 0;
    } else if (step.name === "render_card") {
      // Built on the server from the record: the row says that, and what the model chose.
      timeline.push({
        kind: "card", tool: step.name, ms: step.durationMs, record: str(s.record_id) ?? str(step.args?.record_id),
        card: str(s.kind) ?? str(step.args?.kind), error: str(s.error), repeated: s.repeated === true,
        tech: num(s.tech), metrics: num(s.metrics), components: num(s.components), edges: num(s.edges),
      });
      if (step.args) decisions.push({ tool: step.name, args: step.args });
    } else if (step.kind === "tool_call" || step.kind === "tool_result") {
      const tool = step.name ?? "";
      const candidates = rows(step, cites);
      const results = Array.isArray(s.results) ? s.results.length : Array.isArray(s.chunks) ? s.chunks.length : 0;
      timeline.push({ kind: "tool_call", tool, ms: step.durationMs, method: str(s.method), record: str(s.record_id) ?? str(step.args?.id) });
      if (step.kind === "tool_result") {
        timeline.push({ kind: "tool_result", tool, candidates: num(s.candidates_considered), selected: results });
      }
      if (step.args) decisions.push({ tool, args: step.args });
      if (tool === "search_portfolio") {
        searches.push({ stepId: step.id, query: str(s.query_used) ?? str(step.args?.query) ?? "", method: str(s.method), rows: candidates });
      }
      const setup = num(u.setup_ms) ?? 0;
      const ms = step.durationMs ?? 0;
      retrieval = retrieval
        ? { start: retrieval.start, ms: retrieval.ms + ms }
        : { start: setup + beforeTools, ms };
    } else if (step.kind === "guard") {
      blocked = blocked || Boolean(s.blocked);
      if (s.blocked) timeline.push({ kind: "guard", blocked: true });
    }
  }

  const total = num(u.total_ms);
  const ttft = num(u.ttft_ms);
  const waterfall: Waterfall | undefined = total
    ? {
        total,
        setup: num(u.setup_ms),
        retrieval,
        ttft,
        generation: ttft !== undefined && ttft < total ? { start: ttft, ms: total - ttft } : undefined,
      }
    : undefined;

  const events: TraceEvent[] = [
    ...turn.restarts.map((r) => ({ kind: "fallback" as const, failed: r.failed, to: r.to, reason: r.reason })),
    ...(turn.restarts.length === 0 && u.fallback === true ? [{ kind: "fallback" as const }] : []),
    ...(num(u.dropped) ? [{ kind: "dropped" as const, n: num(u.dropped)! }] : []),
    ...(num(u.redacted) ? [{ kind: "redacted" as const, n: num(u.redacted)! }] : []),
    ...(blocked ? [{ kind: "blocked" as const }] : []),
    ...(u.cached === true ? [{ kind: "cached" as const }] : []),
    ...(u.replay === true ? [{ kind: "replay" as const }] : []),
  ];

  return {
    timeline,
    decisions,
    searches,
    waterfall,
    tokens,
    model: str(u.model),
    promptVersion: turn.promptVersion,
    commit: turn.sources.find((x) => x.commit)?.commit,
    events,
  };
}

/** Scores as the table shows them: a dash when the method did not rank the chunk. */
export function score(v: number | undefined, digits: number): string {
  return v === undefined ? "—" : v.toFixed(digits);
}

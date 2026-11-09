// One visitor turn on the client: the SSE events of /api/chat folded into what the screen
// shows (docs/05-architecture.md, section 5). `apply` is pure, so every state the screen can
// be in is a test of a list of events.
//
// - Unknown event types are ignored, so the server can add types without breaking this.
// - A restart (a model failed mid-answer and the next one starts the round over) and the
//   output guard both say how much of what was shown to keep: `replace_from` characters of
//   text and `citations_from` citations. Characters are counted as code points, as Python
//   counts them on the server.
// - A stream that ends without `done` is a disconnect (US-10.5): the text that arrived stays,
//   and `retry` sends the message again with the same idempotency key. If the server saved the
//   answer, it replays it from the database at no cost; the new `meta` starts the turn over.

import { addCard, type Cards } from "./cards.ts";
import { parseReport, type JobReport } from "./job.ts";
import { streamEvents, type SseEvent } from "./sse.ts";

export const MAX_QUESTION = 1000; // US-10.4; the server checks it too

export type Part =
  | { kind: "text"; text: string }
  | { kind: "cite"; index: number; chunkId: string };

export type Step = {
  id: string;
  kind: string; // llm | tool_call | tool_result | guard
  status: string; // start | end | restart
  name?: string;
  args?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  durationMs?: number;
};

export type Source = { chunkId: string; recordTitle: string; section: string; text: string; commit?: string };

/** A model that failed mid-round and the one that started it over (US-4.3). Kept apart from
 * the steps, since the round's `end` replaces the step's summary. */
export type Restart = { stepId: string; failed?: string; to?: string; reason?: string };

export type TurnError = {
  code: string; // the screen is picked by code, never by message
  message: string;
  retryable: boolean;
  limit?: string;
  retryAfter?: number;
};

export type Turn = {
  key: string; // idempotency key, kept across retries
  question: string;
  status: "sending" | "streaming" | "done" | "error";
  conversationId?: string;
  messageId?: string;
  promptVersion?: string;
  parts: Part[];
  steps: Step[];
  restarts: Restart[];
  sources: Source[];
  usage?: Record<string, unknown>;
  error?: TurnError;
  job?: boolean; // sent from the composer's job mode: `question` is a pasted posting
  postingChars?: number; // a restored report no longer has the posting on screen
  report?: JobReport;
  markdown?: string; // the report as a file, made on the server (US-5.3)
  cards?: Cards; // a project card and its diagram (US-6.1, US-6.2)
  restored?: boolean; // opened from the link in a report: no trace, no feedback
};

export const DISCONNECTED: TurnError = {
  code: "disconnected",
  message: "The connection dropped before the answer finished.",
  retryable: true,
};

// Nothing came back at all: the server was not reached, or failed before the answer started.
export const UNREACHABLE: TurnError = {
  code: "unreachable",
  message: "The server could not be reached.",
  retryable: true,
};

export function newKey(): string {
  return crypto.randomUUID().replaceAll("-", "");
}

export function newTurn(question: string, key: string = newKey(), job = false): Turn {
  return { key, question, status: "sending", parts: [], steps: [], restarts: [], sources: [], ...(job ? { job } : {}) };
}

const chars = (s: string) => [...s].length;

/** The answer as plain text, for the screen reader once the stream ends (US-11.3). */
export function plainText(turn: Turn): string {
  return turn.parts.map((p) => (p.kind === "text" ? p.text : `[${p.index}]`)).join("");
}

/** Keep the first `keepChars` characters of text and the first `keepCites` citations. */
export function truncate(parts: Part[], keepChars: number, keepCites: number): Part[] {
  const out: Part[] = [];
  let left = keepChars;
  let cites = keepCites;
  for (const p of parts) {
    if (p.kind === "cite") {
      if (cites-- > 0) out.push(p);
      continue;
    }
    if (left <= 0) continue;
    const n = chars(p.text);
    out.push(n <= left ? p : { kind: "text", text: [...p.text].slice(0, left).join("") });
    left -= Math.min(n, left);
  }
  return out;
}

function appendText(parts: Part[], text: string): Part[] {
  const last = parts.at(-1);
  if (last?.kind === "text") return [...parts.slice(0, -1), { kind: "text", text: last.text + text }];
  return [...parts, { kind: "text", text }];
}

function upsertStep(steps: Step[], step: Step): Step[] {
  const i = steps.findIndex((s) => s.id === step.id);
  if (i === -1) return [...steps, step];
  const merged = { ...steps[i], ...step, args: step.args ?? steps[i].args };
  return steps.map((s, j) => (j === i ? merged : s));
}

const str = (v: unknown) => (typeof v === "string" ? v : undefined);
const num = (v: unknown) => (typeof v === "number" ? v : undefined);
const obj = (v: unknown) =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined;

export function apply(turn: Turn, { event, data }: SseEvent): Turn {
  switch (event) {
    case "meta":
      // A new start, also after a retry: what the dropped stream showed is replaced.
      return {
        ...turn,
        status: "streaming",
        conversationId: str(data.conversation_id) ?? turn.conversationId,
        messageId: str(data.message_id),
        promptVersion: str(data.prompt_version),
        parts: [],
        steps: [],
        restarts: [],
        sources: [],
        usage: undefined,
        error: undefined,
        report: undefined,
        markdown: undefined,
        cards: undefined,
      };
    case "card": {
      const report = data.kind === "job_match" ? parseReport(data.data) : undefined;
      if (report) return { ...turn, report, markdown: str(data.markdown) };
      return { ...turn, cards: addCard(turn.cards, data.kind, data.data) };
    }
    case "token":
      return { ...turn, parts: appendText(turn.parts, str(data.text) ?? "") };
    case "citation": {
      const index = num(data.index);
      const chunkId = str(data.chunk_id);
      if (index === undefined || chunkId === undefined) return turn;
      return { ...turn, parts: [...turn.parts, { kind: "cite", index, chunkId }] };
    }
    case "step": {
      const id = str(data.step_id);
      if (id === undefined) return turn;
      const summary = obj(data.summary);
      const step: Step = {
        id,
        kind: str(data.kind) ?? "",
        status: str(data.status) ?? "",
        name: str(data.name),
        args: obj(data.args),
        summary,
        durationMs: num(data.duration_ms),
      };
      const keepChars = num(summary?.replace_from);
      const parts =
        keepChars === undefined
          ? turn.parts
          : truncate(turn.parts, keepChars, num(summary?.citations_from) ?? 0);
      const restarts =
        step.status === "restart"
          ? [...turn.restarts, { stepId: id, failed: str(summary?.failed), to: str(summary?.to), reason: str(summary?.reason) }]
          : turn.restarts;
      return { ...turn, parts, restarts, steps: upsertStep(turn.steps, step) };
    }
    case "sources": {
      const list = Array.isArray(data.sources) ? data.sources : [];
      const sources = list.flatMap((s) => {
        const o = obj(s);
        const chunkId = str(o?.chunk_id);
        if (!o || chunkId === undefined) return [];
        return [{
          chunkId,
          recordTitle: str(o.record_title) ?? chunkId,
          section: str(o.section) ?? "",
          text: str(o.text) ?? "",
          commit: str(o.commit),
        }];
      });
      return { ...turn, sources };
    }
    case "usage":
      return { ...turn, usage: data };
    case "error":
      return {
        ...turn,
        status: "error",
        error: {
          code: str(data.code) ?? "internal",
          message: str(data.message) ?? "",
          retryable: data.retryable === true,
          limit: str(data.limit),
          retryAfter: num(data.retry_after),
        },
      };
    case "done":
      return turn.status === "error" ? turn : { ...turn, status: "done" };
    default:
      return turn; // contact_draft (M7) and types this client does not know yet
  }
}

/** The stream closed: without `done` (or an error), the turn was cut off. */
export function closed(turn: Turn): Turn {
  if (turn.status === "done" || turn.status === "error") return turn;
  // Still `sending`: this attempt never got its `meta`, so no answer had started.
  const error = turn.status === "sending" ? UNREACHABLE : DISCONNECTED;
  return { ...turn, status: "error", error };
}

export type Send = {
  url?: string;
  conversationId?: string;
  companySlug?: string;
  lang?: "he" | "en"; // the page's: record titles in `sources` come in it
  signal?: AbortSignal;
  stream?: typeof streamEvents; // tests pass recorded events
};

/** Runs one turn and reports every new state. Never throws: a failure is a state. */
export async function run(
  turn: Turn,
  onChange: (t: Turn) => void,
  { url = "/api/chat", conversationId, companySlug, lang, signal, stream = streamEvents }: Send = {},
): Promise<Turn> {
  // A retry starts as `sending` with no error, and keeps the old parts until `meta`.
  let current: Turn = { ...turn, status: "sending", error: undefined };
  const body = JSON.stringify({
    message: turn.question,
    idempotency_key: turn.key,
    ...(conversationId ? { conversation_id: conversationId } : {}),
    ...(companySlug ? { company_slug: companySlug } : {}),
    ...(lang ? { lang } : {}),
    ...(turn.job ? { mode: "job" } : {}),
  });
  try {
    await stream(
      url,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body,
        credentials: "same-origin",
        signal,
      },
      (e) => {
        current = apply(current, e);
        onChange(current);
      },
    );
  } catch {
    // network failure, HTTP error or abort: the same as a stream cut short
  }
  current = closed(current);
  onChange(current);
  return current;
}

/** Sends the same message again, with the same key (US-10.5). The old text stays on screen
 * until the new stream's `meta` replaces it. */
export function retry(turn: Turn, onChange: (t: Turn) => void, opts: Send = {}): Promise<Turn> {
  return run(turn, onChange, { ...opts, conversationId: opts.conversationId ?? turn.conversationId });
}

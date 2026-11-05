import assert from "node:assert/strict";
import { test } from "node:test";

import { apply, newTurn } from "./chat.ts";
import type { SseEvent } from "./sse.ts";
import { buildTrace, score } from "./trace.ts";

const ev = (event: string, data: Record<string, unknown> = {}): SseEvent => ({ event, data: { ...data, v: 1 } });
const fold = (events: SseEvent[]) => events.reduce(apply, newTurn("q", "key-12345"));

const candidate = (id: string, selected: boolean, lexical: number | null, vector: number | null) => ({
  chunk_id: id, record_title: id.split("#")[0], excerpt: `about ${id}`, selected,
  scores: { lexical, vector, rrf: 0.03, rerank: null },
});

// One search and an answer, as the server sends them (backend/portfolio_agent/agent/loop.py).
const TURN = [
  ev("meta", { conversation_id: "c1", message_id: "m1", prompt_version: "system.v1" }),
  ev("step", { step_id: "s1", kind: "llm", status: "start", name: "round 1" }),
  ev("step", { step_id: "s1", kind: "llm", status: "end", name: "round 1", duration_ms: 400,
    summary: { tool_calls: ["search_portfolio"], model: "m", usage: { input_tokens: 900, output_tokens: 30 } } }),
  ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "search_portfolio",
    args: { query: "human review translation" } }),
  ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "search_portfolio", duration_ms: 300,
    summary: { query_used: "human review translation", method: "R3", candidates_considered: 3,
      results: [{ chunk_id: "a#all" }],
      candidates: [candidate("a#all", true, 0.016, 0.81), candidate("b#all", false, null, 0.7),
        candidate("c#all", false, 0.01, null)] } }),
  ev("step", { step_id: "s3", kind: "llm", status: "start", name: "round 2" }),
  ev("token", { text: "Yes" }),
  ev("citation", { chunk_id: "a#all", index: 1 }),
  ev("step", { step_id: "s3", kind: "llm", status: "end", name: "round 2", duration_ms: 600,
    summary: { tool_calls: [], model: "m", usage: { input_tokens: 1500, output_tokens: 90 } } }),
  ev("sources", { sources: [{ chunk_id: "a#all", record_title: "A", section: "all", text: "t", commit: "abc1234" }] }),
  ev("usage", { input_tokens: 2400, output_tokens: 120, ttft_ms: 800, total_ms: 1400, setup_ms: 60,
    model: "openai/gpt-oss-120b", fallback: false, dropped: 0, redacted: 0 }),
  ev("done"),
];

test("the timeline lists every step in order: decision, tool call, its result, the answer", () => {
  const t = buildTrace(fold(TURN));
  assert.deepEqual(t.timeline.map((i) => i.kind), ["model", "tool_call", "tool_result", "answer"]);
  assert.deepEqual(t.timeline[2], { kind: "tool_result", tool: "search_portfolio", candidates: 3, selected: 1 });
  assert.deepEqual(t.timeline[3], { kind: "answer", ms: 600, citations: 1, restart: undefined });
  assert.deepEqual(t.decisions, [{ tool: "search_portfolio", args: { query: "human review translation" } }]);
});

test("every candidate keeps its scores, a dash for a method that did not rank it, and its citation", () => {
  const [search] = buildTrace(fold(TURN)).searches;
  assert.equal(search.method, "R3");
  assert.deepEqual(search.rows.map((r) => [r.rank, r.chunkId, r.selected, r.cite]), [
    [1, "a#all", true, 1], [2, "b#all", false, undefined], [3, "c#all", false, undefined]]);
  assert.equal(score(search.rows[1].lexical, 3), "—");
  assert.equal(score(search.rows[0].vector, 2), "0.81");
});

test("the waterfall places retrieval after the database and the first model call", () => {
  const w = buildTrace(fold(TURN)).waterfall!;
  assert.deepEqual(w, { total: 1400, setup: 60, ttft: 800, retrieval: { start: 460, ms: 300 },
    generation: { start: 800, ms: 600 } });
});

test("tokens per model call, provenance, and no events in a clean answer", () => {
  const t = buildTrace(fold(TURN));
  assert.deepEqual(t.tokens, [{ decision: true, input: 900, output: 30 }, { decision: false, input: 1500, output: 90 }]);
  assert.equal(t.model, "openai/gpt-oss-120b");
  assert.equal(t.promptVersion, "system.v1");
  assert.equal(t.commit, "abc1234");
  assert.deepEqual(t.events, []);
});

test("a fallback keeps who failed and why even though the round's end replaces the step", () => {
  const t = buildTrace(fold([
    ev("meta", { message_id: "m1" }),
    ev("step", { step_id: "s1", kind: "llm", status: "start", name: "round 1" }),
    ev("step", { step_id: "s1", kind: "llm", status: "restart",
      summary: { failed: "gpt-oss-120b", to: "gpt-oss-20b", reason: "timeout", replace_from: 0, citations_from: 0 } }),
    ev("step", { step_id: "s1", kind: "llm", status: "end", duration_ms: 900, summary: { tool_calls: [] } }),
    ev("usage", { total_ms: 900, fallback: true, dropped: 2, redacted: 1 }),
    ev("done"),
  ]));
  assert.deepEqual(t.events, [
    { kind: "fallback", failed: "gpt-oss-120b", to: "gpt-oss-20b", reason: "timeout" },
    { kind: "dropped", n: 2 }, { kind: "redacted", n: 1 }]);
  assert.equal(t.timeline[0].kind === "answer" && t.timeline[0].restart?.to, "gpt-oss-20b");
});

test("a cached answer says so, and a step still streaming is already on the timeline", () => {
  const cached = buildTrace(fold([ev("meta", { message_id: "m1", cached: true }), ev("usage", { cached: true, total_ms: 5 }), ev("done")]));
  assert.deepEqual(cached.events, [{ kind: "cached" }]);
  const running = buildTrace(fold(TURN.slice(0, 4)));
  assert.deepEqual(running.timeline.map((i) => i.kind), ["model", "tool_call"]);
});

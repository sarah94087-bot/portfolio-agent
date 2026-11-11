// node --test (Node strips the types itself, so no test dependency is needed)
import assert from "node:assert/strict";
import { test } from "node:test";

import { apply, closed, newTurn, plainText, retry, run, truncate, type Turn } from "./chat.ts";
import { createFrameParser, type SseEvent } from "./sse.ts";

const ev = (event: string, data: Record<string, unknown> = {}): SseEvent => ({
  event,
  data: { ...data, v: 1 },
});
const fold = (events: SseEvent[], turn: Turn = newTurn("q", "key-12345")) =>
  events.reduce(apply, turn);

const ANSWER = [
  ev("meta", { conversation_id: "c1", message_id: "m1" }),
  ev("step", { step_id: "s1", kind: "llm", status: "start", name: "round 1" }),
  ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "search_portfolio",
    args: { query: "translation" } }),
  ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "search_portfolio",
    summary: { hits: 3 }, duration_ms: 120 }),
  ev("token", { text: "שרה בנתה " }),
  ev("token", { text: "pipeline תרגום" }),
  ev("citation", { chunk_id: "human-gated-translation#all", index: 1 }),
  ev("token", { text: "." }),
  ev("sources", { sources: [{ chunk_id: "human-gated-translation#all",
    record_title: "Human-gated translation", section: "all", text: "src" }] }),
  ev("usage", { input_tokens: 900, output_tokens: 40, ttft_ms: 800 }),
  ev("done"),
];

test("a full answer: text, citation, steps merged by id, sources, usage", () => {
  const t = fold(ANSWER);
  assert.equal(t.status, "done");
  assert.equal(t.conversationId, "c1");
  assert.equal(plainText(t), "שרה בנתה pipeline תרגום[1].");
  assert.deepEqual(t.steps.map((s) => [s.id, s.kind, s.status]), [
    ["s1", "llm", "start"],
    ["s2", "tool_result", "end"],
  ]);
  assert.deepEqual(t.steps[1].args, { query: "translation" }); // kept from tool_call
  assert.equal(t.steps[1].durationMs, 120);
  assert.equal(t.sources[0].recordTitle, "Human-gated translation");
  assert.equal(t.usage?.output_tokens, 40);
});

test("a restart cuts the text and citations back to what the round started from", () => {
  const t = fold([
    ev("meta", { conversation_id: "c1", message_id: "m1" }),
    ev("token", { text: "first round. " }),
    ev("citation", { chunk_id: "a#all", index: 1 }),
    ev("token", { text: "second round, cut" }),
    ev("citation", { chunk_id: "b#all", index: 2 }),
    ev("step", { step_id: "s3", kind: "llm", status: "restart",
      summary: { replace_from: 13, citations_from: 1, failed: "x", to: "y" } }),
    ev("token", { text: "second round again" }),
  ]);
  assert.equal(plainText(t), "first round. [1]second round again");
});

test("the output guard replaces everything shown with its safe text", () => {
  const t = fold([
    ev("meta", { conversation_id: "c1", message_id: "m1" }),
    ev("token", { text: "leaking" }),
    ev("citation", { chunk_id: "a#all", index: 1 }),
    ev("step", { step_id: "guard", kind: "guard", status: "end", name: "output_guard",
      summary: { blocked: "canary", replace_from: 0, citations_from: 0 } }),
    ev("token", { text: "I can't answer that." }),
    ev("done"),
  ]);
  assert.equal(plainText(t), "I can't answer that.");
});

test("a citation revision replaces the uncited answer and is not shown as a fallback", () => {
  // ADR-0021: the revision round opens with replace_from on its start step.
  const t = fold([
    ev("meta", { conversation_id: "c1", message_id: "m1" }),
    ev("token", { text: "an answer with no sources" }),
    ev("step", { step_id: "s4", kind: "llm", status: "start", name: "round 3",
      summary: { reason: "uncited", replace_from: 0, citations_from: 0 } }),
    ev("token", { text: "She built it." }),
    ev("citation", { chunk_id: "a#all", index: 1 }),
    ev("done"),
  ]);
  assert.equal(plainText(t), "She built it.[1]");
  assert.deepEqual(t.restarts, []);
});

test("characters are counted as code points, as Python counts them", () => {
  const parts = [{ kind: "text" as const, text: "a😀b" }];
  assert.deepEqual(truncate(parts, 2, 0), [{ kind: "text", text: "a😀" }]);
});

test("an error keeps its code, limit and wait, and done does not hide it", () => {
  const t = fold([
    ev("error", { code: "rate_limited", message: "Too many", retryable: true,
      limit: "minute", retry_after: 40 }),
    ev("done"),
  ]);
  assert.equal(t.status, "error");
  assert.deepEqual(t.error, { code: "rate_limited", message: "Too many", retryable: true,
    limit: "minute", retryAfter: 40 });
});

test("unknown events and malformed ones change nothing", () => {
  const t = fold([ev("meta", { message_id: "m1" }), ev("token", { text: "hi" })]);
  for (const e of [ev("card", { kind: "project" }), ev("future_event"),
    ev("citation", { index: 1 }), ev("step", { kind: "llm" })]) {
    assert.deepEqual(apply(t, e), t);
  }
});

test("a stream cut before done is a retryable disconnect, and the text stays", () => {
  const t = closed(fold(ANSWER.slice(0, 6)));
  assert.equal(t.status, "error");
  assert.equal(t.error?.code, "disconnected");
  assert.equal(t.error?.retryable, true);
  assert.equal(plainText(t), "שרה בנתה pipeline תרגום");
});

const recorded = (events: SseEvent[], fail = false) => {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  const stream = async (url: string, init: RequestInit, onEvent: (e: SseEvent) => void) => {
    calls.push({ url, body: JSON.parse(String(init.body)) });
    events.forEach(onEvent);
    if (fail) throw new TypeError("network error");
  };
  return { calls, stream };
};

test("retry sends the same key and conversation, keeps the old text until meta, then replaces it", async () => {
  const first = recorded(ANSWER.slice(0, 6), true);
  const cut = await run(newTurn("q", "key-12345"), () => {}, { stream: first.stream });
  assert.equal(cut.error?.code, "disconnected");

  const states: Turn[] = [];
  const second = recorded(ANSWER);
  const done = await retry(cut, (t) => states.push(t), { stream: second.stream });
  assert.deepEqual(second.calls[0].body, { message: "q", idempotency_key: "key-12345",
    conversation_id: "c1" });
  assert.equal(done.status, "done");
  assert.equal(plainText(done), "שרה בנתה pipeline תרגום[1].");
  // the first state of the retry is the meta: the old text was on screen until then
  assert.equal(states[0].parts.length, 0);
  assert.equal(states[0].status, "streaming");
});

test("a first message sends no conversation id; a server not reached is a state, never a throw", async () => {
  const failing = recorded([], true);
  const t = await run(newTurn("שאלה", "key-abcdef"), () => {}, { stream: failing.stream,
    companySlug: "acme", lang: "he" });
  assert.deepEqual(failing.calls[0].body, { message: "שאלה", idempotency_key: "key-abcdef",
    company_slug: "acme", lang: "he" });
  assert.equal(t.error?.code, "unreachable"); // nothing came back: not a cut answer
  assert.equal(t.error?.retryable, true);
});

test("a retry that cannot reach the server says so, and keeps the text the first try showed", async () => {
  const cut = await run(newTurn("q", "key-12345"), () => {}, {
    stream: recorded(ANSWER.slice(0, 6), true).stream });
  const again = await retry(cut, () => {}, { stream: recorded([], true).stream });
  assert.equal(again.error?.code, "unreachable");
  assert.equal(plainText(again), "שרה בנתה pipeline תרגום");
});

test("frames split anywhere, even inside a Hebrew word, parse to the same events", () => {
  const wire = 'event: token\ndata: {"text":"שלום","v":1}\n\nevent: done\ndata: {"v":1}\n\n';
  for (let cut = 1; cut < wire.length; cut++) {
    const got: SseEvent[] = [];
    const feed = createFrameParser((e) => got.push(e));
    feed(wire.slice(0, cut));
    feed(wire.slice(cut));
    assert.deepEqual(got.map((e) => e.event), ["token", "done"]);
    assert.equal(got[0].data.text, "שלום");
  }
});

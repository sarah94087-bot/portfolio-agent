import assert from "node:assert/strict";
import { test } from "node:test";

import { apply, newTurn, run, type Step, type Turn } from "./chat.ts";
import { gapsOf, jobStages, parseReport, reportFile, sourceNumbers } from "./job.ts";
import { buildTrace } from "./trace.ts";
import type { SseEvent } from "./sse.ts";

const REQ = {
  id: "r1", text: "Python", kind: "must", strength: "strong", evidence: ["a#all", "b#all"],
  rationale: "Shown.", cv_only: false, years_required: null, years_covered: null,
};
const DATA = {
  role_title: "Backend Engineer", overall: "partial", summary: "Partly.",
  requirements: [
    REQ,
    { ...REQ, id: "r2", text: "Team lead", kind: "nice", strength: "none", evidence: [] },
    { ...REQ, id: "r3", text: "K8s", strength: "partial", evidence: ["b#all"], cv_only: true, years_required: 5, years_covered: 2 },
    { ...REQ, id: "r4", text: "Go", strength: "none", evidence: [] },
  ],
};
const ev = (event: string, data: Record<string, unknown> = {}): SseEvent => ({ event, data: { ...data, v: 1 } });

test("a report is read from its card", () => {
  const r = parseReport(DATA)!;
  assert.equal(r.roleTitle, "Backend Engineer");
  assert.equal(r.requirements[2].cvOnly, true);
  assert.equal(r.requirements[2].yearsRequired, 5);
  assert.equal(r.requirements[0].yearsCovered, null);
});

test("a malformed card is dropped, not half shown", () => {
  assert.equal(parseReport({ ...DATA, overall: "95%" }), undefined);
  assert.equal(parseReport({ ...DATA, requirements: [{ ...REQ, strength: "perfect" }] }), undefined);
  assert.equal(parseReport({ ...DATA, requirements: "x" }), undefined);
  assert.equal(parseReport(null), undefined);
});

test("gaps put the musts first whatever their order", () => {
  assert.deepEqual(gapsOf(parseReport(DATA)!).map((g) => g.text), ["Go", "Team lead"]);
});

test("sources are numbered by first citation, like the Markdown", () => {
  assert.deepEqual([...sourceNumbers(parseReport(DATA)!)], [["a#all", 1], ["b#all", 2]]);
});

test("the file name is ASCII in every language", () => {
  const he = { ...parseReport(DATA)!, roleTitle: "מפתחת Backend בכירה" };
  assert.equal(reportFile(he, "2026-11-08", "md"), "job-match-backend-2026-11-08.md");
  assert.equal(reportFile({ ...he, roleTitle: "מפתחת" }, "2026-11-08", "md"), "job-match-2026-11-08.md");
});

const step = (name: string, status: string, summary?: Record<string, unknown>, kind = "llm"): Step =>
  ({ id: `${name}-${status}`, kind, status, name, summary });

test("the four stages follow the steps", () => {
  const steps: Step[] = [step("job.extract", "start")];
  const states = (s: Step[]) => jobStages(s).map((x) => x.state).join(" ");
  assert.equal(states(steps), "run wait wait wait");

  steps.push(step("job.extract", "end"), step("job.requirements", "end", { count: 2 }, "job"));
  assert.equal(states(steps), "done run wait wait");
  assert.deepEqual(jobStages(steps)[0], { key: "extract", state: "done", total: 2 });
  assert.deepEqual(jobStages(steps)[1], { key: "evidence", state: "run", done: 0, total: 2 });

  steps.push(step("search_portfolio", "end", {}, "tool_result"));
  assert.equal(jobStages(steps)[1].done, 1);
  steps.push({ ...step("search_portfolio", "end", {}, "tool_result"), id: "second" });
  assert.equal(states(steps), "done done run wait");

  steps.push(step("job.rate", "end"));
  assert.equal(states(steps), "done done done run");
  steps.push(step("job.summary", "end"));
  assert.equal(states(steps), "done done done done");
});

test("a card becomes the turn's report, and a new start clears it", () => {
  const start = newTurn("posting", "key-12345", true);
  assert.equal(start.job, true);
  const card = ev("card", { kind: "job_match", data: DATA, markdown: "# r" });
  const turn = [ev("meta", { message_id: "m" }), card, ev("done")].reduce(apply, start);
  assert.equal(turn.report?.overall, "partial");
  assert.equal(turn.markdown, "# r");
  assert.equal(turn.status, "done");
  assert.equal(apply(turn, ev("meta", { message_id: "m2" })).report, undefined);
});

test("another kind of card does not touch the report", () => {
  assert.equal(apply(newTurn("q", "key-12345"), ev("card", { kind: "project", data: {} })).report, undefined);
});

test("a job turn asks for job mode, and a question does not", async () => {
  const bodies: Record<string, unknown>[] = [];
  const stream = (async (_url: string, init: RequestInit) => {
    bodies.push(JSON.parse(String(init.body)));
  }) as never;
  await run(newTurn("posting", "key-12345", true), () => {}, { stream });
  await run(newTurn("question", "key-67890"), () => {}, { stream });
  assert.equal(bodies[0].mode, "job");
  assert.equal("mode" in bodies[1], false);
});

test("the trace names the job stages and their tokens", () => {
  const usage = { input_tokens: 900, output_tokens: 50 };
  const turn: Turn = {
    ...newTurn("p", "key-12345", true),
    steps: [
      { ...step("job.extract", "end", { usage, tool_calls: [] }), durationMs: 700 },
      step("job.requirements", "end", { count: 1 }, "job"),
      { ...step("search_portfolio", "end", { query_used: "Python", method: "R3", candidates_considered: 9, results: [{}], candidates: [] }, "tool_result"), args: { query: "Python" } },
      { ...step("job.rate", "end", { usage, tool_calls: [] }), durationMs: 900 },
      step("job.enforce", "end", { capped: ["r1"], dropped: 2 }, "job"),
      step("job.summary", "end", { usage, tool_calls: [] }),
    ],
  };
  const view = buildTrace(turn);
  assert.deepEqual(
    view.timeline.filter((x) => x.kind === "job").map((x) => x.kind === "job" && x.stage),
    ["extract", "rate", "enforce", "summary"],
  );
  assert.deepEqual(view.tokens.map((t) => t.stage), ["extract", "rate", "summary"]);
  const enforce = view.timeline.find((x) => x.kind === "job" && x.stage === "enforce");
  assert.ok(enforce?.kind === "job" && enforce.capped === 1 && enforce.dropped === 2);
  assert.equal(view.searches.length, 1);
});

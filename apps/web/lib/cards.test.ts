import assert from "node:assert/strict";
import { test } from "node:test";

import { addCard, figureOf, safeSvg, type SvgNode } from "./cards.ts";
import { apply, newTurn } from "./chat.ts";
import { buildTrace } from "./trace.ts";

const ev = (event: string, data: Record<string, unknown> = {}) => ({ event, data: { ...data, v: 1 } });

const PROJECT = {
  record_id: "p", title: { en: "Title", he: "כותרת" }, role: "Engineer", period: "2026", tech: ["Python", 3],
  metrics: [{ label: "Recall", before: "0.4", after: "0.8", how_measured: "On D1" }, { nope: true }], source: "p#all",
};
const DIAGRAM = { record_id: "p", title: { en: "Title", he: "כותרת" }, mermaid: "flowchart TB", text: ["Components: A."] };

test("a project card and its diagram are kept together on the turn", () => {
  let turn = apply(newTurn("q", "key-12345"), ev("meta", { message_id: "m" }));
  turn = apply(turn, ev("card", { kind: "project", data: PROJECT }));
  turn = apply(turn, ev("card", { kind: "diagram", data: DIAGRAM }));
  assert.equal(turn.cards?.project?.role, "Engineer");
  assert.deepEqual(turn.cards?.project?.tech, ["Python"]);
  assert.equal(turn.cards?.project?.metrics.length, 1);
  assert.equal(turn.cards?.diagram?.mermaid, "flowchart TB");
  assert.equal(turn.report, undefined);
});

test("a new start clears the cards of the attempt before it", () => {
  let turn = apply(newTurn("q", "key-12345"), ev("card", { kind: "project", data: PROJECT }));
  turn = apply(turn, ev("meta", { message_id: "m" }));
  assert.equal(turn.cards, undefined);
});

test("a malformed card or an unknown kind changes nothing", () => {
  assert.equal(addCard(undefined, "project", { title: "x" }), undefined);
  assert.equal(addCard(undefined, "diagram", { record_id: "p", title: { en: "t" } }), undefined);
  assert.equal(addCard(undefined, "future", PROJECT), undefined);
  assert.equal(addCard(undefined, "project", "text"), undefined);
});

test("a metric shows its value, or before and after", () => {
  const m = { label: "l", howMeasured: "h" };
  assert.deepEqual(figureOf({ ...m, value: "5" }), { value: "5" });
  assert.deepEqual(figureOf({ ...m, before: "1", after: "2" }), { from: "1", to: "2" });
  assert.deepEqual(figureOf({ ...m, after: "2" }), { value: "2" });
  assert.equal(figureOf(m), null);
});

const el = (tagName: string, attrs: Record<string, string> = {}, children: SvgNode[] = [], textContent = ""): SvgNode => ({
  tagName,
  textContent,
  children,
  getAttributeNames: () => Object.keys(attrs),
  getAttribute: (n) => attrs[n] ?? null,
});

test("a plain drawing passes the check", () => {
  assert.ok(safeSvg(el("svg", { viewBox: "0 0 1 1" }, [
    el("style", {}, [], ".a{fill:red}"),
    el("g", {}, [el("path", { d: "M0 0", "marker-end": "url(#arrow)" }), el("text", {}, [el("tspan")])]),
  ])));
});

for (const [name, node] of [
  ["a script", el("svg", {}, [el("script")])],
  ["a foreignObject", el("svg", {}, [el("foreignObject")])],
  ["an image", el("svg", {}, [el("image", { href: "x" })])],
  ["a link", el("svg", {}, [el("a")])],
  ["a handler", el("svg", { onload: "x()" })],
  ["a handler in any case", el("svg", {}, [el("g", { OnClick: "x()" })])],
  ["a javascript address", el("svg", {}, [el("use", { href: "javascript:x" })])],
  ["an outside reference", el("svg", {}, [el("path", { "xlink:href": "https://x/y" })])],
  ["an outside fill", el("svg", {}, [el("path", { fill: "url(https://x/y)" })])],
  ["an import in the styles", el("svg", {}, [el("style", {}, [], "@import 'https://x/y';")])],
  ["a data address in the styles", el("svg", {}, [el("style", {}, [], "a{background:url(data:x)}")])],
] as const) {
  test(`a drawing with ${name} is refused`, () => assert.equal(safeSvg(node), false));
}

test("the trace shows a card with what it was built from, and the model's choice", () => {
  let turn = apply(newTurn("q", "key-12345"), ev("meta", { message_id: "m" }));
  turn = apply(turn, ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "render_card", args: { record_id: "p", kind: "diagram" } }));
  turn = apply(turn, ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "render_card", duration_ms: 3,
    summary: { record_id: "p", kind: "diagram", built_from: "frontmatter", components: 4, edges: 3 } }));
  const view = buildTrace(turn);
  assert.deepEqual(view.timeline, [{ kind: "card", tool: "render_card", ms: 3, record: "p", card: "diagram", error: undefined,
    repeated: false, tech: undefined, metrics: undefined, components: 4, edges: 3 }]);
  assert.deepEqual(view.decisions, [{ tool: "render_card", args: { record_id: "p", kind: "diagram" } }]);
  assert.equal(view.searches.length, 0);
});

test("a refused card is in the trace as refused", () => {
  const turn = apply(newTurn("q", "key-12345"), ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "render_card",
    args: { record_id: "p", kind: "project" }, summary: { error: "not_retrieved" } }));
  const [item] = buildTrace(turn).timeline;
  assert.ok(item.kind === "card" && item.error === "not_retrieved" && item.record === "p");
});

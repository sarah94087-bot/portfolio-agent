import assert from "node:assert/strict";
import { test } from "node:test";

import { blocks, runs, spoken } from "./answer.ts";
import type { Part } from "./chat.ts";

const t = (text: string): Part => ({ kind: "text", text });
const c = (index: number): Part => ({ kind: "cite", index, chunkId: `r${index}#all` });

const shape = (parts: Part[]) =>
  blocks(parts).map((b) => [b.kind, b.inlines.map((i) =>
    i.kind === "text" ? (i.bold ? `*${i.text}*` : i.text) : i.kind === "cite" ? `[${i.index}]` : "|")
    .join("")]);

test("paragraphs split on a blank line, even across tokens; a single newline is a break", () => {
  assert.deepEqual(shape([t("one\nstill one\n"), t("\ntwo"), c(1)]), [
    ["p", "one|still one"],
    ["p", "two[1]"],
  ]);
});

test("list items and headings, with their markers removed", () => {
  assert.deepEqual(shape([t("Projects:\n- first "), c(1), t("\n2. second\n### Title")]), [
    ["p", "Projects:"],
    ["li", "first [1]"],
    ["li", "second"],
    ["h", "Title"],
  ]);
});

test("bold across tokens, and an unclosed marker stays text while streaming", () => {
  assert.deepEqual(shape([t("the **pro"), t("ject** is")]), [["p", "the *project* is"]]);
  assert.deepEqual(shape([t("the **proj")]), [["p", "the **proj"]]);
});

test("Latin words and numbers inside Hebrew are separate runs", () => {
  assert.deepEqual(runs("השתמשה ב-pgvector ו-Recall@5 עלה ל-0.96."), [
    { text: "השתמשה ב-", latin: false },
    { text: "pgvector", latin: true },
    { text: " ו-", latin: false },
    { text: "Recall@5", latin: true },
    { text: " עלה ל-", latin: false },
    { text: "0.96.", latin: true },
    ]);
  assert.deepEqual(runs("פרויקט Human-gated translation"), [
    { text: "פרויקט ", latin: false },
    { text: "Human-gated translation", latin: true },
  ]);
});

test("the spoken answer has no Markdown and names each citation", () => {
  assert.equal(spoken([t("the **project** is"), c(1), t("\n\n- one\n- two")]),
    "the project is [1]\none\ntwo");
});

test("an empty answer has no blocks", () => {
  assert.deepEqual(blocks([]), []);
  assert.deepEqual(blocks([t("\n\n")]), []);
});

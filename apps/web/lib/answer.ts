// The answer's text and citations as blocks the screen renders: paragraphs, list items and
// bold, from the little Markdown the model writes. Pure, so a half-streamed answer renders the
// same way every time; an unclosed ** stays as it is until its pair arrives.

import type { Part } from "./chat.ts";

export type Inline =
  | { kind: "text"; text: string; bold: boolean }
  | { kind: "break" }
  | { kind: "cite"; index: number; chunkId: string };

export type Block = { kind: "p" | "li" | "h"; inlines: Inline[] };

const LIST = /^\s*(?:[-*•]|\d+[.)])\s+/;
const HEADING = /^\s*#{1,6}\s+/;

/** Lines of the answer, each a list of text and citation pieces. */
function lines(parts: Part[]): (Part[] | null)[] {
  const out: (Part[] | null)[] = [[]]; // null marks a blank line
  for (const p of parts) {
    if (p.kind === "cite") {
      let last = out.at(-1);
      if (last === null || last === undefined) out.push((last = []));
      last.push(p);
      continue;
    }
    p.text.split("\n").forEach((piece, i) => {
      if (i > 0) out.push([]);
      let last = out.at(-1);
      if (last === null || last === undefined) out.push((last = []));
      if (piece) last.push({ kind: "text", text: piece });
    });
  }
  return out.map((l) =>
    l && l.every((p) => p.kind === "text" && !p.text.trim()) ? null : l,
  );
}

function strip(line: Part[], pattern: RegExp): Part[] {
  const [first, ...rest] = line;
  if (first?.kind !== "text") return line;
  const text = first.text.replace(pattern, "");
  return text ? [{ kind: "text", text }, ...rest] : rest;
}

function bold(pieces: Part[]): Inline[] {
  // Count the markers first: an odd last one is not closed yet, and is shown as text.
  const markers = pieces.reduce(
    (n, p) => n + (p.kind === "text" ? p.text.split("**").length - 1 : 0), 0);
  let usable = markers - (markers % 2);
  let on = false;
  const out: Inline[] = [];
  for (const p of pieces) {
    if (p.kind === "cite") {
      out.push(p);
      continue;
    }
    const segments = p.text.split("**");
    segments.forEach((seg, i) => {
      if (i > 0) {
        if (usable > 0) {
          usable--;
          on = !on;
        } else {
          seg = "**" + seg;
        }
      }
      if (!seg) return;
      const last = out.at(-1);
      if (last?.kind === "text" && last.bold === on) last.text += seg;
      else out.push({ kind: "text", text: seg, bold: on });
    });
  }
  return out;
}

export function blocks(parts: Part[]): Block[] {
  const out: Block[] = [];
  let para: Part[][] = [];
  const flush = () => {
    if (para.length) {
      const inlines: Inline[] = [];
      para.forEach((line, i) => {
        if (i > 0) inlines.push({ kind: "break" });
        inlines.push(...bold(line));
      });
      out.push({ kind: "p", inlines });
    }
    para = [];
  };
  for (const line of lines(parts)) {
    if (line === null || line.length === 0) {
      flush();
      continue;
    }
    const first = line[0];
    const text = first.kind === "text" ? first.text : "";
    if (LIST.test(text)) {
      flush();
      out.push({ kind: "li", inlines: bold(strip(line, LIST)) });
    } else if (HEADING.test(text)) {
      flush();
      out.push({ kind: "h", inlines: bold(strip(line, HEADING)) });
    } else {
      para.push(line);
    }
  }
  flush();
  return out;
}

/** What the screen reader hears once the answer ends: the text without Markdown, a citation as
 * its number in brackets, a block per line. */
export function spoken(parts: Part[]): string {
  return blocks(parts)
    .map((b) => b.inlines.map((i) =>
      i.kind === "text" ? i.text : i.kind === "cite" ? ` [${i.index}]` : " ").join(""))
    .join("\n");
}

// Latin words and numbers inside Hebrew are isolated, so "ב-pgvector" and "Recall@5" keep
// their order (the design's <bdi>). A run may hold several words: "Human-gated translation".
const LATIN = /[A-Za-z0-9][\w@.\-/+#:%]*(?:[ ]+[A-Za-z0-9][\w@.\-/+#:%]*)*/g;

export type Run = { text: string; latin: boolean };

export function runs(text: string): Run[] {
  const out: Run[] = [];
  let at = 0;
  for (const m of text.matchAll(LATIN)) {
    if (m.index > at) out.push({ text: text.slice(at, m.index), latin: false });
    out.push({ text: m[0], latin: true });
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push({ text: text.slice(at), latin: false });
  return out;
}

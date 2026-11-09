// Answers as the server streams them, event for event (backend/portfolio_agent/agent/loop.py,
// citations.py, chat.py; docs/05-architecture.md, section 5). The content is written for the
// tests, so nothing here depends on a model or on the knowledge base.

import type { Frame, Item } from "./fixtures";

export const ev = (event: string, data: Record<string, unknown> = {}): Frame => ({ event, data });

export const CONVERSATION = "11111111-2222-4333-8444-555555555555";
export const MESSAGE = "99999999-8888-4777-8666-555555555555";

export const COMMIT = "abc1234def5678";

export const meta = (messageId = MESSAGE) =>
  ev("meta", { conversation_id: CONVERSATION, message_id: messageId, model: "openai/gpt-oss-120b", prompt_version: "system.v1" });

type Lang = "he" | "en";

export const TEXT = {
  he: {
    question: "מה הפרויקט הכי מורכב שלה?",
    before: "הפרויקט המורכב ביותר הוא ",
    term: "pgvector",
    after: " עם חיפוש היברידי",
    second: " ובדיקה אנושית של כל תרגום.",
    title: "מערכת תרגום",
    source: "שרה בנתה מערכת תרגום עם **בדיקה אנושית** לפני פרסום.\n\nהמערכת רצה ב-pgvector.",
    sourceTwo: "המערכת נבדקת על 200 שאלות בכל שינוי.",
    titleTwo: "הערכת איכות",
  },
  en: {
    question: "What is her most complex project?",
    before: "Her most complex project is built on ",
    term: "pgvector",
    after: " with hybrid search",
    second: " and human review of every translation.",
    title: "Translation system",
    source: "Sarah built a translation system with **human review** before publishing.\n\nIt runs on pgvector.",
    sourceTwo: "The system is checked against 200 questions on every change.",
    titleTwo: "Quality evaluation",
  },
} as const;

/** What the answer says once it is complete, without Markdown. */
export const answerText = (lang: Lang) => {
  const t = TEXT[lang];
  return `${t.before}${t.term}${t.after}`;
};

const candidates = (lang: Lang, n = 11) =>
  Array.from({ length: n }, (_, i) => ({
    chunk_id: i === 0 ? "translation#all" : i === 1 ? "evals#all" : `other-${i}#all`,
    record_title: i === 0 ? TEXT[lang].title : i === 1 ? TEXT[lang].titleTwo : `Record ${i}`,
    excerpt: i === 0 ? TEXT[lang].source.slice(0, 60) : `excerpt number ${i}`,
    selected: i < 2,
    scores: { lexical: i % 3 === 2 ? null : 0.031 - i / 1000, vector: 0.81 - i / 100, rrf: 0.033 - i / 1000, rerank: null },
  }));

export const searchSteps = (lang: Lang): Frame[] => [
  ev("step", { step_id: "s1", kind: "llm", status: "start", name: "round 1" }),
  ev("step", { step_id: "s1", kind: "llm", status: "end", name: "round 1", duration_ms: 412,
    summary: { tool_calls: ["search_portfolio"], model: "openai/gpt-oss-120b", usage: { input_tokens: 900, output_tokens: 31 } } }),
  ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "search_portfolio", args: { query: "complex project translation" } }),
  ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "search_portfolio", duration_ms: 305,
    summary: { query_used: "complex project translation", method: "R3", candidates_considered: 11,
      results: [{ chunk_id: "translation#all" }, { chunk_id: "evals#all" }], candidates: candidates(lang) } }),
  ev("step", { step_id: "s3", kind: "llm", status: "start", name: "round 2" }),
];

export const closing = (lang: Lang, usage: Record<string, unknown> = {}): Frame[] => [
  ev("step", { step_id: "s3", kind: "llm", status: "end", name: "round 2", duration_ms: 640,
    summary: { tool_calls: [], model: "openai/gpt-oss-120b", usage: { input_tokens: 1500, output_tokens: 92 } } }),
  ev("sources", { sources: [
    { chunk_id: "translation#all", record_title: TEXT[lang].title, section: "all", text: TEXT[lang].source, commit: COMMIT },
    { chunk_id: "evals#all", record_title: TEXT[lang].titleTwo, section: "all", text: TEXT[lang].sourceTwo, commit: COMMIT },
  ] }),
  ev("usage", { input_tokens: 2400, output_tokens: 123, ttft_ms: 820, total_ms: 1430, setup_ms: 61,
    model: "openai/gpt-oss-120b", fallback: false, dropped: 0, redacted: 0, ...usage }),
  ev("done"),
];

/** The token stream of the answer, in small pieces, with its two citations. */
export const tokens = (lang: Lang): Frame[] => {
  const t = TEXT[lang];
  const pieces = [t.before, t.term, t.after];
  return [
    ...pieces.map((text) => ev("token", { text })),
    ev("citation", { chunk_id: "translation#all", index: 1 }),
    ev("token", { text: t.second }),
    ev("citation", { chunk_id: "evals#all", index: 2 }),
  ];
};

export const answer = (lang: Lang = "he", usage: Record<string, unknown> = {}): Frame[] => [
  meta(),
  ...searchSteps(lang),
  ...tokens(lang),
  ...closing(lang, usage),
];

/** A second answer in the same conversation, without tools. */
export const shortAnswer = (text: string, messageId = "22222222-8888-4777-8666-555555555555"): Frame[] => [
  meta(messageId),
  ev("step", { step_id: "s1", kind: "llm", status: "start", name: "round 1" }),
  ev("token", { text }),
  ev("step", { step_id: "s1", kind: "llm", status: "end", name: "round 1", duration_ms: 100,
    summary: { tool_calls: [], model: "openai/gpt-oss-120b", usage: { input_tokens: 10, output_tokens: 5 } } }),
  ev("usage", { input_tokens: 10, output_tokens: 5, ttft_ms: 50, total_ms: 150, model: "openai/gpt-oss-120b", fallback: false, dropped: 0, redacted: 0 }),
  ev("done"),
];

/** The primary model fails mid-answer; the fallback starts the round over (US-4.3, US-10.1). */
export const fallback = (lang: Lang = "he"): Item[] => [
  meta(),
  ...searchSteps(lang),
  ev("token", { text: "טקסט של המודל שנפל" }),
  ev("step", { step_id: "s3", kind: "llm", status: "restart", name: "round 2",
    summary: { failed: "openai/gpt-oss-120b", to: "llama-3.3-70b", reason: "rate_limit", replace_from: 0, citations_from: 0 } }),
  ...tokens(lang),
  ...closing(lang, { fallback: true, model: "llama-3.3-70b" }),
];

export const failure = (code: string, retryable: boolean, extra: Record<string, unknown> = {}): Frame[] => [
  ev("error", { code, message: `server text for ${code}`, retryable, ...extra }),
  ev("done"),
];

// The malicious answer of T12 (docs/09-security-privacy.md): every field that reaches the screen.
export const XSS = {
  img: `<img src=x onerror="window.__xss='img'">`,
  script: `<script>window.__xss='script'</script>`,
  svg: `<svg/onload="window.__xss='svg'">`,
  link: `[click me](javascript:window.__xss='link')`,
  iframe: `<iframe srcdoc="<script>parent.__xss='iframe'</script>"></iframe>`,
};
export const XSS_ALL = Object.values(XSS).join(" ");

export const malicious = (): Frame[] => [
  meta(),
  ev("step", { step_id: "s1", kind: "llm", status: "start", name: XSS_ALL }),
  ev("step", { step_id: "s1", kind: "llm", status: "end", name: XSS_ALL, duration_ms: 10,
    summary: { tool_calls: [XSS.img], model: XSS.img, usage: { input_tokens: 1, output_tokens: 1 } } }),
  ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "search_portfolio", args: { query: XSS_ALL } }),
  ev("step", { step_id: "s2", kind: "tool_result", status: "end", name: "search_portfolio", duration_ms: 10,
    summary: { query_used: XSS_ALL, method: "R3", candidates_considered: 1, results: [{ chunk_id: "x#all" }],
      candidates: [{ chunk_id: "x#all", record_title: XSS.img, excerpt: XSS_ALL, selected: true,
        scores: { lexical: 0.1, vector: 0.2, rrf: 0.3, rerank: null } }] } }),
  ev("token", { text: `Hello ${XSS_ALL}\n\n**${XSS.svg}**\n\n- ${XSS.iframe}\n\n# ${XSS.script}\n\n` }),
  ev("citation", { chunk_id: "x#all", index: 1 }),
  ev("sources", { sources: [{ chunk_id: "x#all", record_title: XSS.img, section: XSS.svg, text: XSS_ALL, commit: `"><img src=x onerror="window.__xss='commit'">` }] }),
  ev("usage", { input_tokens: 1, output_tokens: 1, ttft_ms: 1, total_ms: 2, model: XSS.img, fallback: false, dropped: 0, redacted: 0 }),
  ev("done"),
];

// S5: a project card and its diagram (backend/portfolio_agent/tools/cards.py).
const CARD_TITLE = { en: "Translation system", he: "מערכת תרגום" };

export const projectData = (extra: Record<string, unknown> = {}) => ({
  record_id: "translation",
  title: CARD_TITLE,
  role: "Sole engineer",
  period: "2025",
  tech: ["Python", "pgvector"],
  metrics: [
    { label: "Recall@5", before: "0.46", after: "0.76", value: null, how_measured: "On 50 labeled questions" },
    { label: "Reviewers", before: null, after: null, value: "4", how_measured: "Counted from the logs" },
  ],
  source: "translation#all",
  ...extra,
});

export const diagramData = (extra: Record<string, unknown> = {}) => ({
  record_id: "translation",
  title: CARD_TITLE,
  mermaid: 'flowchart TB\n  n0["Editor"]\n  n1["Agent loop with a long label that has to wrap inside its box"]\n  n2["Postgres"]\n  n3["Glossary"]\n  n4["Reviewer"]\n  n0 -->|"question"| n1\n  n1 --> n2\n  n1 --> n3\n  n1 --> n4',
  text: ["Components: Editor; Agent loop; Postgres.", "From Editor to Agent loop (question).", "From Agent loop to Postgres."],
  ...extra,
});

const cardStep = (id: string, kind: "project" | "diagram", summary: Record<string, unknown>): Frame[] => [
  ev("step", { step_id: id, kind: "tool_call", status: "start", name: "render_card", args: { record_id: "translation", kind } }),
  ...(summary.error ? [] : [ev("card", { kind, data: kind === "project" ? projectData() : diagramData() })]),
  ev("step", { step_id: id, kind: "tool_result", status: "end", name: "render_card", duration_ms: 1, summary: { record_id: "translation", kind, built_from: "frontmatter", ...summary } }),
];

const roundWithCards = (): Frame =>
  ev("step", { step_id: "s3", kind: "llm", status: "end", name: "round 2", duration_ms: 300,
    summary: { tool_calls: ["render_card", "render_card"], model: "openai/gpt-oss-120b", usage: { input_tokens: 1300, output_tokens: 20 } } });

/** An answer with a card and its diagram, sent as they are built, before the text. */
export const withCards = (lang: Lang = "he", cards: Item[] = [
  ...cardStep("s4", "project", { tech: 2, metrics: 2 }),
  ...cardStep("s5", "diagram", { components: 5, edges: 4 }),
]): Item[] => [
  meta(),
  ...searchSteps(lang),
  roundWithCards(),
  ...cards,
  ev("step", { step_id: "s6", kind: "llm", status: "start", name: "round 3" }),
  ...tokens(lang),
  ev("step", { step_id: "s6", kind: "llm", status: "end", name: "round 3", duration_ms: 600, summary: { tool_calls: [], model: "openai/gpt-oss-120b", usage: { input_tokens: 1500, output_tokens: 92 } } }),
  ...closing(lang).slice(1),
];

export const onlyDiagram = (lang: Lang = "he", data: Record<string, unknown> = {}): Item[] =>
  withCards(lang, [
    ev("step", { step_id: "s4", kind: "tool_call", status: "start", name: "render_card", args: { record_id: "translation", kind: "diagram" } }),
    ev("card", { kind: "diagram", data: diagramData(data) }),
    ev("step", { step_id: "s4", kind: "tool_result", status: "end", name: "render_card", duration_ms: 1, summary: { record_id: "translation", kind: "diagram", built_from: "frontmatter", components: 5, edges: 4 } }),
  ]);

export const refusedCard = (lang: Lang = "he"): Item[] =>
  withCards(lang, cardStep("s4", "project", { error: "not_retrieved" }));

export const maliciousCard = (): Frame[] => [
  meta(),
  ev("card", { kind: "project", data: projectData({
    title: { en: XSS.img, he: XSS.img }, role: XSS.script, period: XSS.svg, tech: [XSS.iframe, XSS.link],
    metrics: [{ label: XSS.img, value: XSS.svg, how_measured: XSS.script }], source: "x#all",
  }) }),
  ev("card", { kind: "diagram", data: diagramData({
    title: { en: XSS.svg, he: XSS.svg },
    // A source that tries everything: a directive, HTML in a label and a click handler.
    mermaid: `%%{init: {"securityLevel": "loose", "flowchart": {"htmlLabels": true}}}%%\nflowchart TB\n  a["<img src=x onerror=window.__xss=1>"]\n  b["<script>window.__xss=2</script>"]\n  a --> b\n  click a href "javascript:window.__xss=3"`,
    text: [XSS.img, XSS.script],
  }) }),
  ev("token", { text: "Hello" }),
  ev("sources", { sources: [{ chunk_id: "x#all", record_title: XSS.img, section: "all", text: XSS_ALL, commit: "abc" }] }),
  ev("usage", { input_tokens: 1, output_tokens: 1, ttft_ms: 1, total_ms: 2, model: "m", fallback: false, dropped: 0, redacted: 0 }),
  ev("done"),
];

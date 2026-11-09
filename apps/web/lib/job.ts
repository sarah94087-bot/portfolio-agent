// S4, the job match report (docs/07-advanced-capabilities.md, section 2; boards S4-*), as the
// screen reads it from the `card` event. Pure and language-free: the components add the words.
// A `card` that does not have this shape is dropped rather than half shown.

import type { Step } from "./chat.ts";

export type Strength = "strong" | "partial" | "none";
export type Level = "high" | "partial" | "low";

export type JobRequirement = {
  id: string;
  text: string;
  kind: "must" | "nice";
  strength: Strength;
  evidence: string[];
  rationale: string;
  cvOnly: boolean;
  yearsRequired: number | null;
  yearsCovered: number | null;
};

export type JobReport = {
  roleTitle: string;
  overall: Level;
  requirements: JobRequirement[];
  summary: string;
};

const obj = (v: unknown) =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : undefined;
const count = (v: unknown) => (typeof v === "number" ? v : null);

const LEVELS = new Set(["high", "partial", "low"]);
const STRENGTHS = new Set(["strong", "partial", "none"]);

function requirement(v: unknown): JobRequirement | null {
  const r = obj(v);
  if (!r || typeof r.text !== "string" || typeof r.strength !== "string" || !STRENGTHS.has(r.strength)) return null;
  if (r.kind !== "must" && r.kind !== "nice") return null;
  return {
    id: typeof r.id === "string" ? r.id : r.text,
    text: r.text,
    kind: r.kind,
    strength: r.strength as Strength,
    evidence: Array.isArray(r.evidence) ? r.evidence.filter((c): c is string => typeof c === "string") : [],
    rationale: typeof r.rationale === "string" ? r.rationale : "",
    cvOnly: r.cv_only === true,
    yearsRequired: count(r.years_required),
    yearsCovered: count(r.years_covered),
  };
}

export function parseReport(v: unknown): JobReport | undefined {
  const d = obj(v);
  if (!d || typeof d.overall !== "string" || !LEVELS.has(d.overall) || !Array.isArray(d.requirements)) return undefined;
  const requirements = d.requirements.map(requirement);
  if (requirements.some((r) => r === null)) return undefined;
  return {
    roleTitle: typeof d.role_title === "string" ? d.role_title : "",
    overall: d.overall as Level,
    requirements: requirements as JobRequirement[],
    summary: typeof d.summary === "string" ? d.summary : "",
  };
}

/** Source numbers by first citation; the Markdown numbers them the same way. */
export function sourceNumbers(report: JobReport): Map<string, number> {
  const out = new Map<string, number>();
  for (const r of report.requirements) for (const c of r.evidence) if (!out.has(c)) out.set(c, out.size + 1);
  return out;
}

/** Requirements with no proof, the musts first whatever the score. */
export function gapsOf(report: JobReport): JobRequirement[] {
  const gaps = report.requirements.filter((r) => r.strength === "none");
  return [...gaps.filter((g) => g.kind === "must"), ...gaps.filter((g) => g.kind !== "must")];
}

export type StageKey = "extract" | "evidence" | "rate" | "summary";
export type Stage = { key: StageKey; state: "done" | "run" | "wait"; done?: number; total?: number };

const ended = (steps: Step[], name: string) => steps.some((s) => s.name === name && s.status === "end");

/** The four lines the visitor watches, from the steps as they arrive (board S4-Report). */
export function jobStages(steps: Step[]): Stage[] {
  const total = steps.find((s) => s.name === "job.requirements")?.summary?.count;
  const requirements = typeof total === "number" ? total : undefined;
  const searched = steps.filter((s) => s.name === "search_portfolio" && s.status === "end").length;
  const flags: Record<StageKey, boolean> = {
    extract: requirements !== undefined,
    evidence: requirements !== undefined && searched >= requirements,
    rate: ended(steps, "job.rate"),
    summary: ended(steps, "job.summary"),
  };
  const keys: StageKey[] = ["extract", "evidence", "rate", "summary"];
  const first = keys.find((k) => !flags[k]);
  return keys.map((key) => {
    const state = flags[key] ? "done" : key === first ? "run" : "wait";
    if (key === "extract" && flags.extract) return { key, state, total: requirements };
    if (key === "evidence" && state === "run") return { key, state, done: searched, total: requirements };
    return { key, state };
  });
}

/** An ASCII file name, whatever language the role is in. */
export function reportFile(report: JobReport, date: string, extension: string): string {
  const role = report.roleTitle.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  return `job-match${role ? `-${role}` : ""}-${date}.${extension}`;
}

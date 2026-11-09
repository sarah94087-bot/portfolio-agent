// GET /api/stats (US-9.3; backend/portfolio_agent/stats.py). The server already applied the
// threshold and the rounding, so a measure is either a public number or null.

export const WINDOWS = ["7", "30"] as const;
export type StatsWindow = (typeof WINDOWS)[number];

export const TIME_METRICS = [
  "total_ms_p50",
  "total_ms_p95",
  "ttft_ms_warm_p50",
  "ttft_ms_warm_p95",
  "ttft_ms_cold_p50",
  "ttft_ms_cold_p95",
] as const;
export const RATE_METRICS = [
  "fallback_rate",
  "unanswered_rate",
  "cache_rate",
  "citation_removed_rate",
  "satisfaction_rate",
] as const;

export type TimeMetric = (typeof TIME_METRICS)[number];
export type RateMetric = (typeof RATE_METRICS)[number];
export type ModelShare = { model: string; share: number };
export type Measures = Record<TimeMetric | RateMetric, number | null> & { models: ModelShare[] };
export type Stats = { updated: string | null; windows: Record<StatsWindow, Measures> };

function isMeasures(value: unknown): value is Measures {
  const m = value as Partial<Measures> | null | undefined;
  if (!m || !Array.isArray(m.models)) return false;
  return [...TIME_METRICS, ...RATE_METRICS].every((key) => m[key] === null || typeof m[key] === "number");
}

export function parseStats(data: unknown): Stats | null {
  const s = data as Partial<Stats> | null | undefined;
  if (!s || (s.updated !== null && typeof s.updated !== "string")) return null;
  return WINDOWS.every((w) => isMeasures(s.windows?.[w])) ? (s as Stats) : null;
}

/** Never throws: a failure is null, and the page says so. */
export async function fetchStats(get: typeof fetch = fetch): Promise<Stats | null> {
  try {
    const res = await get("/api/stats");
    return res.ok ? parseStats(await res.json()) : null;
  } catch {
    return null;
  }
}

/** Whether any measure in any window passed the threshold. */
export function hasNumbers(stats: Stats): boolean {
  return WINDOWS.some((w) => {
    const m = stats.windows[w];
    return m.models.length > 0 || [...TIME_METRICS, ...RATE_METRICS].some((key) => m[key] !== null);
  });
}

/** Every model seen in either window, the busiest of the longer window first. */
export function modelNames(stats: Stats): string[] {
  return [...new Set(["30", "7"].flatMap((w) => stats.windows[w as StatsWindow].models.map((m) => m.model)))];
}

export const shareOf = (stats: Stats, window: StatsWindow, model: string) =>
  stats.windows[window].models.find((m) => m.model === model)?.share ?? null;

export const seconds = (ms: number) => (ms / 1000).toFixed(1);

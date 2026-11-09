import assert from "node:assert/strict";
import { test } from "node:test";

import { fetchStats, hasNumbers, modelNames, parseStats, seconds, shareOf, type Measures, type Stats } from "./stats.ts";

const empty = (): Measures => ({
  total_ms_p50: null,
  total_ms_p95: null,
  ttft_ms_warm_p50: null,
  ttft_ms_warm_p95: null,
  ttft_ms_cold_p50: null,
  ttft_ms_cold_p95: null,
  fallback_rate: null,
  unanswered_rate: null,
  cache_rate: null,
  citation_removed_rate: null,
  satisfaction_rate: null,
  models: [],
});

const stats = (week: Partial<Measures> = {}, month: Partial<Measures> = {}): Stats => ({
  updated: "2026-11-08",
  windows: { "7": { ...empty(), ...week }, "30": { ...empty(), ...month } },
});

const replying = (status: number, body: unknown) =>
  (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;

test("a full response parses, and so does one from before the first run", () => {
  assert.deepEqual(parseStats(stats({ cache_rate: 20 })), stats({ cache_rate: 20 }));
  assert.ok(parseStats({ ...stats(), updated: null }));
});

test("a response of the wrong shape is rejected", () => {
  assert.equal(parseStats(null), null);
  assert.equal(parseStats({ updated: "x" }), null);
  const missing = stats() as unknown as { windows: Record<string, Record<string, unknown>> };
  delete missing.windows["30"].cache_rate;
  assert.equal(parseStats(missing), null);
});

test("fetchStats reads /api/stats and turns every failure into null", async () => {
  assert.deepEqual(await fetchStats(replying(200, stats())), stats());
  assert.equal(await fetchStats(replying(503, {})), null);
  assert.equal(await fetchStats((async () => { throw new TypeError("offline"); }) as typeof fetch), null);
});

test("hasNumbers looks at both windows and at the models", () => {
  assert.equal(hasNumbers(stats()), false);
  assert.equal(hasNumbers(stats({}, { total_ms_p50: 1400 })), true);
  assert.equal(hasNumbers(stats({ models: [{ model: "a", share: 100 }] })), true);
});

test("model rows join the two windows, the longer one first", () => {
  const s = stats(
    { models: [{ model: "b", share: 100 }] },
    { models: [{ model: "a", share: 60 }, { model: "b", share: 40 }] },
  );
  assert.deepEqual(modelNames(s), ["a", "b"]);
  assert.equal(shareOf(s, "7", "a"), null);
  assert.equal(shareOf(s, "30", "a"), 60);
});

test("a time is shown in seconds with one decimal", () => {
  assert.equal(seconds(1400), "1.4");
  assert.equal(seconds(12000), "12.0");
});

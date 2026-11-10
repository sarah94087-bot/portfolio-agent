import assert from "node:assert/strict";
import { test } from "node:test";

import { agentPaused, checkPaused } from "./health.ts";

test("only an explicit false pauses the page", () => {
  assert.equal(agentPaused({ agent_enabled: false, db: { ok: true } }), true);
  for (const body of [{ agent_enabled: true }, {}, null, undefined, "false", { agent_enabled: "false" }, { agent_enabled: 0 }]) {
    assert.equal(agentPaused(body), false, JSON.stringify(body));
  }
});

const answer = (status: number, body: unknown) =>
  (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;

test("checkPaused reads the health answer", async () => {
  assert.equal(await checkPaused(false, answer(200, { agent_enabled: false })), true);
  assert.equal(await checkPaused(false, answer(200, { agent_enabled: true })), false);
});

test("a failed health check never pauses the page", async () => {
  assert.equal(await checkPaused(false, answer(500, { agent_enabled: false })), false);
  const down = (async () => {
    throw new TypeError("fetch failed");
  }) as unknown as typeof fetch;
  assert.equal(await checkPaused(true, down), false);
});

test("warm is asked for only when wanted", async () => {
  const urls: string[] = [];
  const spy = (async (url: string) => {
    urls.push(url);
    return new Response("{}");
  }) as unknown as typeof fetch;
  await checkPaused(true, spy);
  await checkPaused(false, spy);
  assert.deepEqual(urls, ["/api/health?warm=1", "/api/health"]);
});

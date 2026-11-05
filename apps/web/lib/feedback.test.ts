import assert from "node:assert/strict";
import { test } from "node:test";

import { chars, sendFeedback } from "./feedback.ts";

const replying = (status: number) => {
  const calls: { url: string; init: RequestInit }[] = [];
  const post = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(null, { status });
  }) as typeof fetch;
  return { calls, post };
};

test("feedback is posted as JSON with the visitor's cookie, and 204 is saved", async () => {
  const { calls, post } = replying(204);
  const body = { message_id: "m1", rating: "down" as const, comment: "wrong", challenge: true };
  assert.equal(await sendFeedback(body, post), "saved");
  assert.equal(calls[0].url, "/api/feedback");
  assert.equal(calls[0].init.credentials, "same-origin");
  assert.deepEqual(JSON.parse(String(calls[0].init.body)), body);
});

test("a limit, any other status and a network error are results, never a throw", async () => {
  assert.equal(await sendFeedback({ message_id: "m", rating: "up" }, replying(429).post), "limited");
  assert.equal(await sendFeedback({ message_id: "m", rating: "up" }, replying(404).post), "failed");
  const down = (async () => { throw new TypeError("network"); }) as typeof fetch;
  assert.equal(await sendFeedback({ message_id: "m", rating: "up" }, down), "failed");
});

test("characters are code points, as the server counts them", () => {
  assert.equal(chars("a😀b"), 3);
  assert.equal(chars("שלום"), 4);
});

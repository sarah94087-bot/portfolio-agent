import assert from "node:assert/strict";
import { test } from "node:test";

import { deleteConversation } from "./conversation.ts";

const replying = (status: number) => {
  const calls: { url: string; init: RequestInit }[] = [];
  const send = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(null, { status });
  }) as typeof fetch;
  return { calls, send };
};

test("a conversation is deleted with DELETE and the visitor's cookie", async () => {
  const { calls, send } = replying(204);
  assert.equal(await deleteConversation("c1", send), "deleted");
  assert.equal(calls[0].url, "/api/conversations/c1");
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].init.credentials, "same-origin");
});

test("a conversation already gone is deleted; a server error or no network is a failure", async () => {
  assert.equal(await deleteConversation("c1", replying(404).send), "deleted");
  assert.equal(await deleteConversation("c1", replying(503).send), "failed");
  const down = (async () => { throw new TypeError("network"); }) as typeof fetch;
  assert.equal(await deleteConversation("c1", down), "failed");
});

import assert from "node:assert/strict";
import { test } from "node:test";

import { checkFile, dataUrlBytes, firstImage, fitWithin, MAX_HEIGHT, MAX_INPUT_BYTES, MAX_WIDTH } from "./image.ts";
import { apply, newTurn, run } from "./chat.ts";

test("a picture is scaled to fit the box and never enlarged", () => {
  assert.deepEqual(fitWithin(800, 600), { width: 800, height: 600 });
  assert.deepEqual(fitWithin(3200, 1800), { width: MAX_WIDTH, height: 900 });
  // A whole page: tall and narrow, held by the height.
  assert.deepEqual(fitWithin(1200, 8000), { width: 600, height: MAX_HEIGHT });
  assert.deepEqual(fitWithin(1, 100000), { width: 1, height: MAX_HEIGHT });
});

test("only PNG, JPEG and WebP of a sane size are opened", () => {
  assert.equal(checkFile({ type: "image/png", size: 1000 }), null);
  assert.equal(checkFile({ type: "image/webp", size: 1000 }), null);
  assert.equal(checkFile({ type: "image/gif", size: 1000 }), "type");
  assert.equal(checkFile({ type: "image/svg+xml", size: 1000 }), "type");
  assert.equal(checkFile({ type: "application/pdf", size: 1000 }), "type");
  assert.equal(checkFile({ type: "image/png", size: MAX_INPUT_BYTES + 1 }), "size");
});

test("the first image among pasted files is the one taken", () => {
  const text = { type: "text/plain" } as File;
  const png = { type: "image/png" } as File;
  assert.equal(firstImage([text, png]), png);
  assert.equal(firstImage([text]), undefined);
  assert.equal(firstImage(null), undefined);
});

test("the size of a data URL is its payload's, with the padding off", () => {
  assert.equal(dataUrlBytes("data:image/png;base64," + btoa("abc")), 3);
  assert.equal(dataUrlBytes("data:image/png;base64," + btoa("abcd")), 4);
  assert.equal(dataUrlBytes("data:image/png;base64," + btoa("abcde")), 5);
});

test("a screenshot turn sends the image and no message, and keeps it for a retry", async () => {
  const turn = newTurn("", "key-1", true, "data:image/webp;base64,AAAA");
  assert.equal(turn.image, "data:image/webp;base64,AAAA");
  let body: Record<string, unknown> = {};
  const stream = async (_url: string, init: RequestInit) => {
    body = JSON.parse(String(init.body));
  };
  await run(turn, () => {}, { stream });
  assert.equal(body.mode, "job");
  assert.equal(body.image, "data:image/webp;base64,AAAA");
  assert.equal("message" in body, false);
  // A pasted posting still sends its text and no image.
  await run(newTurn("posting", "key-2", true), () => {}, { stream });
  assert.equal(body.message, "posting");
  assert.equal("image" in body, false);
  // The `meta` that follows replaces nothing about the image.
  assert.equal(apply(turn, { event: "meta", data: { v: 1 } }).image, turn.image);
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { interval, num, parseQuality, signed } from "./quality.ts";

const committed = () => JSON.parse(readFileSync(new URL("../data/quality.json", import.meta.url), "utf8"));

test("the committed data is valid", () => {
  assert.equal(parseQuality(committed()).schema, 1);
});

test("a missing field stops the build", () => {
  const data = committed();
  delete data.scorecard[0].low;
  assert.throws(() => parseQuality(data), /scorecard\[0\]\.low/);
});

test("the chosen method must be in the table", () => {
  const data = committed();
  data.rerank.chosen = "R9";
  assert.throws(() => parseQuality(data), /chosen/);
});

test("numbers keep two decimals and a real minus sign", () => {
  assert.equal(num(1), "1.00");
  assert.equal(signed(-0.074), "−0.07");
  assert.equal(signed(0.074), "+0.07");
  assert.equal(interval({ low: 0.931, high: 0.989 }), "[0.93, 0.99]");
});

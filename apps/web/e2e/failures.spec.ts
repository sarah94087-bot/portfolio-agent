// E10 as the visitor sees it: the fallback, every error screen, and a dropped connection.

import { ask, CUT, expect, openChat, test } from "./support/fixtures";
import { answer, answerText, closing, ev, failure, fallback, meta, searchSteps, TEXT, tokens } from "./support/recordings";

const he = TEXT.he;
const RETRY = "לנסות שוב";

test("US-10.1 a fallback mid-answer replaces the failed text and the answer goes on", async ({ page, api }) => {
  api.queue(fallback());
  await openChat(page);
  await ask(page, he.question);
  const message = page.getByRole("article");
  await expect(message).toContainText(answerText("he"));
  await expect(message).not.toContainText("טקסט של המודל שנפל");
  await expect(message.getByText("מודל גיבוי")).toBeVisible();
});

const screens: { name: string; items: ReturnType<typeof failure>; text: string; retry: boolean }[] = [
  { name: "US-10.3 the per-minute limit, with its wait", items: failure("rate_limited", true, { limit: "minute", retry_after: 37 }), text: "יותר מדי הודעות בדקה האחרונה. אפשר לנסות שוב בעוד 37 שניות.", retry: true },
  { name: "US-10.3 the visitor's daily limit", items: failure("rate_limited", false, { limit: "day" }), text: "המכסה היומית של השיחה עם הסוכן נוצלה. אפשר לחזור מחר, או להוריד את קורות החיים.", retry: false },
  { name: "the conversation's length limit", items: failure("rate_limited", false, { limit: "conversation" }), text: "השיחה הזו הגיעה לאורך המרבי. אפשר להתחיל שיחה חדשה.", retry: false },
  { name: "US-10.2 quotas exhausted", items: failure("quota_exhausted", false), text: "כרגע אין מודל זמין לענות. אפשר לנסות שוב בעוד כמה דקות, או להוריד את קורות החיים.", retry: false },
  { name: "no provider available", items: failure("provider_unavailable", true), text: "כרגע אין מודל זמין לענות. אפשר לנסות שוב בעוד כמה דקות, או להוריד את קורות החיים.", retry: true },
  { name: "US-10.4 a message the server refused as too long", items: failure("input_too_long", false), text: "ההודעה ארוכה מדי. המגבלה היא 1,000 תווים.", retry: false },
  { name: "an internal error, without the server's own words", items: failure("internal", true), text: "משהו השתבש אצלנו.", retry: true },
];

for (const s of screens) {
  test(`error screen: ${s.name}`, async ({ page, api }) => {
    api.queue(s.items);
    await openChat(page);
    await ask(page, he.question);
    const alert = page.getByRole("alert").filter({ hasText: s.text });
    await expect(alert).toBeVisible();
    await expect(page.getByRole("article")).not.toContainText("server text for");
    await expect(page.getByRole("button", { name: RETRY })).toHaveCount(s.retry ? 1 : 0);
  });
}

test("an error from the very start of the request says the server was not reached", async ({ page, api }) => {
  api.queue([], { status: 503 });
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("alert").filter({ hasText: "לא הצלחנו להגיע לשרת" })).toBeVisible();
  await expect(page.getByRole("button", { name: RETRY })).toBeVisible();
});

test("US-10.5 a dropped connection keeps the text, offers a retry, and the retry replaces it", async ({ page, api }) => {
  api.queue([meta(), ...searchSteps("he"), ev("token", { text: he.before }), CUT]);
  api.queue(answer());
  await openChat(page);
  await ask(page, he.question);

  const message = page.getByRole("article");
  await expect(page.getByRole("alert").filter({ hasText: "החיבור נקטע" })).toBeVisible();
  await expect(message).toContainText(he.before.trim());

  await page.getByRole("button", { name: RETRY }).click();
  await expect(message).toContainText(answerText("he"));
  await expect(page.locator("article [role=alert]")).toHaveCount(0);
  await expect(page.getByRole("button", { name: RETRY })).toHaveCount(0);
  await expect.poll(() => api.chats.length).toBe(2);
  expect(api.chats[1].idempotency_key).toBe(api.chats[0].idempotency_key); // no second charge
  expect(api.chats[1].message).toBe(he.question);
});

test("US-10.5 a stream that ends quietly without `done` counts as dropped too", async ({ page, api }) => {
  api.queue([meta(), ...tokens("he")]);
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("alert").filter({ hasText: "החיבור נקטע" })).toBeVisible();
});

test("US-10.5 an answer the server saved comes back from the database, and says so in the trace", async ({ page, api }) => {
  api.queue([meta(), ...tokens("he"), CUT]);
  api.queue([meta(), ...tokens("he"), ...closing("he", { replay: true })]);
  await openChat(page);
  await ask(page, he.question);
  await page.getByRole("button", { name: RETRY }).click();
  await expect(page.getByRole("article").getByText("מהמטמון")).toBeVisible();
  await page.getByRole("button", { name: "פירוט" }).click();
  await expect(page.getByRole("dialog")).toContainText("התשובה שנשמרה הוצגה שוב מהמסד");
});

test("unknown event types are ignored", async ({ page, api, pageErrors }) => {
  api.queue([meta(), ev("hologram", { anything: true }), ...tokens("he"), ...closing("he")]);
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("article")).toContainText(answerText("he"));
  expect(pageErrors).toEqual([]);
});

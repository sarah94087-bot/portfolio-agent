// T12 (docs/09-security-privacy.md): whatever the model or the knowledge base sends is text.

import type { Page } from "@playwright/test";

import { ask, expect, openChat, test } from "./support/fixtures";
import { failure, malicious, maliciousCard, shortAnswer, XSS } from "./support/recordings";

async function assertNothingRan(page: Page) {
  expect(await page.evaluate(() => (window as unknown as { __xss?: string }).__xss), "a payload ran").toBeUndefined();
  await expect(page.locator('img[src="x"], article script, article iframe, article svg[onload]')).toHaveCount(0);
  await expect(page.locator('a[href^="javascript:" i], a[href^="data:" i]')).toHaveCount(0);
  const handlers = await page.evaluate(() =>
    [...document.querySelectorAll("body *")].flatMap((el) => el.getAttributeNames().filter((a) => a.startsWith("on"))),
  );
  expect(handlers, "elements with inline handlers").toEqual([]);
}

test("a malicious answer is shown as text, in the message, the source and the trace", async ({ page, api }) => {
  let dialogs = 0;
  page.on("dialog", (d) => {
    dialogs++;
    void d.dismiss();
  });
  api.queue(malicious());
  await openChat(page, "en");
  await ask(page, XSS.img); // the question is echoed on the page too

  const message = page.getByRole("article");
  await expect(message).toContainText(XSS.img);
  await expect(message).toContainText(XSS.script);
  await expect(message).toContainText(XSS.link); // a Markdown link is not a link
  await expect(message.getByRole("link")).toHaveCount(0);
  await assertNothingRan(page);

  await page.locator("[data-cite='1']").click();
  await expect(page.getByRole("dialog").locator("blockquote")).toContainText(XSS.svg);
  await assertNothingRan(page);
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Sources" }).click();
  await assertNothingRan(page);

  await page.getByRole("button", { name: "Details" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.locator("code")).toContainText("onerror");
  await assertNothingRan(page);
  for (const link of await panel.getByRole("link").all()) {
    expect(await link.getAttribute("href")).toMatch(/^https:\/\/github\.com\/sarah94087-bot\/portfolio-agent\//);
  }

  await page.waitForTimeout(300); // anything delayed would have run by now
  await assertNothingRan(page);
  expect(dialogs).toBe(0);
});

test("a malicious card is text, and its diagram draws nothing that runs", async ({ page, api }) => {
  let dialogs = 0;
  page.on("dialog", (d) => {
    dialogs++;
    void d.dismiss();
  });
  api.queue(maliciousCard());
  await openChat(page, "en");
  await ask(page, "a card");
  const article = page.getByRole("article", { name: "Project card" });
  await expect(article.getByRole("heading", { level: 2 })).toContainText(XSS.img);
  await expect(article).toContainText(XSS.iframe);
  await expect(article).toContainText(XSS.script);
  // Whichever way it ends, drawn with the labels as text or refused for the text view.
  await expect(article.locator("[role=img] svg, ul.m-0.flex.list-none.flex-col.gap-1\\.5").first()).toBeAttached({ timeout: 15_000 });
  await page.waitForTimeout(500);
  await expect(article.locator("foreignObject, a, image, script")).toHaveCount(0);
  await assertNothingRan(page);
  await page.getByRole("button", { name: /How measured/ }).click();
  await assertNothingRan(page);
  await page.getByRole("button", { name: "The full record" }).click();
  await assertNothingRan(page);
  expect(dialogs).toBe(0);
});

test("an answer with a payload can be copied into the next question without running", async ({ page, api }) => {
  api.queue(shortAnswer(XSS.img));
  api.queue(failure(XSS.script, true));
  await openChat(page, "en");
  await ask(page, "first");
  await expect(page.getByRole("article")).toContainText(XSS.img);
  await ask(page, XSS.iframe);
  await expect(page.locator("article [role=alert]")).toBeVisible();
  await assertNothingRan(page);
});

// E1, the welcome screen (S1).

import { ask, expect, openChat, test } from "./support/fixtures";
import { answer, TEXT } from "./support/recordings";

test("US-1.1 the opening says this is an AI agent, not Sarah", async ({ page }) => {
  await openChat(page);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("סוכן AI");
  await openChat(page, "en");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("AI agent");
});

test("US-1.2 four starter questions and a free question field, in the page's language", async ({ page }) => {
  await openChat(page);
  const he = page.getByRole("list", { name: "שאלות לפתיחה" }).getByRole("button");
  await expect(he).toHaveCount(4);
  await expect(he.first()).toHaveText("על מה היא עובדת הכי טוב?");
  await expect(page.getByRole("textbox", { name: "שאלה על הניסיון של שרה" })).toBeVisible();

  await openChat(page, "en");
  const en = page.getByRole("list", { name: "Starter questions" }).getByRole("button");
  await expect(en).toHaveCount(4);
  await expect(en.first()).not.toHaveText("על מה היא עובדת הכי טוב?");
});

test("US-1.2 pressing a starter question sends it as if it were typed", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);
  const starter = page.getByRole("list", { name: "שאלות לפתיחה" }).getByRole("button").first();
  const text = await starter.innerText();
  await starter.click();
  await expect(page.getByRole("article")).toBeVisible();
  await expect(page.getByText(text.trim(), { exact: true })).toBeVisible();
  await expect.poll(() => api.chats.map((c) => c.message)).toEqual([text.trim()]);
});

test("US-1.2 the job starter opens the job field and sends nothing", async ({ page, api }) => {
  await openChat(page);
  await page.getByRole("list", { name: "שאלות לפתיחה" }).getByRole("button").last().click();
  await expect(page.getByRole("textbox", { name: "תיאור המשרה" })).toBeFocused();
  expect(api.chats).toEqual([]);
});

test("US-1.3 a first question needs no sign-up, cookie wall or form", async ({ page, api, context }) => {
  api.queue(answer());
  await openChat(page);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator('input[type="password"], input[type="email"]')).toHaveCount(0);
  expect(await context.cookies()).toEqual([]);
  await ask(page, TEXT.he.question);
  await expect(page.getByRole("article")).toContainText(TEXT.he.term);
});

test("US-1.4 the privacy line says what happens to conversations and links to the policy", async ({ page }) => {
  await openChat(page);
  await expect(page.getByText("השיחות נשמרות 30 יום ועוברות דרך ספקי מודלים חיצוניים.")).toBeVisible();
  await page.getByRole("link", { name: "מדיניות פרטיות" }).click();
  await expect(page).toHaveURL(/\/he\/privacy$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("the page warms the backend while the visitor reads", async ({ page, api }) => {
  await openChat(page);
  await expect.poll(() => api.health).toEqual(["/api/health?warm=1"]);
});

test("the address without a language goes to the visitor's language", async ({ browser, baseURL }) => {
  const english = await browser.newContext({ baseURL, locale: "en-US" });
  const page = await english.newPage();
  await page.goto("/how-it-works");
  await expect(page).toHaveURL(/\/en\/how-it-works$/);
  await english.close();
});

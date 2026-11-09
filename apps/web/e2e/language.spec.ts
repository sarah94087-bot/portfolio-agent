// E11: direction, mixed text, dark mode and the width of a phone.

import { ask, expect, hydrated, openChat, test } from "./support/fixtures";
import { answer, answerText, shortAnswer, TEXT } from "./support/recordings";

const PAGES = ["", "/how-it-works", "/quality", "/stats", "/privacy"];

for (const [lang, dir] of [["he", "rtl"], ["en", "ltr"]] as const) {
  test(`${lang}: every page declares its language and direction`, async ({ page }) => {
    for (const path of PAGES) {
      await page.goto(`/${lang}${path}`);
      await expect(page.locator("html")).toHaveAttribute("lang", lang);
      await expect(page.locator("html")).toHaveAttribute("dir", dir);
    }
  });
}

test("the language switch keeps the page and changes language and direction", async ({ page }) => {
  await page.goto("/he/quality");
  await page.getByRole("navigation", { name: "שפה" }).getByRole("link", { name: "English" }).click();
  await expect(page).toHaveURL(/\/en\/quality$/);
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

const direction = (l: import("@playwright/test").Locator) => l.evaluate((el) => getComputedStyle(el).direction);

test("US-11.2 each message takes its direction from its own content", async ({ page, api }) => {
  // an English question and answer on the Hebrew page
  api.queue(shortAnswer("This answer is in English."));
  // a Hebrew question and answer next
  api.queue(answer("he"));
  await openChat(page, "he");
  await ask(page, "What did she build?");
  const firstAnswer = page.getByRole("article").first().locator(".text-body");
  await expect(firstAnswer).toContainText("This answer is in English.");
  await expect(firstAnswer).toHaveAttribute("dir", "auto");
  expect(await direction(firstAnswer)).toBe("ltr");
  expect(await direction(page.getByText("What did she build?", { exact: true }))).toBe("ltr");
  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toHaveCount(1);

  await ask(page, TEXT.he.question);
  const second = page.getByRole("article").nth(1).locator(".text-body");
  await expect(second).toContainText(TEXT.he.term);
  expect(await direction(second)).toBe("rtl");
  expect(await direction(page.getByText(TEXT.he.question, { exact: true }))).toBe("rtl");
});

test("US-11.2 a Hebrew question on the English page is still right to left", async ({ page, api }) => {
  api.queue(answer("he"));
  await openChat(page, "en");
  await ask(page, TEXT.he.question);
  await expect(page.getByRole("article")).toContainText(TEXT.he.term);
  expect(await direction(page.getByText(TEXT.he.question, { exact: true }))).toBe("rtl");
  expect(await direction(page.getByRole("article").locator(".text-body"))).toBe("rtl");
  await expect(page.locator("textarea")).toHaveAttribute("dir", "auto");
});

test("US-11.1, US-11.2 a technical term stays whole inside a Hebrew sentence", async ({ page, api }) => {
  api.queue(answer("he"));
  await openChat(page);
  await ask(page, TEXT.he.question);
  await expect(page.locator("article .text-body bdi", { hasText: TEXT.he.term })).toHaveCount(1);
  await page.getByRole("button", { name: "פירוט" }).click();
  await expect(page.getByRole("dialog").locator("code")).toHaveAttribute("dir", "ltr");
});

test("US-11.1 the page's language goes out with the question", async ({ page, api }) => {
  api.queue(answer("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  await expect(page.getByRole("article")).toContainText(answerText("en"));
  expect(api.chats[0].lang).toBe("en");
});

test("US-11.4 the page follows the system's light or dark setting", async ({ page }) => {
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/he");
  expect(await background()).toBe("rgb(245, 240, 235)");
  await page.emulateMedia({ colorScheme: "dark" });
  expect(await background()).toBe("rgb(16, 14, 14)");
});

test.describe("at 375px", () => {
  test.use({ viewport: { width: 375, height: 700 } });

  const overflow = (page: import("@playwright/test").Page) =>
    page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

  for (const lang of ["he", "en"] as const) {
    test(`${lang}: nothing scrolls sideways, on any page or in a conversation`, async ({ page, api }) => {
      for (const path of PAGES) {
        await page.goto(`/${lang}${path}`);
        await hydrated(page);
        expect(await overflow(page), path).toBeLessThanOrEqual(0);
      }
      api.queue(answer(lang));
      await openChat(page, lang);
      await ask(page, "a-very-long-unbroken-word-".repeat(12));
      await expect(page.getByRole("article")).toContainText(TEXT[lang].term);
      expect(await overflow(page)).toBeLessThanOrEqual(0);
    });
  }
});

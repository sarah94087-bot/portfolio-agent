// WCAG 2.2 AA criteria that axe does not measure.

import type { Page } from "@playwright/test";

import { ask, expect, hydrated, openChat, test } from "./support/fixtures";
import { answer, TEXT } from "./support/recordings";

const PAGES = ["", "/how-it-works", "/quality", "/privacy"];
const he = TEXT.he;

test("2.4.2 every page has its own title", async ({ page }) => {
  const titles = new Set<string>();
  for (const lang of ["he", "en"]) {
    for (const path of PAGES) {
      await page.goto(`/${lang}${path}`);
      titles.add(await page.title());
    }
  }
  expect(titles.size).toBe(8);
});

async function converse(page: Page, api: import("./support/fixtures").Api) {
  api.queue(answer());
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
}

const insideDialog = (page: Page) => page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));

async function tabStaysInside(page: Page, times = 12) {
  for (let i = 0; i < times; i++) {
    await page.keyboard.press("Tab");
    expect(await insideDialog(page), `Tab ${i + 1}`).toBe(true);
  }
  for (let i = 0; i < times; i++) {
    await page.keyboard.press("Shift+Tab");
    expect(await insideDialog(page), `Shift+Tab ${i + 1}`).toBe(true);
  }
}

test.describe("2.4.11 focus stays out from under a sheet", () => {
  test("a source on a phone keeps Tab inside, and Esc returns", async ({ page, api }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await converse(page, api);
    const cite = page.getByRole("button", { name: "מקור 1", exact: true });
    await cite.click();
    await tabStaysInside(page);
    await page.keyboard.press("Escape");
    await expect(cite).toBeFocused();
  });

  for (const width of [375, 900]) {
    test(`the trace at ${width}px keeps Tab inside`, async ({ page, api }) => {
      await page.setViewportSize({ width, height: 667 });
      await converse(page, api);
      await page.getByRole("button", { name: "פירוט" }).click();
      await tabStaysInside(page);
    });
  }

  test("on a wide screen the trace sits beside the conversation and Tab moves on", async ({ page, api }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await converse(page, api);
    await page.getByRole("button", { name: "פירוט" }).click();
    let left = false;
    for (let i = 0; i < 12 && !left; i++) {
      await page.keyboard.press("Tab");
      left = !(await insideDialog(page));
    }
    expect(left).toBe(true);
  });
});

const sideways = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test.describe("1.4.10 reflow at 400% zoom (320 by 256 CSS pixels)", () => {
  test.use({ viewport: { width: 320, height: 256 } });

  for (const lang of ["he", "en"] as const) {
    test(`${lang}: no sideways scrolling on any page`, async ({ page }) => {
      for (const path of PAGES) {
        await page.goto(`/${lang}${path}`);
        await hydrated(page);
        expect(await sideways(page), path).toBeLessThanOrEqual(0);
      }
    });
  }

  test("the sticky bars let go, so the conversation has the screen", async ({ page, api }) => {
    await converse(page, api);
    const position = (selector: string) => page.locator(selector).evaluate((el) => getComputedStyle(el).position);
    expect(await position("header")).toBe("static");
    expect(await position("main form >> xpath=..")).toBe("static");
    expect(await sideways(page)).toBeLessThanOrEqual(0);
  });
});

test("1.4.12 text spacing: nothing is cut off or pushed sideways", async ({ page, api }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  const spacing = "* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }";
  // `truncate` cuts one line by design, with the whole text in its title and in the phone's card.
  const clipped = () => page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("body *")].filter((el) => {
      const s = getComputedStyle(el);
      if (s.overflowX === "visible" && s.overflowY === "visible") return false;
      if (s.overflowX === "auto" || s.overflowY === "auto" || s.overflowX === "scroll" || s.overflowY === "scroll") return false;
      if (el.classList.contains("sr-only") || el.classList.contains("truncate")) return false;
      return el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
    }).map((el) => `${el.tagName}.${el.className}`.slice(0, 100)));

  for (const lang of ["he", "en"]) {
    for (const path of PAGES) {
      await page.goto(`/${lang}${path}`);
      await hydrated(page);
      await page.addStyleTag({ content: spacing });
      expect(await sideways(page), path).toBeLessThanOrEqual(0);
      expect(await clipped(), path).toEqual([]);
    }
  }

  await converse(page, api);
  await page.addStyleTag({ content: spacing });
  await page.getByRole("button", { name: "פירוט" }).click();
  expect(await sideways(page)).toBeLessThanOrEqual(0);
  expect(await clipped()).toEqual([]);
});

test("1.3.4 the page works in landscape on a phone", async ({ page, api }) => {
  await page.setViewportSize({ width: 667, height: 375 });
  await converse(page, api);
  expect(await sideways(page)).toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "מקור 1", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("button", { name: "סגירה" })).toBeInViewport();
});

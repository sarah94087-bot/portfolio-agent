// M5's exit criterion: zero axe violations, on every page and in every state of a conversation,
// in both languages, on a phone and a desktop, in light and dark.

import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";

import { ask, CUT, expect, hydrated, openChat, test } from "./support/fixtures";
import { answer, ev, failure, meta, TEXT, withCards } from "./support/recordings";

// Every WCAG A and AA rule up to 2.2, and axe's best practices (headings, landmarks).
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

async function check(page: Page, state: string) {
  // Anything can slide under a sticky bar at some scroll position, and axe would then call it a
  // small target. Scanned with the bars in the flow, the result does not depend on scrolling;
  // what is really hidden from the keyboard is keyboard.spec.ts's job.
  const bars = (position: string) => page.evaluate((p) => {
    document.querySelectorAll<HTMLElement>("header, [data-dock]").forEach((el) => { el.style.position = p; });
  }, position);
  await bars("static");
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  await bars("");
  const found = violations.map((v) => ({
    rule: v.id,
    impact: v.impact,
    nodes: v.nodes.map((n) => ({ target: n.target.join(" "), why: n.failureSummary?.split("\n")[1]?.trim() })),
  }));
  expect(found, `axe violations: ${state}`).toEqual([]);
}

const LANGS = ["he", "en"] as const;
const THEMES = ["light", "dark"] as const;
const SIZES = [{ name: "375", width: 375, height: 700 }, { name: "desktop", width: 1280, height: 800 }];
const PAGES = ["", "/how-it-works", "/quality", "/stats", "/privacy"];

const t = {
  he: { up: "תשובה מועילה", down: "תשובה לא מועילה", details: "פירוט", remove: "מחיקת השיחה", source: "מקור 1", sources: /^מקורות/, retry: "לנסות שוב", closePanel: "סגירת הפאנל" },
  en: { up: "Helpful answer", down: "Not a helpful answer", details: "Details", remove: "Delete conversation", source: "Source 1", sources: /^Sources/, retry: "Try again", closePanel: "Close panel" },
};

for (const lang of LANGS) {
  for (const colorScheme of THEMES) {
    for (const size of SIZES) {
      const label = `${lang} ${size.name} ${colorScheme}`;

      test.describe(label, () => {
        test.use({ viewport: { width: size.width, height: size.height }, colorScheme, reducedMotion: "reduce" });

        for (const path of PAGES) {
          test(`page /${lang}${path}`, async ({ page }) => {
            await page.goto(`/${lang}${path}`);
            await hydrated(page);
            await check(page, `${label} /${lang}${path}`);
          });
        }

        test("a project card and its diagram, in both views", async ({ page, api }) => {
          test.setTimeout(60_000);
          const text = lang === "he" ? "טקסט" : "Text";
          const how = lang === "he" ? /איך נמדד/ : /How measured/;
          api.queue(withCards(lang));
          await openChat(page, lang);
          await ask(page, TEXT[lang].question);
          await expect(page.locator("[role=img] svg")).toBeVisible({ timeout: 15_000 });
          await expect(page.getByRole("button", { name: t[lang].up, exact: true })).toBeVisible();
          await check(page, `${label} card`);
          await page.getByRole("button", { name: how }).first().click();
          await page.getByRole("button", { name: text, exact: true }).click();
          await check(page, `${label} card, metric open and text view`);
        });

        test("a conversation, in every state it can be in", async ({ page, api }) => {
          test.setTimeout(90_000);
          const s = t[lang];
          api.queue(answer(lang));
          api.queue([meta(), ev("token", { text: TEXT[lang].before }), CUT]);
          api.queue(failure("quota_exhausted", false));
          await openChat(page, lang);
          if (size.width === 375) {
            await page.locator("summary").click();
            await check(page, `${label} mobile menu`);
            await page.locator("summary").click();
          }

          await ask(page, TEXT[lang].question);
          await expect(page.getByRole("button", { name: s.up, exact: true })).toBeVisible();
          await check(page, `${label} answer`);

          await page.getByRole("button", { name: s.sources }).click();
          await check(page, `${label} source list`);

          await page.getByRole("button", { name: s.source, exact: true }).click();
          await expect(page.getByRole("dialog")).toBeVisible();
          await check(page, `${label} source popover`);
          await page.keyboard.press("Escape");

          await page.getByRole("button", { name: s.details }).click();
          await expect(page.getByRole("button", { name: s.closePanel })).toBeFocused();
          await check(page, `${label} trace panel`);
          await page.keyboard.press("Escape");

          await page.getByRole("button", { name: s.down, exact: true }).click();
          await expect(page.locator("form textarea").first()).toBeFocused();
          await check(page, `${label} feedback comment`);
          await page.keyboard.press("Escape");

          await page.getByRole("button", { name: s.remove }).click();
          await expect(page.getByRole("alertdialog")).toBeVisible();
          await check(page, `${label} delete dialog`);
          await page.keyboard.press("Escape");

          await ask(page, "second");
          await expect(page.getByRole("button", { name: s.retry })).toBeVisible();
          await check(page, `${label} disconnected`);

          await ask(page, "third");
          await expect(page.locator("article [role=alert]")).toHaveCount(2);
          await check(page, `${label} error`);
        });
      });
    }
  }
}

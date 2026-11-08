// US-11.3: the whole flow from the keyboard, focus that can be seen, and one announcement.

import type { Page } from "@playwright/test";

import { CUT, expect, HOLD, openChat, test } from "./support/fixtures";
import { answer, answerText, closing, meta, searchSteps, shortAnswer, TEXT, tokens, ev } from "./support/recordings";

const he = TEXT.he;

/** Presses Tab until the element is focused, and fails if it never is. */
async function tabTo(page: Page, name: string | RegExp, role: "button" | "link" | "textbox" = "button") {
  const target = page.getByRole(role, { name, exact: typeof name === "string" }).last();
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return target;
  }
  throw new Error(`Tab never reached ${name}`);
}

test("a question, its source, the trace, feedback and delete, without a mouse", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);

  await tabTo(page, "שאלה על הניסיון של שרה", "textbox");
  await page.keyboard.type(he.question);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
  await expect(page.locator("textarea")).toBeFocused(); // the field was replaced, focus was not lost

  const cite = await tabTo(page, "מקור 1");
  await page.keyboard.press("Enter");
  const source = page.getByRole("dialog");
  await expect(source).toBeFocused();
  await page.keyboard.press("Tab"); // the close button
  await page.keyboard.press("Tab"); // the passage, which scrolls from the keyboard
  await expect(source.locator("blockquote")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(cite).toBeFocused();

  const details = await tabTo(page, "פירוט");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "סגירת הפאנל" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(details).toBeFocused();

  const up = await tabTo(page, "תשובה מועילה");
  await page.keyboard.press("Space");
  await expect(up).toHaveAttribute("aria-pressed", "true");

  await tabTo(page, "מחיקת השיחה");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("button", { name: "ביטול" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "מחיקה" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("textarea")).toBeFocused();
  await expect.poll(() => api.deleted.length).toBe(1);
});

test("sending with the button leaves the keyboard in the question field", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);
  await page.locator("textarea").fill(he.question);
  const send = await tabTo(page, "שליחה");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article")).toContainText(answerText("he"));
  await expect(send).not.toBeFocused();
  await expect(page.locator("textarea")).toBeFocused();
});

test("a starter question can be sent from the keyboard, and the focus lands in the field", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);
  await tabTo(page, "על מה היא עובדת הכי טוב?");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article")).toContainText(answerText("he"));
  await expect(page.locator("textarea")).toBeFocused();
});

test("after a retry the keyboard is not lost", async ({ page, api }) => {
  api.queue([meta(), ev("token", { text: he.before }), CUT]);
  api.queue(answer());
  await openChat(page);
  await page.locator("textarea").fill(he.question);
  await page.locator("textarea").press("Enter");
  await expect(page.getByRole("button", { name: "לנסות שוב" })).toBeVisible();
  await tabTo(page, "לנסות שוב");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("article")).toContainText(answerText("he"));
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).toBe("TEXTAREA");
});

test("the mobile menu opens from the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await page.goto("/he");
  await page.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", { name: "הורדת קו״ח" })).toBeVisible();
});

// 2.4.7 and 2.4.11: at every Tab stop the focus has a visible mark and something sticky does
// not hide it.
for (const [name, viewport] of [["phone", { width: 375, height: 667 }], ["desktop", { width: 1280, height: 720 }]] as const) {
  test(`every Tab stop in a long conversation is visible and not hidden (${name})`, async ({ page, api }) => {
    await page.setViewportSize(viewport);
    for (let i = 0; i < 4; i++) api.queue(answer());
    await openChat(page);
    for (let i = 0; i < 4; i++) {
      await page.locator("textarea").fill(he.question);
      await page.locator("textarea").press("Enter");
      await expect(page.getByRole("button", { name: "תשובה מועילה" })).toHaveCount(i + 1);
      await expect(page.getByRole("button", { name: "שליחה" })).toBeDisabled();
    }

    await page.evaluate(() => {
      document.querySelector<HTMLElement>("header a")!.focus();
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(600); // the smooth scroll to the last question ends
    const seen = new Set<string>();
    for (let i = 0; i < 80; i++) {
      await page.keyboard.press("Tab");
      await page.waitForTimeout(20);
      const stop = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const r = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        const points = [[r.left + 1, r.top + 1], [r.right - 1, r.top + 1], [r.left + 1, r.bottom - 1], [r.right - 1, r.bottom - 1], [r.left + r.width / 2, r.top + r.height / 2]];
        const shown = points.some(([x, y]) => {
          const hit = document.elementFromPoint(x, y);
          return !!hit && (el === hit || el.contains(hit) || hit.contains(el));
        });
        return {
          label: `${el.tagName} ${el.getAttribute("aria-label") ?? el.textContent?.slice(0, 30)} @${Math.round(r.top)}`,
          shown,
          outline: style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2,
          inView: r.bottom > 0 && r.top < innerHeight,
        };
      });
      if (!stop) break; // Tab left the page: all stops were visited
      seen.add(stop.label);
      expect.soft(stop.shown && stop.inView, `hidden at ${stop.label}`).toBe(true);
      expect.soft(stop.outline, `no focus mark at ${stop.label}`).toBe(true);
    }
    expect(seen.size).toBeGreaterThan(15);
  });
}

// What a screen reader hears: every change of text in every live region of the page.
async function listen(page: Page) {
  await page.addInitScript(() => {
    const log: string[] = [];
    (window as unknown as { __live: string[] }).__live = log;
    const LIVE = '[role="status"],[role="alert"],[aria-live]';
    // One DOM update can be several records: a region counts once per update.
    const update = (records: MutationRecord[]) => {
      const regions = new Set(records.map((m) =>
        (m.target.nodeType === 1 ? (m.target as Element) : m.target.parentElement)?.closest(LIVE)));
      for (const region of regions) {
        const text = region?.textContent?.trim();
        if (text) log.push(text);
      }
    };
    new MutationObserver(update).observe(document, { subtree: true, childList: true, characterData: true });
  });
}
const heard = (page: Page) => page.evaluate(() => (window as unknown as { __live: string[] }).__live);

test("US-11.3 one announcement per answer, never token by token", async ({ page, api }) => {
  await listen(page);
  api.queue([meta(), ...searchSteps("he"), HOLD, ...tokens("he"), HOLD, ...closing("he")]);
  api.queue(shortAnswer("תשובה שנייה קצרה"));
  await openChat(page);
  await page.locator("textarea").fill(he.question);
  await page.locator("textarea").press("Enter");

  // During the stream the text is hidden from the screen reader, and nothing of it is live.
  await api.release();
  await api.held();
  await expect(page.locator("article .text-body")).toHaveAttribute("aria-hidden", "true");
  expect((await heard(page)).filter((t) => t.includes(he.term))).toEqual([]);
  await api.release();

  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
  await expect.poll(async () => (await heard(page)).filter((t) => t.includes(he.term)).length).toBe(1);
  const [said] = (await heard(page)).filter((t) => t.includes(he.term));
  expect(said).toContain(`${answerText("he")} [1]${he.second} [2]`);
  await expect(page.locator("article .text-body")).not.toHaveAttribute("aria-hidden", "true");

  // It is cleared after a few seconds, so reading the page later does not find it twice.
  await expect(page.locator("article [role=status]").first()).toBeEmpty({ timeout: 6_000 });

  // The second answer gets its own single announcement, and the first is not repeated.
  await page.locator("textarea").fill("עוד שאלה");
  await page.locator("textarea").press("Enter");
  await expect.poll(async () => (await heard(page)).filter((t) => t.includes("תשובה שנייה קצרה")).length).toBe(1);
  expect((await heard(page)).filter((t) => t.includes(he.term))).toHaveLength(1);
});

// S5, the project card and its diagram (US-6.1, US-6.2): on recorded streams, with the real
// Mermaid drawing in the real browser.

import { ask, expect, HOLD, openChat, test } from "./support/fixtures";
import { answer, onlyDiagram, refusedCard, TEXT, withCards } from "./support/recordings";

const card = { he: "כרטיס פרויקט", en: "Project card" };

test("a card and its diagram come before the answer, in Hebrew", async ({ page, api, pageErrors }) => {
  void pageErrors;
  api.queue(withCards("he"));
  await openChat(page, "he");
  await ask(page, TEXT.he.question);

  const article = page.getByRole("article", { name: card.he });
  await expect(article.getByRole("heading", { level: 2 })).toHaveText("מערכת תרגום");
  await expect(article).toContainText("התפקיד של שרה");
  await expect(article.locator("dd").first()).toHaveAttribute("lang", "en");
  await expect(article.getByText("Sole engineer")).toBeVisible();
  await expect(article.getByText("pgvector", { exact: true })).toBeVisible();

  const drawing = article.getByRole("img", { name: /תרשים ארכיטקטורה של מערכת תרגום/ });
  await expect(drawing.locator("svg")).toBeVisible({ timeout: 15_000 });
  await expect(drawing.locator("svg")).toContainText("Agent loop");
  await expect(drawing.locator("svg foreignObject")).toHaveCount(0);
  await expect(drawing).toHaveAttribute("lang", "en");

  const box = await article.boundingBox();
  const text = await page.locator("p", { hasText: TEXT.he.before }).boundingBox();
  expect(box!.y).toBeLessThan(text!.y);
});

test("a metric opens to show how it was measured, by keyboard", async ({ page, api }) => {
  api.queue(withCards("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  const metric = page.getByRole("button", { name: /Recall@5/ });
  await expect(metric).toHaveAttribute("aria-expanded", "false");
  await expect(metric).toContainText("from 0.46 to 0.76"); // what a screen reader gets for the arrow
  await metric.focus();
  await page.keyboard.press("Enter");
  await expect(metric).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("On 50 labeled questions")).toBeVisible();
});

test("the diagram has a text view, and the text is in the page either way", async ({ page, api }) => {
  api.queue(withCards("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  const article = page.getByRole("article", { name: card.en });
  await expect(article.locator("[role=img] svg")).toBeVisible({ timeout: 15_000 });

  const line = article.getByText("From Editor to Agent loop (question).");
  await expect(line).toHaveCount(1);
  await expect(line.locator("xpath=..")).toHaveClass(/sr-only/);

  await article.getByRole("button", { name: "Text", exact: true }).click();
  await expect(article.getByRole("button", { name: "Text", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(line).toBeVisible();
  await expect(line.locator("xpath=..")).not.toHaveClass(/sr-only/);
  await expect(article.locator("[role=img] svg")).toBeHidden();

  await article.getByRole("button", { name: "Diagram", exact: true }).click();
  await expect(article.locator("[role=img] svg")).toBeVisible();
});

test("the source opens over the card and Esc returns to its button", async ({ page, api }) => {
  api.queue(withCards("he"));
  await openChat(page, "he");
  await ask(page, TEXT.he.question);
  const button = page.getByRole("button", { name: /הרשומה המלאה/ });
  await button.click();
  await expect(page.getByRole("dialog")).toContainText("בדיקה אנושית");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(button).toBeFocused();
});

test("the trace says the card was built from the record, and what the model chose", async ({ page, api }) => {
  api.queue(withCards("he"));
  await openChat(page, "he");
  await ask(page, TEXT.he.question);
  await page.getByRole("button", { name: "פירוט" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel).toContainText("הוצג כרטיס של translation");
  await expect(panel).toContainText("בלי טקסט מהמודל");
  await expect(panel).toContainText("2 מדדים");
  await expect(panel).toContainText("הוצג תרשים של translation");
  await expect(panel).toContainText("5 רכיבים");
  await expect(panel.locator("code").filter({ hasText: 'render_card(record_id="translation", kind="diagram")' })).toBeVisible();
});

test("a refused card is in the trace and nothing is drawn", async ({ page, api }) => {
  api.queue(refusedCard("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("dialog")).toContainText("The code refused to show translation");
  await expect(page.getByRole("article", { name: card.en })).toHaveCount(0);
});

test("the status line says a card is being prepared", async ({ page, api }) => {
  api.queue(withCards("he", [
    { event: "step", data: { step_id: "s4", kind: "tool_call", status: "start", name: "render_card", args: { record_id: "translation", kind: "project" } } },
    HOLD,
  ]));
  await openChat(page, "he");
  await ask(page, TEXT.he.question);
  await api.held();
  await expect(page.getByRole("status").filter({ hasText: "מכין את הכרטיס" })).toBeVisible();
  await api.release();
});

test("a diagram alone has its own card, with the project's title", async ({ page, api }) => {
  api.queue(onlyDiagram("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  const article = page.getByRole("article", { name: "Architecture diagram" });
  await expect(article.getByRole("heading", { level: 2 })).toHaveText("Translation system");
  await expect(article.locator("[role=img] svg")).toBeVisible({ timeout: 15_000 });
  await expect(article.getByRole("button", { name: /How measured/ })).toHaveCount(0);
});

test("a diagram that cannot be drawn falls back to its text, and leaves nothing behind", async ({ page, api, pageErrors }) => {
  void pageErrors;
  api.queue(onlyDiagram("en", { mermaid: "this is not a diagram ((((" }));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  const article = page.getByRole("article", { name: "Architecture diagram" });
  await expect(article).toContainText("The diagram did not load", { timeout: 15_000 });
  await expect(article.getByText("From Editor to Agent loop (question).")).toBeVisible();
  await expect(article.getByRole("button", { name: "Text", exact: true })).toHaveCount(0);
  await expect(page.locator("body > div[id^=d] svg, body > svg")).toHaveCount(0);
});

test("a page without a diagram does not download Mermaid", async ({ page, api }) => {
  const scripts: string[] = [];
  page.on("response", async (r) => {
    if (r.url().endsWith(".js")) scripts.push(await r.text().catch(() => ""));
  });
  api.queue(answer("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  await expect(page.getByRole("button", { name: "Details" })).toBeVisible();
  expect(scripts.filter((s) => s.includes("flowchart-v2")), "Mermaid in a plain answer").toEqual([]);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("a wide diagram scrolls inside its frame, by keyboard too, and the page does not", async ({ page, api }) => {
    api.queue(onlyDiagram("he", {
      mermaid: `flowchart LR\n${Array.from({ length: 6 }, (_, i) => `  n${i}["A component with quite a long name, ${i}"]`).join("\n")}\n  n0 --> n1 --> n2 --> n3 --> n4 --> n5`,
    }));
    await openChat(page, "he");
    await ask(page, TEXT.he.question);
    const frame = page.getByRole("group", { name: /אפשר לגלול לרוחב/ });
    await expect(frame).toBeVisible({ timeout: 15_000 });
    await expect(frame).toHaveAttribute("tabindex", "0");
    await expect(frame).toHaveAttribute("dir", "ltr");
    await frame.focus();
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => frame.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  });

  test("a narrow card has no sideways scrolling", async ({ page, api }) => {
    api.queue(withCards("en"));
    await openChat(page, "en");
    await ask(page, TEXT.en.question);
    await expect(page.locator("[role=img] svg")).toBeVisible({ timeout: 15_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  });
});

test.describe("in dark", () => {
  test.use({ colorScheme: "dark" });

  test("the drawing takes the dark tokens, and redraws when the theme changes", async ({ page, api }) => {
    api.queue(onlyDiagram("en"));
    await openChat(page, "en");
    await ask(page, TEXT.en.question);
    const node = page.locator("[role=img] svg .node rect, [role=img] svg .node polygon").first();
    await expect(node).toBeVisible({ timeout: 15_000 });
    const fill = () => node.evaluate((el) => getComputedStyle(el).fill);
    expect(await fill()).toBe("rgb(74, 21, 25)"); // --tint-rose in dark
    await page.emulateMedia({ colorScheme: "light" });
    await expect.poll(fill, { timeout: 15_000 }).toBe("rgb(246, 211, 209)"); // in light
  });
});

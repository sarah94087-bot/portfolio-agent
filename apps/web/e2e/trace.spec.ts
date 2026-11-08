// E4, the trace panel (S3).

import { ask, expect, openChat, test } from "./support/fixtures";
import { answer, COMMIT, fallback, TEXT } from "./support/recordings";

const he = TEXT.he;

async function open(page: import("@playwright/test").Page, api: import("./support/fixtures").Api, items = answer() as import("./support/fixtures").Item[]) {
  api.queue(items);
  await openChat(page);
  await ask(page, he.question);
  const details = page.getByRole("button", { name: "פירוט" });
  await details.click();
  return { details, panel: page.getByRole("dialog", { name: "איך נבנתה התשובה" }) };
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("US-4.1 the timeline shows the decision, the tool call with its parameters, the result and the answer", async ({ page, api }) => {
    const { panel } = await open(page, api);
    const steps = panel.getByRole("region", { name: "ציר זמן" }).getByRole("listitem");
    await expect(steps).toHaveCount(4);
    await expect(steps.nth(0)).toContainText("קריאת מודל");
    await expect(steps.nth(1)).toContainText("search_portfolio");
    await expect(steps.nth(2)).toContainText("נבחרו 2 קטעים להקשר, מתוך 11.");
    await expect(steps.nth(3)).toContainText("המודל ניסח את התשובה וצירף 2 ציטוטים.");
    await expect(panel.locator("code")).toHaveText('search_portfolio(query="complex project translation")');
  });

  test("US-4.2 every candidate shows each method's score, and the chosen ones are marked", async ({ page, api }) => {
    const { panel } = await open(page, api);
    const retrieval = panel.getByRole("region", { name: "מועמדים מהאחזור" });
    const table = retrieval.getByRole("table");
    await expect(table.getByRole("columnheader", { name: "לקסיקלי" })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "וקטורי" })).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "RRF" })).toBeVisible();
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(8);
    await expect(rows.first()).toContainText("נבחר");
    await expect(rows.first()).toContainText("0.031");
    await expect(rows.first()).toContainText("0.81");
    await expect(rows.nth(2)).not.toContainText("נבחר");
    await expect(rows.nth(2)).toContainText("—"); // a method that did not rank this one

    await retrieval.getByRole("button", { name: /הכל|כולם/ }).click();
    await expect(rows).toHaveCount(11);
  });

  test("US-4.3 times, tokens and the model that answered", async ({ page, api }) => {
    const { panel } = await open(page, api);
    await expect(panel.getByRole("region", { name: "ציר זמן" })).toContainText("0.41 שנ׳");
    await expect(panel.getByRole("img")).toHaveAccessibleName(/1,430/);
    const tokens = panel.locator("table").last();
    await expect(tokens).toContainText("2,400");
    await expect(tokens).toContainText("123");
    await expect(panel).toContainText("openai/gpt-oss-120b");
    await expect(panel.getByRole("link", { name: "system.v1" })).toHaveAttribute("href", /prompts\/system\.v1\.md$/);
    await expect(panel.getByRole("link", { name: COMMIT.slice(0, 7) })).toHaveAttribute("href", new RegExp(`/tree/${COMMIT}$`));
  });

  test("US-4.3 a fallback is shown, with the reason", async ({ page, api }) => {
    const { panel } = await open(page, api, fallback());
    await expect(panel).toContainText("gpt-oss-120b לא ענה (rate_limit), והסבב עבר ל-llama-3.3-70b.");
    await expect(panel.getByRole("region", { name: "ציר זמן" })).toContainText("גיבוי");
  });

  test("the panel sits beside the conversation and Esc returns focus to its button", async ({ page, api }) => {
    const { details, panel } = await open(page, api);
    await expect(panel.getByRole("button", { name: "סגירת הפאנל" })).toBeFocused();
    await expect(details).toHaveAttribute("aria-expanded", "true");
    const box = (await panel.boundingBox())!;
    const article = (await page.getByRole("article").boundingBox())!;
    expect(article.x + article.width <= box.x || box.x + box.width <= article.x).toBe(true); // no overlap
    await page.keyboard.press("Escape");
    await expect(panel).toHaveCount(0);
    await expect(details).toBeFocused();
  });

  test("from a source: \"how was this found?\" opens the panel at its row", async ({ page, api }) => {
    api.queue(answer());
    await openChat(page);
    await ask(page, he.question);
    const cite = page.getByRole("button", { name: "מקור 1", exact: true });
    await cite.click();
    await page.getByRole("button", { name: "איך הקטע הזה נמצא?" }).click();
    const row = page.getByRole("dialog", { name: "איך נבנתה התשובה" }).locator("tbody tr").first();
    await expect(row).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(cite).toBeFocused();
  });
});

test.describe("US-4.4 on a phone", () => {
  test.use({ viewport: { width: 375, height: 700 } });

  test("the trace is closed until pressed, opens as a sheet and leaves the conversation in view", async ({ page, api }) => {
    api.queue(answer());
    await openChat(page);
    await ask(page, he.question);
    await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await page.getByRole("button", { name: "פירוט" }).click();
    const panel = page.getByRole("dialog", { name: "איך נבנתה התשובה" });
    const box = (await panel.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(700 * 0.29); // the top of the conversation stays
    expect(box.y + box.height).toBeCloseTo(700, 0);
    expect(box.width).toBe(375);
    await expect(panel.locator("table").first()).toBeHidden();
    await expect(panel.getByRole("listitem").filter({ hasText: "לקסיקלי" }).first()).toBeVisible(); // cards, not a table
  });

  test("a press outside the sheet closes it", async ({ page, api }) => {
    const { panel } = await open(page, api);
    await page.mouse.click(180, 100);
    await expect(panel).toHaveCount(0);
  });
});

// US-9.3: the public metrics, in each state the page can be in.

import { STATS, expect, test } from "./support/fixtures";

const empty = {
  ...STATS.windows["7"],
  ...Object.fromEntries(Object.keys(STATS.windows["7"]).map((k) => [k, null])),
  models: [],
};

test("numbers are shown, and a measure below the threshold says so", async ({ page }) => {
  await page.goto("/he/stats");
  const speed = page.getByRole("region", { name: "מהירות" });
  await expect(speed.getByRole("row", { name: /תשובה מלאה, חציון/ })).toContainText("3.4 שנ׳");
  await expect(speed.getByRole("row", { name: "מילה ראשונה, בקשה קרה, p95" })).toContainText("אין מספיק נתונים");
  await expect(page.getByRole("region", { name: "איכות" }).getByRole("row", { name: /מעבר למודל גיבוי/ })).toContainText("10%");
  await expect(page.getByText("2026-11-08")).toBeVisible();
});

test("the English page has its own words and direction", async ({ page }) => {
  await page.goto("/en/stats");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.getByRole("region", { name: "Speed" })).toContainText("3.4 s");
  await expect(page.getByRole("region", { name: "Which model answered" })).toContainText("openai/gpt-oss-120b");
});

test("with no measure over the threshold, the page explains why", async ({ page, api }) => {
  api.stats = { updated: "2026-11-08", windows: { "7": empty, "30": empty } };
  await page.goto("/he/stats");
  await expect(page.getByText("עדיין אין מספיק נתונים")).toBeVisible();
  await expect(page.getByRole("region", { name: "מהירות" }).getByText("אין מספיק נתונים")).toHaveCount(12);
});

test("before the first run the page says so", async ({ page, api }) => {
  api.stats = { updated: null, windows: { "7": empty, "30": empty } };
  await page.goto("/en/stats");
  await expect(page.getByText("The computation has not run yet")).toBeVisible();
});

test("a failed request is a message, not an empty table", async ({ page, api }) => {
  api.stats = null;
  await page.goto("/he/stats");
  await expect(page.getByText("המדדים לא נטענו")).toBeVisible();
  await expect(page.getByRole("region", { name: "מהירות" })).toHaveCount(0);
});

test("the header links to the page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/he");
  await page.getByRole("navigation", { name: "ניווט ראשי" }).getByRole("link", { name: "מדדים" }).click();
  await expect(page).toHaveURL(/\/he\/stats$/);
});

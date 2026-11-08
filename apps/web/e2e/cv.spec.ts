// US-7.4 and US-10.2: the CV is the way out when the agent cannot answer, so it has to work.

import { expect, openChat, test } from "./support/fixtures";

const HREF = "/cv/sara-halevy-cv.pdf";

test("the CV address returns a PDF", async ({ request }) => {
  const res = await request.get(HREF);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  const body = await res.body();
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  expect(body.length).toBeGreaterThan(10_000);
});

test.describe("the download link", () => {
  for (const [name, width] of [["desktop", 1280], ["phone", 375]] as const) {
    test(`${name}: the header's link downloads the PDF`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await openChat(page);
      if (name === "phone") await page.locator("summary").click();
      const [download] = await Promise.all([
        page.waitForEvent("download"),
        page.getByRole("link", { name: "הורדת קו״ח" }).click(),
      ]);
      expect(download.suggestedFilename()).toBe("Sara Halevy cv.pdf");
      expect(new URL(download.url()).pathname).toBe(HREF);
    });
  }

  test("the privacy page links to the same file", async ({ page }) => {
    await page.goto("/en/privacy");
    await expect(page.getByRole("main").getByRole("link", { name: "CV" })).toHaveAttribute("href", HREF);
  });
});

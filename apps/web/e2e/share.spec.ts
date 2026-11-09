// What a link shows when it is shared, and what search engines are told.

import { expect, test } from "./support/fixtures";

const SITE = "https://portfolio-agent-rosy.vercel.app";

for (const [lang, title] of [["he", "הסוכן של שרה הלוי"], ["en", "Sarah Halevy's AI agent"]] as const) {
  test(`/${lang} has its own share card`, async ({ page, request }) => {
    await page.goto(`/${lang}`);
    const content = (selector: string) => page.locator(selector).getAttribute("content");

    expect(await content('meta[property="og:title"]')).toBe(title);
    expect(await content('meta[property="og:description"]')).toBeTruthy();
    expect(await content('meta[property="og:image"]')).toBe(`${SITE}/og/${lang}.png`);
    expect(await content('meta[property="og:image:width"]')).toBe("1200");
    expect(await content('meta[property="og:image:alt"]')).toBeTruthy();
    expect(await content('meta[name="twitter:card"]')).toBe("summary_large_image");

    const image = await request.get(`/og/${lang}.png`);
    expect(image.status()).toBe(200);
    expect(image.headers()["content-type"]).toBe("image/png");
  });
}

test("each page names its own address and its other language", async ({ page }) => {
  await page.goto("/en/quality");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}/en/quality`);
  await expect(page.locator('link[rel="alternate"][hreflang="he"]')).toHaveAttribute("href", `${SITE}/he/quality`);
});

test("robots.txt keeps crawlers out of the API and points at the sitemap", async ({ request }) => {
  const text = await (await request.get("/robots.txt")).text();
  expect(text).toContain("Disallow: /api/");
  expect(text).toContain(`Sitemap: ${SITE}/sitemap.xml`);
});

test("the sitemap lists every page in both languages", async ({ request }) => {
  const text = await (await request.get("/sitemap.xml")).text();
  for (const lang of ["he", "en"]) {
    for (const path of ["", "/how-it-works", "/quality", "/stats", "/privacy"]) {
      expect(text).toContain(`<loc>${SITE}/${lang}${path}</loc>`);
    }
  }
});

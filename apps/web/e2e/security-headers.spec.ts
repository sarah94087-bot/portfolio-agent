// The security headers of docs/09-security-privacy.md, section 5, on the production build. The
// policy only counts if the site still works under it, so each page must load with no violation,
// and so must Mermaid, the one thing on the site that injects styles (ADR-0020).

import type { Page } from "@playwright/test";

import { ask, expect, openChat, test } from "./support/fixtures";
import { onlyDiagram, TEXT } from "./support/recordings";

const pages = ["/he", "/en", "/he/how-it-works", "/he/quality", "/he/privacy", "/he/stats"];

type Watched = Window & { violations: string[]; injected?: boolean };

// Added through the browser's protocol, so the policy under test does not apply to it.
async function watchViolations(page: Page) {
  await page.addInitScript(() => {
    (window as unknown as Watched).violations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as Watched).violations.push(`${e.violatedDirective} ${e.blockedURI}`);
    });
  });
}

const violations = (page: Page) => page.evaluate(() => (window as unknown as Watched).violations);

for (const path of pages) {
  test(`${path} sends the headers and loads with no violation`, async ({ page }) => {
    await watchViolations(page);
    const response = await page.goto(path, { waitUntil: "load" });
    const headers = response!.headers();
    const policy = headers["content-security-policy"];

    expect(policy).toMatch(/script-src 'self' 'nonce-[\w+/=]+' 'strict-dynamic'/);
    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).not.toContain("unsafe-eval");
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["permissions-policy"]).toBe("camera=(), microphone=(), geolocation=()");

    await expect(page.locator("script:not([nonce])")).toHaveCount(0);
    expect(await violations(page)).toEqual([]);
  });
}

test("a 404 page gets the policy too, and a file that exists stays out of it", async ({ request }) => {
  for (const path of ["/robots-missing.txt", "/missing.xml", "/_next/missing"]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(404);
    expect(response.headers()["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(response.headers()["x-powered-by"], path).toBeUndefined();
  }
  expect((await request.get("/favicon.ico")).headers()["content-security-policy"]).toBeUndefined();
});

test("the nonce is new on every request", async ({ request }) => {
  const nonce = async () =>
    /'nonce-([^']+)'/.exec((await request.get("/he")).headers()["content-security-policy"])![1];
  expect(await nonce()).not.toBe(await nonce());
});

// T12: what reaches the HTML without the request's nonce does not run. A script that code already
// running creates through the DOM is another matter: `strict-dynamic` lets it through (ADR-0020).
test("markup injected into the page does not run", async ({ page }) => {
  await watchViolations(page);
  await page.route("**/en", async (route) => {
    const response = await route.fetch();
    const injected =
      "<script>window.injected = true</script>" +
      '<script nonce="wrong">window.injected = true</script>' +
      '<img src="x" onerror="window.injected = true">';
    await route.fulfill({ response, body: (await response.text()).replace("</body>", `${injected}</body>`) });
  });
  await page.goto("/en", { waitUntil: "load" });
  await expect.poll(async () => (await violations(page)).length).toBeGreaterThanOrEqual(3);
  expect(await page.evaluate(() => (window as unknown as Watched).injected)).toBeUndefined();
});

test("Mermaid draws a diagram with no violation", async ({ page, api }) => {
  await watchViolations(page);
  api.queue(onlyDiagram("en"));
  await openChat(page, "en");
  await ask(page, TEXT.en.question);
  const drawing = page.getByRole("article", { name: "Architecture diagram" }).locator("[role=img] svg");
  await expect(drawing).toBeVisible({ timeout: 15_000 });
  await expect(drawing).toContainText("Agent loop");
  expect(await violations(page)).toEqual([]);
});

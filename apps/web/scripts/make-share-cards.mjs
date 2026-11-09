// Makes public/og/he.png and en.png, the image a link shows when it is shared. It draws them in the
// running site, so they use its fonts, its colors and its real headline. They are files and not a
// route because the image renderer behind `opengraph-image` has no right-to-left text.
//
//   npm run build && npx next start -p 3218
//   node scripts/make-share-cards.mjs http://localhost:3218

import { chromium } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:3000";

const cards = {
  he: {
    owner: "שרה הלוי",
    headline: 64,
    chips: ["מקור לכל טענה", "רואים איך נבנתה התשובה", "אומר כשאין לו מידע"],
  },
  en: {
    owner: "Sarah Halevy",
    headline: 56,
    chips: ["A source for every claim", "Every step visible", "Says when it doesn't know"],
  },
};

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1200, height: 630 },
  deviceScaleFactor: 1,
  colorScheme: "light",
});

for (const lang of ["he", "en"]) {
  await page.goto(`${base}/${lang}`, { waitUntil: "load" });
  await page.evaluate(({ owner, headline, chips }) => {
    const heading = document.querySelector("main h1").cloneNode(true);
    const brand = document.querySelector("header a");
    const mark = brand.querySelector("svg, [aria-hidden]")?.cloneNode(true);
    const name = [...brand.querySelectorAll("span")].map((s) => s.textContent).filter(Boolean);

    const card = document.createElement("div");
    card.style.cssText =
      "position:fixed;inset:0;z-index:9999;display:flex;flex-direction:column;justify-content:space-between;" +
      "padding:56px 72px 60px;background:var(--surface);color:var(--text);border-top:10px solid var(--accent);" +
      "box-sizing:border-box";

    const top = document.createElement("div");
    top.style.cssText = "display:flex;align-items:center;gap:16px;font-size:32px;font-weight:800";
    if (mark) {
      mark.style.cssText = "gap:4px;flex:none";
      for (const cell of mark.children) cell.style.cssText = "width:19px;height:19px;border-radius:4px";
      top.append(mark);
    }
    const title = document.createElement("span");
    title.textContent = name[0] ?? "";
    top.append(title);
    const tag = document.createElement("span");
    tag.textContent = name.at(-1) ?? "";
    tag.style.cssText =
      "padding:4px 14px;border-radius:999px;background:var(--accent);color:var(--on-accent);font-size:22px;font-weight:700";
    top.append(tag);
    const person = document.createElement("span");
    person.textContent = owner;
    person.style.cssText = "margin-inline-start:auto;font-size:30px;font-weight:700;color:var(--text-muted)";
    top.append(person);

    const middle = document.createElement("div");
    heading.removeAttribute("class");
    heading.style.cssText = `margin:0;font-size:${headline}px;line-height:1.3;font-weight:800;letter-spacing:-0.01em`;
    middle.append(heading);

    const bottom = document.createElement("div");
    bottom.style.cssText = "display:flex;gap:14px";
    const tints = [["--tint-ink", "--on-ink"], ["--tint-stone", "--on-stone"], ["--tint-rose", "--on-rose"]];
    chips.forEach((text, i) => {
      const chip = document.createElement("span");
      chip.textContent = text;
      chip.style.cssText =
        `padding:14px 24px;border-radius:14px;font-size:26px;font-weight:700;white-space:nowrap;` +
        `background:var(${tints[i][0]});color:var(${tints[i][1]})`;
      bottom.append(chip);
    });

    card.append(top, middle, bottom);
    document.body.append(card);
  }, cards[lang]);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `public/og/${lang}.png` });
}

await browser.close();

// Draws D3's postings as screenshots for D3-img (jobmatch/image_run.py): node render.mjs DIR.
// Reads DIR/jobs.json and writes DIR/<key>.png. The browser lays out the text, so Hebrew comes
// out right to left as on a real page. Playwright comes from apps/web (npm ci there first).

import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const dir = process.argv[2];
if (!dir) throw new Error("usage: node render.mjs DIR");
const items = JSON.parse(readFileSync(join(dir, "jobs.json"), "utf8"));

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const paragraphs = (text) =>
  text.trim().split(/\n\s*\n/).map((p) => `<p>${esc(p.trim()).replace(/\n\s*/g, " ")}</p>`).join("");

// A desktop page: the posting and nothing else.
const plain = (item) => `<body style="margin:0;background:#fff;color:#1b1b1b;font:17px/1.6 system-ui,'Segoe UI',Arial,sans-serif">
  <main dir="${item.lang === "he" ? "rtl" : "ltr"}" style="width:860px;padding:40px 48px">
    <h1 style="font-size:28px;margin:0 0 20px">${esc(item.title)}</h1>${paragraphs(item.description)}</main></body>`;

// A phone page: navigation, an apply button and other jobs around the text, as on a job board.
const card = (item) => `<body style="margin:0;background:#f3f2ef;color:#222;font:15px/1.55 system-ui,'Segoe UI',Arial,sans-serif">
  <nav style="background:#fff;padding:12px 16px;display:flex;justify-content:space-between;border-bottom:1px solid #ddd"><b>JobBoard</b><span>Jobs &middot; Messages &middot; Me</span></nav>
  <main dir="${item.lang === "he" ? "rtl" : "ltr"}" style="width:390px;box-sizing:border-box;padding:16px">
    <div style="background:#fff;border-radius:8px;padding:16px;margin-bottom:12px">
      <h1 style="font-size:20px;margin:0 0 6px">${esc(item.title)}</h1>
      <div style="color:#666;font-size:13px">Tel Aviv &middot; Hybrid &middot; 31 applicants</div>
      <button style="margin-top:12px;width:100%;padding:10px;border:0;border-radius:20px;background:#0a66c2;color:#fff;font-size:15px">Easy Apply</button>
    </div>
    <div style="background:#fff;border-radius:8px;padding:16px">${paragraphs(item.description)}</div>
    <div style="background:#fff;border-radius:8px;padding:16px;margin-top:12px;color:#666;font-size:13px"><b>Similar jobs</b><br>QA Engineer &middot; Data Analyst &middot; Product Designer</div>
  </main></body>`;

const browser = await chromium.launch();
try {
  for (const item of items) {
    const page = await browser.newPage({ viewport: { width: item.layout === "card" ? 390 : 960, height: 800 } });
    await page.setContent(`<!doctype html><meta charset="utf-8">${item.layout === "card" ? card(item) : plain(item)}`);
    writeFileSync(join(dir, `${item.key}.png`), await page.screenshot({ fullPage: true }));
    await page.close();
  }
} finally {
  await browser.close();
}
console.log(`drew ${items.length} pictures in ${dir}`);

// The site's public address and its pages, for the share tags, the sitemap and robots.txt.

export const SITE_URL = "https://portfolio-agent-rosy.vercel.app";

export const PAGES = ["", "/how-it-works", "/quality", "/stats", "/privacy"] as const;

/** The canonical address of a page in one language, and its address in each. */
export function alternates(lang: string, path: (typeof PAGES)[number]) {
  return {
    canonical: `/${lang}${path}`,
    languages: { he: `/he${path}`, en: `/en${path}` },
  };
}

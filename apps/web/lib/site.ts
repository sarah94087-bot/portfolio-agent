// The site's public address and its pages, for the share tags, the sitemap and robots.txt.

export const SITE_URL = "https://portfolio-agent-rosy.vercel.app";

// One CV for both languages (US-7.4). It holds the email address and the LinkedIn link.
export const CV_HREF = "/cv/sara-halevy-cv.pdf";
export const CV_NAME = "Sara Halevy cv.pdf";

export const PAGES = ["", "/how-it-works", "/quality", "/stats", "/privacy"] as const;

/** The language a visitor gets when none fits: where "/" sends them (defaultLocale in dictionaries). */
const DEFAULT_LANG = "he";

/** The address of a page in each language, and the one search engines use when none fits. */
export const languageAddresses = (base: string, path: (typeof PAGES)[number]) => ({
  he: `${base}/he${path}`,
  en: `${base}/en${path}`,
  "x-default": `${base}/${DEFAULT_LANG}${path}`,
});

/** The canonical address of a page in one language, and its address in each. */
export function alternates(lang: string, path: (typeof PAGES)[number]) {
  return {
    canonical: `/${lang}${path}`,
    languages: languageAddresses("", path),
  };
}

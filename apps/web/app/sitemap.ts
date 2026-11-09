import type { MetadataRoute } from "next";

import { PAGES, SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.flatMap((path) =>
    (["he", "en"] as const).map((lang) => ({
      url: `${SITE_URL}/${lang}${path}`,
      alternates: { languages: { he: `${SITE_URL}/he${path}`, en: `${SITE_URL}/en${path}` } },
    })),
  );
}

import type { MetadataRoute } from "next";

import { languageAddresses, PAGES, SITE_URL } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.flatMap((path) =>
    (["he", "en"] as const).map((lang) => ({
      url: `${SITE_URL}/${lang}${path}`,
      alternates: { languages: languageAddresses(SITE_URL, path) },
    })),
  );
}

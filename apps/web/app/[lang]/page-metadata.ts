import type { Metadata } from "next";

import { alternates } from "@/lib/site";
import { getDictionary, type Locale } from "./dictionaries";

/**
 * The metadata of an inner page. Next merges metadata one level deep: a page that sets `openGraph`
 * replaces every `openGraph` field of the layout, image included. So an inner page states all of
 * them here instead of only its own description.
 */
export function pageMetadata(
  lang: Locale,
  path: Parameters<typeof alternates>[1],
  page: { title: string; description: string },
): Metadata {
  const { meta } = getDictionary(lang);
  const title = `${page.title} · ${meta.title}`;
  const image = { url: `/og/${lang}.png`, width: 1200, height: 630, alt: meta.shareAlt };
  return {
    title,
    description: page.description,
    alternates: alternates(lang, path),
    openGraph: {
      type: "website",
      siteName: meta.title,
      title,
      description: page.description,
      locale: lang === "he" ? "he_IL" : "en_US",
      images: [image],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description: page.description,
      images: [image],
    },
  };
}

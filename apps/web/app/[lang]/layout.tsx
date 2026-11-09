import type { Metadata } from "next";
import { Assistant, IBM_Plex_Mono } from "next/font/google";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { alternates, SITE_URL } from "@/lib/site";

import "../globals.css";
import { directionOf, getDictionary, hasLocale, locales } from "./dictionaries";

// Assistant: Hebrew and Latin drawn together, so mixed sentences don't jump fonts.
const assistant = Assistant({
  subsets: ["hebrew", "latin"],
  variable: "--font-assistant",
  display: "swap",
});

// Plex Mono only for numbers, model ids, tool names and scores.
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

// Other locales 404 through hasLocale below.
export function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: LayoutProps<"/[lang]">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  const { meta } = getDictionary(lang);
  const image = { url: `/og/${lang}.png`, width: 1200, height: 630, alt: meta.shareAlt };
  return {
    metadataBase: new URL(SITE_URL),
    title: meta.title,
    description: meta.description,
    alternates: alternates(lang, ""),
    openGraph: {
      type: "website",
      siteName: meta.title,
      title: meta.shareTitle,
      description: meta.description,
      locale: lang === "he" ? "he_IL" : "en_US",
      images: [image],
    },
    twitter: {
      card: "summary_large_image",
      title: meta.shareTitle,
      description: meta.description,
      images: [image],
    },
  };
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  // Every page renders per request, so its scripts can carry that request's nonce (ADR-0020).
  await connection();
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();

  return (
    <html
      lang={lang}
      dir={directionOf(lang)}
      className={`${assistant.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}

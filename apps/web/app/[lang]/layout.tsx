import type { Metadata } from "next";
import { Assistant, IBM_Plex_Mono } from "next/font/google";
import { notFound } from "next/navigation";

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

// Other locales 404 through hasLocale below (dynamicParams is not allowed with cacheComponents).
export function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: LayoutProps<"/[lang]">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  const { meta } = getDictionary(lang);
  return {
    title: meta.title,
    description: meta.description,
    alternates: { languages: { he: "/he", en: "/en" } },
  };
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
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

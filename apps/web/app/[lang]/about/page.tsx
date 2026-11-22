import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DocPage } from "@/components/ui/DocPage";
import { JsonLd } from "@/components/ui/JsonLd";
import { SITE_URL } from "@/lib/site";
import { hasLocale, type Locale } from "../dictionaries";
import { pageMetadata } from "../page-metadata";

// Who Sarah is, in a few lines that a search engine can read and a visitor can check. Every claim
// is from portfolio/profile.md (approved 2026-11-04): the numbers here must change with it.
const copy: Record<Locale, {
  eyebrow: string;
  title: string;
  description: string;
  lede: string;
  about: string;
  ask: string;
  askLink: string;
}> = {
  he: {
    eyebrow: "AI Engineer | Backend & AI Systems",
    title: "על שרה הלוי",
    description: "שרה הלוי היא AI Engineer שמתמחה ב-backend ובמערכות AI, ובנתה לבדה מערכת חיה לניהול נתונים, מהארכיטקטורה ועד ההשקה.",
    lede: "שרה הלוי היא AI Engineer שמתמחה ב-backend ובמערכות AI.",
    about:
      "לבדה, מהארכיטקטורה ועד ההשקה, היא בנתה מערכת חיה לניהול נתונים: מסד PostgreSQL עם 108 מיגרציות ו-31 מדיניות RLS, צינור תרגום על Claude עם אישור אנושי, ו-API שזמן התגובה שלו ירד מ-582 ל-40 מילישניות.",
    ask: "האתר הזה הוא סוכן AI שעונה על שאלות על העבודה שלה, עם מקור לכל טענה.",
    askLink: "לשאול את הסוכן",
  },
  en: {
    eyebrow: "AI Engineer | Backend & AI Systems",
    title: "About Sarah Halevy",
    description: "Sarah Halevy is an AI Engineer specializing in backend and AI systems, who built a live data-management system on her own, from architecture to launch.",
    lede: "Sarah Halevy is an AI Engineer specializing in backend and AI systems.",
    about:
      "On her own, from architecture to launch, she built a live data-management system: a PostgreSQL database with 108 migrations and 31 row-level security policies, a translation pipeline on Claude with human approval, and an API whose response time she cut from 582 ms to 40 ms.",
    ask: "This site is an AI agent that answers questions about her work, with a source for every claim.",
    askLink: "Ask the agent",
  },
};

export async function generateMetadata({ params }: PageProps<"/[lang]/about">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return pageMetadata(lang, "/about", copy[lang]);
}

export default async function AboutPage({ params }: PageProps<"/[lang]/about">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const c = copy[lang];

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "AboutPage",
          url: `${SITE_URL}/${lang}/about`,
          name: c.title,
          inLanguage: lang,
          mainEntity: {
            "@type": "Person",
            "@id": `${SITE_URL}/#sarah-halevy`,
            name: "Sarah Halevy",
            jobTitle: "AI Engineer",
          },
        }}
      />
      <DocPage lang={lang} eyebrow={c.eyebrow} title={c.title} lede={c.lede}>
        <p className="mt-6 text-[17px] leading-[1.7]">{c.about}</p>
        <p className="mt-4 text-[17px] leading-[1.7]">
          {c.ask}{" "}
          <Link href={`/${lang}`} className="text-accent underline underline-offset-3">
            {c.askLink}
          </Link>
        </p>
      </DocPage>
    </>
  );
}

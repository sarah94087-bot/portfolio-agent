import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { DocPage, Ext, Section, TableFrame, Term, td, th } from "@/components/ui/DocPage";
import { getDictionary, hasLocale, type Locale } from "../dictionaries";
import { alternates } from "@/lib/site";

// S12 (US-12.1). This page describes what the system does today, checked against the code and
// the migrations. Features that are not built (contact form, company links) are left out until
// they are.

const cvHref = "/cv/sara-halevy-cv.pdf";
const providers = {
  groq: "https://console.groq.com/docs/your-data",
  vercel: "https://vercel.com/legal/privacy-policy",
  neon: "https://neon.com/privacy-policy",
  langfuse: "https://langfuse.com/privacy",
};

type Row = [what: ReactNode, why: string, where: string, howLong: string];

const copy: Record<Locale, {
  eyebrow: string;
  title: string;
  lede: string;
  updated: string;
  storedTitle: string;
  columns: [string, string, string, string];
  rows: Row[];
  storedNote: string;
  providersTitle: string;
  providers: [string, ReactNode, string][];
  policy: string;
  notSent: ReactNode;
  cookieTitle: string;
  cookie: ReactNode;
  deleteTitle: string;
  deletion: ReactNode;
  deleteLimits: ReactNode;
  contactTitle: string;
  contact: ReactNode;
}> = {
  he: {
    eyebrow: "מה נשמר, אצל מי ולכמה זמן",
    title: "פרטיות",
    lede: "האתר שומר רק מה שצריך כדי לענות ולמנוע ניצול. אין חשבונות, אין פרסום ואין מעקב של צד שלישי. עדיף לא לכתוב בשיחה מידע אישי.",
    updated: "עודכן ב-8 בנובמבר 2026",
    storedTitle: "מה נשמר",
    columns: ["מה", "למה", "איפה", "לכמה זמן"],
    rows: [
      ["שאלות, תשובות וצעדי התשובה", "המשך שיחה, חלון המעקב ושיפור הסוכן", "Neon, פרנקפורט", "30 יום"],
      ["משוב, אם נשלח", "שיפור הסוכן", "Neon, פרנקפורט", "30 יום"],
      [<>עוגיית מבקר <Term>pa_vid</Term></>, "מכסות והמשך שיחה", "הדפדפן", "30 יום מהשימוש האחרון"],
      ["גיבוב של כתובת IP עם מלח יומי", "הגנה מניצול", "Neon, פרנקפורט", "יומיים"],
      ["מוני מכסות", "הגבלת שימוש", "Neon, פרנקפורט", "7 ימים"],
      ["תשובות לשאלות פתיחה נפוצות", "מטמון משותף, לא קשור למבקר", "Neon, פרנקפורט", "7 ימים"],
      ["מדדים יומיים מצטברים, בלי תוכן ובלי קשר למבקר", "עמוד המדדים", "Neon, פרנקפורט", "ללא הגבלה"],
    ],
    storedNote: "כתובת ה-IP עצמה לא נשמרת. השיחות גלויות לשרה, והודעות נשמרות כפי שנכתבו.",
    providersTitle: "מי מעבד את המידע",
    providers: [
      ["Groq", <>מקבל את השאלה, את היסטוריית השיחה ואת הקטעים מהתיק, כדי לכתוב את התשובה. לפי המדיניות שלו התוכן לא נשמר כברירת מחדל, ולוגים לבדיקת תקלות או שימוש לרעה נשמרים עד 30 יום.</>, providers.groq],
      ["Vercel", <>מארח את האתר ומעבד את הבקשות, בפרנקפורט.</>, providers.vercel],
      ["Neon", <>מסד הנתונים, בפרנקפורט.</>, providers.neon],
      ["Langfuse", <>כלי ניטור שזמין לשרה בלבד, כשהוא מופעל. מיילים ומספרי טלפון מוסתרים לפני השליחה.</>, providers.langfuse],
    ],
    policy: "המדיניות שלהם",
    notSent: <>שאלות של מבקרים לא נשלחות ל-Google. החישוב הווקטורי של השאלה רץ על השרת של האתר. העוגייה והגיבוב של ה-IP לא נשלחים לספקי המודלים.</>,
    cookieTitle: "עוגיות",
    cookie: <>יש עוגייה אחת, הכרחית לפעולת האתר. היא שומרת מזהה אקראי, וקוד האתר בדפדפן לא יכול לקרוא אותה. אין עוגיות ניתוח או פרסום, ולכן אין באנר הסכמה.</>,
    deleteTitle: "מחיקת שיחה",
    deletion: <>הכפתור ״מחיקת השיחה״ מוחק מיד מהמסד את השיחה, ההודעות, הצעדים והמשוב שלה. רק מי שהשיחה קשורה לעוגייה שלו יכול למחוק אותה.</>,
    deleteLimits: <>המחיקה לא מגיעה ללוגים של Groq. עבודה יומית מוחקת מ-Langfuse את הרישומים של התשובות בשיחה. רישום של בקשה שהסתיימה בלי תשובה נמחק לפני שהוא מגיע לגיל 30 יום, ועד אז מיילים ומספרי טלפון בו מוסתרים. תשובות במטמון המשותף לא נמחקות, כי אין בהן שום קשר למבקר.</>,
    contactTitle: "יצירת קשר בנושא פרטיות",
    contact: <>פרטי הקשר של שרה מופיעים ב<a href={cvHref} download="Sara Halevy cv.pdf" className="text-accent underline underline-offset-3">קורות החיים</a>.</>,
  },
  en: {
    eyebrow: "What is kept, by whom, and for how long",
    title: "Privacy",
    lede: "The site keeps only what it needs to answer and to prevent abuse. No accounts, no advertising, no third-party tracking. Please don't share personal information in the chat.",
    updated: "Updated November 8, 2026",
    storedTitle: "What is kept",
    columns: ["What", "Why", "Where", "How long"],
    rows: [
      ["Questions, answers and answer steps", "Continuing the chat, the trace panel, improving the agent", "Neon, Frankfurt", "30 days"],
      ["Feedback, if sent", "Improving the agent", "Neon, Frankfurt", "30 days"],
      [<>Visitor cookie <Term>pa_vid</Term></>, "Quotas and continuing the chat", "Your browser", "30 days from last use"],
      ["Hash of the IP address, with a daily salt", "Abuse prevention", "Neon, Frankfurt", "2 days"],
      ["Quota counters", "Usage limits", "Neon, Frankfurt", "7 days"],
      ["Answers to common opening questions", "Shared cache, not tied to a visitor", "Neon, Frankfurt", "7 days"],
      ["Aggregated daily metrics, with no content and no link to a visitor", "The metrics page", "Neon, Frankfurt", "No limit"],
    ],
    storedNote: "The IP address itself is not stored. Conversations are visible to Sarah, and messages are stored as written.",
    providersTitle: "Who processes the data",
    providers: [
      ["Groq", <>Receives the question, the conversation history and passages from the portfolio, to write the answer. Under its policy content is not retained by default, and logs for troubleshooting or abuse are kept up to 30 days.</>, providers.groq],
      ["Vercel", <>Hosts the site and handles requests, in Frankfurt.</>, providers.vercel],
      ["Neon", <>The database, in Frankfurt.</>, providers.neon],
      ["Langfuse", <>A monitoring tool available to Sarah only, when it is switched on. Emails and phone numbers are masked before sending.</>, providers.langfuse],
    ],
    policy: "Their policy",
    notSent: <>Visitors’ questions are not sent to Google. The question’s embedding is computed on the site’s own server. The cookie and the IP hash are not sent to model providers.</>,
    cookieTitle: "Cookies",
    cookie: <>There is one cookie, required for the site to work. It holds a random id, and page scripts cannot read it. There are no analytics or advertising cookies, so there is no consent banner.</>,
    deleteTitle: "Deleting a conversation",
    deletion: <>The “Delete conversation” button immediately removes the conversation, its messages, steps and feedback from the database. Only the visitor whose cookie owns the conversation can delete it.</>,
    deleteLimits: <>Deletion does not reach Groq’s logs. A daily job removes the traces of the conversation’s answers from Langfuse. The trace of a request that ended without an answer is removed before it is 30 days old, with emails and phone numbers masked until then. Answers in the shared cache are not deleted, since they have no link to a visitor.</>,
    contactTitle: "Privacy questions",
    contact: <>Sarah’s contact details are in her <a href={cvHref} download="Sara Halevy cv.pdf" className="text-accent underline underline-offset-3">CV</a>.</>,
  },
};

export async function generateMetadata({ params }: PageProps<"/[lang]/privacy">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return {
    title: `${copy[lang].title} · ${getDictionary(lang).meta.title}`,
    alternates: alternates(lang, "/privacy"),
  };
}

export default async function PrivacyPage({ params }: PageProps<"/[lang]/privacy">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const c = copy[lang];

  return (
    <DocPage lang={lang} eyebrow={c.eyebrow} title={c.title} lede={c.lede}>
      <p className="mt-3 text-small text-text-muted">{c.updated}</p>

      <Section title={c.storedTitle}>
        <TableFrame label={c.storedTitle}>
          <thead>
            <tr>
              {c.columns.map((name) => (
                <th key={name} scope="col" className={th}>{name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {c.rows.map(([what, why, where, howLong], i) => (
              <tr key={i}>
                <th scope="row" className={`${td} min-w-40 text-start font-normal`}>{what}</th>
                <td className={`${td} min-w-40`}>{why}</td>
                <td className={`${td} whitespace-nowrap`}>{where}</td>
                <td className={`${td} whitespace-nowrap`}>{howLong}</td>
              </tr>
            ))}
          </tbody>
        </TableFrame>
        <p>{c.storedNote}</p>
      </Section>

      <Section title={c.providersTitle}>
        {c.providers.map(([name, text, href]) => (
          <p key={name}>
            <strong>{name}.</strong> {text} <Ext href={href}>{c.policy}</Ext>
          </p>
        ))}
        <p>{c.notSent}</p>
      </Section>

      <Section title={c.cookieTitle}>
        <p>{c.cookie}</p>
      </Section>

      <Section title={c.deleteTitle}>
        <p>{c.deletion}</p>
        <p>{c.deleteLimits}</p>
      </Section>

      <Section title={c.contactTitle}>
        <p>{c.contact}</p>
      </Section>
    </DocPage>
  );
}

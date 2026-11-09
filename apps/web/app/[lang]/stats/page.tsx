import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { StatsBoard, type StatsCopy } from "@/components/StatsBoard";
import { DocPage, Ext, Section, repoFile } from "@/components/ui/DocPage";
import { getDictionary, hasLocale, type Locale } from "../dictionaries";

// S10 (US-9.3). The numbers are never in this file: they come from GET /api/stats, which applies
// the threshold and the rounding. docs/08-transparency.md, section 4.

type Copy = {
  eyebrow: string;
  title: string;
  lede: string;
  board: StatsCopy;
  rulesTitle: string;
  rules: ReactNode[];
  limitsTitle: string;
  limits: ReactNode[];
  sourceTitle: string;
  source: ReactNode;
};

const jobFile = repoFile("backend/portfolio_agent/daily_metrics.py");
const gateFile = repoFile("backend/portfolio_agent/stats.py");

const copy: Record<Locale, Copy> = {
  he: {
    eyebrow: "איך הסוכן מתנהג מול מבקרים",
    title: "מדדים",
    lede: "מהירות ואיכות של הסוכן בפרודקשן, מחושבות פעם ביום מהתשובות עצמן. בלי מספרי שיחות ובלי מספרי מבקרים.",
    board: {
      columns: { measure: "מדד", model: "מודל", windows: { "7": "7 ימים", "30": "30 יום" } },
      none: "אין מספיק נתונים",
      loading: "טוען את המדדים…",
      failedTitle: "המדדים לא נטענו",
      failed: "אפשר לנסות שוב בעוד כמה דקות. הצ׳אט לא תלוי בעמוד הזה.",
      updated: "עודכן לפי ימים שלמים עד",
      notYetTitle: "החישוב עדיין לא רץ",
      notYet: "המדדים מחושבים פעם ביום. אחרי הריצה הראשונה הם יופיעו כאן.",
      fewTitle: "עדיין אין מספיק נתונים",
      few: "מדד מופיע רק כשיש מאחוריו לפחות 30 תצפיות בחלון הזמן. עד אז הוא נשאר ריק, כדי ששיעור לא יחשוף כמה אנשים השתמשו באתר.",
      second: "שנ׳",
      timesTitle: "מהירות",
      times: [
        { key: "total_ms_p50", name: "תשובה מלאה, חציון", hint: "מהרגע שהשאלה הגיעה עד שהתשובה נשמרה" },
        { key: "total_ms_p95", name: "תשובה מלאה, p95" },
        { key: "ttft_ms_warm_p50", name: "מילה ראשונה, בקשה חמה, חציון", hint: "כשהשרת כבר פעיל" },
        { key: "ttft_ms_warm_p95", name: "מילה ראשונה, בקשה חמה, p95" },
        { key: "ttft_ms_cold_p50", name: "מילה ראשונה, בקשה קרה, חציון", hint: "התור הראשון של שרת שרק עלה" },
        { key: "ttft_ms_cold_p95", name: "מילה ראשונה, בקשה קרה, p95" },
      ],
      ratesTitle: "איכות",
      rates: [
        { key: "fallback_rate", name: "מעבר למודל גיבוי", hint: "תשובות שלא נכתבו במודל הראשי" },
        { key: "unanswered_rate", name: "שאלות בלי מענה מהתיק", hint: "הסוכן חיפש בתיק, והתשובה לא ציטטה אף מקור" },
        { key: "cache_rate", name: "תשובות מהמטמון" },
        { key: "citation_removed_rate", name: "תשובות שציטוט בהן נפסל", hint: "הציטוט לא היה בתוצאות החיפוש, ולכן הוסר" },
        { key: "satisfaction_rate", name: "שביעות רצון", hint: "אחוז 👍 מכלל הדירוגים" },
      ],
      modelsTitle: "איזה מודל ענה",
      modelsIntro: "החלק של כל מודל בתשובות שנכתבו, בלי תשובות מהמטמון.",
    },
    rulesTitle: "מה לא מוצג, ולמה",
    rules: [
      <>מדד מופיע רק כשיש מאחוריו לפחות 30 תצפיות בחלון הזמן. כך שיעור לא יכול לחשוף כמה תשובות או דירוגים היו.</>,
      <>שיעורים מעוגלים ל-5% הקרובים, וזמנים ל-0.1 שנייה.</>,
      <>אין גרף יומי, ואין פילוח לפי חברה או לפי שפה. עם מעט מבקרים, כל אחד מהם היה מזהה תנועה.</>,
      <>המספר הגולמי של התצפיות נשאר במסד, ולא יוצא משם. גם תוכן של שאלות ותשובות לא מגיע לכאן.</>,
    ],
    limitsTitle: "מגבלות ידועות",
    limits: [
      <>“בלי מענה” הוא קירוב. אין סימון ישיר לתשובה כזאת, ולכן נספרות תשובות שבהן הסוכן חיפש ולא ציטט. תשובה טובה שנשארה בלי ציטוט תיספר בטעות, וסירוב בלי חיפוש לא ייספר.</>,
      <>הזמנים נמדדים בשרת, ולא כוללים את הדרך ברשת עד הדפדפן. תשובות מהמטמון והתאמות למשרה לא נכללות בהם.</>,
      <>בקשה שנכשלה בלי תשובה לא נספרת באף מדד כאן.</>,
      <>הזמנים נמדדים רק מנובמבר 2026, ולכן בהתחלה יש להם פחות נתונים משאר המדדים.</>,
      <>גם שיחות הבדיקה של שרה באתר נספרות.</>,
    ],
    sourceTitle: "איך זה מחושב",
    source: (
      <>
        עבודה יומית מחשבת את שני החלונות <Ext href={jobFile}>מהתשובות השמורות</Ext>, לפני מחיקת השיחות הישנות. ה-<Ext href={gateFile}>שכבה הציבורית</Ext> מחילה את הסף ואת העיגול.
      </>
    ),
  },
  en: {
    eyebrow: "How the agent behaves with real visitors",
    title: "Metrics",
    lede: "The agent's speed and quality in production, computed once a day from the answers themselves. No conversation counts and no visitor counts.",
    board: {
      columns: { measure: "Measure", model: "Model", windows: { "7": "7 days", "30": "30 days" } },
      none: "Not enough data",
      loading: "Loading the metrics…",
      failedTitle: "The metrics did not load",
      failed: "Try again in a few minutes. The chat does not depend on this page.",
      updated: "Based on whole days through",
      notYetTitle: "The computation has not run yet",
      notYet: "The metrics are computed once a day. They will appear here after the first run.",
      fewTitle: "Not enough data yet",
      few: "A measure appears only with at least 30 observations in its window. Until then it stays empty, so that a rate cannot reveal how many people used the site.",
      second: "s",
      timesTitle: "Speed",
      times: [
        { key: "total_ms_p50", name: "Full answer, median", hint: "From the question arriving to the answer being saved" },
        { key: "total_ms_p95", name: "Full answer, p95" },
        { key: "ttft_ms_warm_p50", name: "First word, warm request, median", hint: "When the server is already running" },
        { key: "ttft_ms_warm_p95", name: "First word, warm request, p95" },
        { key: "ttft_ms_cold_p50", name: "First word, cold request, median", hint: "The first turn of a server that just started" },
        { key: "ttft_ms_cold_p95", name: "First word, cold request, p95" },
      ],
      ratesTitle: "Quality",
      rates: [
        { key: "fallback_rate", name: "Moved to a backup model", hint: "Answers not written by the main model" },
        { key: "unanswered_rate", name: "Questions the portfolio did not answer", hint: "The agent searched, and the answer cites no source" },
        { key: "cache_rate", name: "Answers from the cache" },
        { key: "citation_removed_rate", name: "Answers with a rejected citation", hint: "The citation was not in the search results, so it was removed" },
        { key: "satisfaction_rate", name: "Satisfaction", hint: "Share of 👍 among all ratings" },
      ],
      modelsTitle: "Which model answered",
      modelsIntro: "Each model's share of the written answers, leaving out the cache.",
    },
    rulesTitle: "What is not shown, and why",
    rules: [
      <>A measure appears only with at least 30 observations in its window, so that a rate cannot reveal how many answers or ratings there were.</>,
      <>Rates are rounded to the nearest 5%, and times to 0.1 second.</>,
      <>There is no daily chart and no breakdown by company or language. With few visitors, any of those would identify traffic.</>,
      <>The raw number of observations stays in the database and never leaves it. The text of questions and answers does not reach this page either.</>,
    ],
    limitsTitle: "Known limitations",
    limits: [
      <>“Did not answer” is an approximation. Such an answer has no direct mark, so the count is of answers where the agent searched and cited nothing. A good answer left without a citation is counted by mistake, and a refusal with no search is missed.</>,
      <>Times are measured on the server and leave out the network to the browser. Cached answers and job matches are not included in them.</>,
      <>A request that failed without an answer is not counted in any measure here.</>,
      <>Times are measured only since November 2026, so at first they have less data than the other measures.</>,
      <>Sarah’s own test conversations on the site are counted too.</>,
    ],
    sourceTitle: "How it is computed",
    source: (
      <>
        A daily job computes both windows <Ext href={jobFile}>from the saved answers</Ext>, before old conversations are deleted. The <Ext href={gateFile}>public layer</Ext> applies the threshold and the rounding.
      </>
    ),
  },
};

export async function generateMetadata({ params }: PageProps<"/[lang]/stats">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return { title: `${copy[lang].title} · ${getDictionary(lang).meta.title}` };
}

const List = ({ items }: { items: ReactNode[] }) => (
  <ul className="flex list-disc flex-col gap-1.5 ps-6">
    {items.map((item, i) => (
      <li key={i}>{item}</li>
    ))}
  </ul>
);

export default async function StatsPage({ params }: PageProps<"/[lang]/stats">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const c = copy[lang];

  return (
    <DocPage lang={lang} eyebrow={c.eyebrow} title={c.title} lede={c.lede}>
      <StatsBoard c={c.board} />
      <Section title={c.rulesTitle}>
        <List items={c.rules} />
      </Section>
      <Section title={c.limitsTitle}>
        <List items={c.limits} />
      </Section>
      <Section title={c.sourceTitle}>
        <p>{c.source}</p>
      </Section>
    </DocPage>
  );
}

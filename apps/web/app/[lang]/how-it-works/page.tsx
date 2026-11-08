import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { Callout, DocPage, Ext, Section, Term, adrUrl, repoFile, repoUrl } from "@/components/ui/DocPage";
import { getDictionary, hasLocale, type Locale } from "../dictionaries";

// S13 (US-9.4, US-9.5, US-9.6). The text describes the system as built, not as first planned.

// Attempts that became tests. The public counter is the length of this list (docs/08, section 5).
const challengeCases: { description: string; date: string; commit?: string }[] = [];

type Component = { title: string; body: ReactNode; adrs: [string, string][] };

const adr = {
  loop: ["ADR-0001", "0001-own-agent-loop"],
  single: ["ADR-0002", "0002-single-agent"],
  vercel: ["ADR-0004", "0004-vercel-services"],
  providers: ["ADR-0005", "0005-llm-providers"],
  citations: ["ADR-0006", "0006-streaming-citation-enforcement"],
  tools: ["ADR-0007", "0007-tool-registry-in-process"],
  gemini: ["ADR-0009", "0009-no-free-gemini-in-production"],
  chunking: ["ADR-0010", "0010-chunking"],
  retrieval: ["ADR-0011", "0011-retrieval-method"],
  embeddings: ["ADR-0012", "0012-embeddings-model"],
  query: ["ADR-0013", "0013-query-processing"],
  rerank: ["ADR-0014", "0014-reranking"],
} satisfies Record<string, [string, string]>;

const copy: Record<Locale, {
  eyebrow: string;
  title: string;
  lede: string;
  diagramTitle: string;
  diagramAlt: string;
  componentsTitle: string;
  components: Component[];
  decisions: string;
  reviewTitle: string;
  reviewIntro: string;
  review: ReactNode[];
  challengeTitle: string;
  challenge: ReactNode;
  challengeHow: ReactNode;
  counter: string;
  noCases: string;
  linksTitle: string;
  links: [string, string][];
}> = {
  he: {
    eyebrow: "הקוד, ההחלטות והבדיקות פתוחים",
    title: "איך הסוכן עובד",
    lede: "הסוכן עונה רק מתוך תיק העבודות של שרה. הוא מחפש בתיק, כותב תשובה, והשרת בודק כל ציטוט לפני שהוא מגיע למסך.",
    diagramTitle: "הדרך של שאלה אחת",
    diagramAlt:
      "השאלה עוברת מהדפדפן לשרת FastAPI ב-Vercel. השרת בודק מכסות ואורך, ומפעיל לולאת סוכן של עד 4 סבבים מול Groq. הסוכן מחפש בתיק דרך כלים, והחיפוש רץ על Neon Postgres. התשובה עוברת סינון בזמן ההזרמה, וחוזרת לדפדפן. GitHub Actions מריץ בדיקות לפני כל פריסה.",
    componentsTitle: "הרכיבים, ולמה הם קיימים",
    components: [
      {
        title: "לולאת סוכן שנכתבה ביד",
        body: <>המודל בוחר אם לחפש או לענות, עד 4 סבבים. בלי framework, כדי שכל צעד יישלח למסך ויופיע בחלון המעקב.</>,
        adrs: [adr.loop, adr.single],
      },
      {
        title: "כלים לקריאה בלבד",
        body: <>לסוכן יש שני כלים: <Term>search_portfolio</Term> ו-<Term>get_project</Term>. אף אחד מהם לא כותב ולא ניגש לאינטרנט, ולכן גם הזרקת הוראות לא יכולה להפעיל פעולה חיצונית.</>,
        adrs: [adr.tools],
      },
      {
        title: "חיפוש בארבעה שלבים",
        body: <>חיפוש מילים ב-Postgres, חיפוש וקטורי, מיזוג של שתי הרשימות, ומודל שפה שמסדר מחדש את עשרת הראשונים. כל שלב נכנס רק אחרי שמדידה הראתה שהוא מועיל, והמספרים ב<Link href="quality" className="text-accent underline underline-offset-3">עמוד האיכות</Link>.</>,
        adrs: [adr.chunking, adr.retrieval, adr.embeddings, adr.query, adr.rerank],
      },
      {
        title: "אכיפת ציטוטים בזמן ההזרמה",
        body: <>המודל מסמן כל מקור, והשרת בודק שהקטע באמת נשלף בשיחה. ציטוט שלא עובר נמחק לפני שהוא מוצג. אותו סינון חוסם גם דליפת הנחיות, מיילים ומספרי טלפון.</>,
        adrs: [adr.citations],
      },
      {
        title: "מודלים וגיבוי",
        body: <>התשובות נכתבות במודלים פתוחים דרך Groq. כשהמכסה של המודל הראשי נגמרת, הבקשה עוברת למודל גיבוי והתשובה מסומנת בהתאם. שאלות של מבקרים לא נשלחות ל-Google.</>,
        adrs: [adr.providers, adr.gemini],
      },
      {
        title: "שירות אחד שמחליט",
        body: <>כל הלוגיקה נמצאת ב-FastAPI, והממשק רק מציג. המפתחות נשארים בשרת, ו-Postgres אחד מחזיק את התיק, השיחות, המכסות והמטמון.</>,
        adrs: [adr.vercel],
      },
    ],
    decisions: "החלטות:",
    reviewTitle: "מסלול בדיקה של 10 דקות",
    reviewIntro: "למהנדסים שרוצים להעריך את הפרויקט, לפי הסדר:",
    review: [
      <>העמוד הזה.</>,
      <><Ext href={adrUrl(adr.loop[1])}>ADR-0001</Ext> (הלולאה), <Ext href={adrUrl(adr.citations[1])}>ADR-0006</Ext> (ציטוטים) ו-<Ext href={adrUrl(adr.retrieval[1])}>ADR-0011</Ext> (שיטת השליפה).</>,
      <><Ext href={repoFile("docs/experiments/retrieval-2026-11-04.md")}>דוח הניסויים</Ext>, כולל מה שלא עבד.</>,
      <>הקוד של הלולאה: <Ext href={repoFile("backend/portfolio_agent/agent/loop.py")}><Term>agent/loop.py</Term></Ext>.</>,
      <>הרצה מקומית: <Term>make setup</Term> ואז <Term>make test</Term>. צריך Docker בשביל Postgres.</>,
    ],
    challengeTitle: "האתגר הפתוח",
    challenge: <>מוזמנים לנסות לגרום לסוכן להמציא טענה על שרה, לחשוף את ההנחיות שלו, לפעול לפי הוראות של מבקר או למסור מידע שאסור לו למסור.</>,
    challengeHow: <>הצלחתם? לוחצים 👎 מתחת לתשובה ומסמנים ״זה ניסיון באתגר״. מקרה אמיתי יהפוך לבדיקה קבועה, ואחרי התיקון יופיע כאן בלי פרטים מזהים.</>,
    counter: "ניסיונות שהפכו לבדיקות:",
    noCases: "עדיין אין מקרים ברשימה.",
    linksTitle: "לקריאה נוספת",
    links: [
      ["הקוד ב-GitHub", repoUrl()],
      ["כל ה-ADRs", repoUrl("tree/main/docs/adr")],
      ["ריצות ה-CI", repoUrl("actions")],
    ],
  },
  en: {
    eyebrow: "The code, the decisions and the tests are open",
    title: "How the agent works",
    lede: "The agent answers only from Sarah's portfolio. It searches the portfolio, writes an answer, and the server checks every citation before it reaches the screen.",
    diagramTitle: "The path of one question",
    diagramAlt:
      "The question goes from the browser to a FastAPI server on Vercel. The server checks quotas and length, then runs an agent loop of up to 4 rounds against Groq. The agent searches the portfolio through tools, and search runs on Neon Postgres. The answer is filtered while it streams and returns to the browser. GitHub Actions runs the tests before every deploy.",
    componentsTitle: "The components, and why they exist",
    components: [
      {
        title: "A hand-written agent loop",
        body: <>The model chooses to search or to answer, for up to 4 rounds. No framework, so every step can be streamed and shown in the trace panel.</>,
        adrs: [adr.loop, adr.single],
      },
      {
        title: "Read-only tools",
        body: <>The agent has two tools: <Term>search_portfolio</Term> and <Term>get_project</Term>. Neither writes or reaches the internet, so an injected instruction has no external action to trigger.</>,
        adrs: [adr.tools],
      },
      {
        title: "Search in four stages",
        body: <>Keyword search in Postgres, vector search, a merge of the two lists, and a language model that reorders the top ten. Each stage went in only after a measurement showed it helped. The numbers are on the <Link href="quality" className="text-accent underline underline-offset-3">quality page</Link>.</>,
        adrs: [adr.chunking, adr.retrieval, adr.embeddings, adr.query, adr.rerank],
      },
      {
        title: "Citations enforced while streaming",
        body: <>The model marks each source, and the server checks that the passage was really retrieved in this conversation. A citation that fails is removed before it is shown. The same filter blocks prompt leaks, emails and phone numbers.</>,
        adrs: [adr.citations],
      },
      {
        title: "Models and fallback",
        body: <>Answers are written by open models through Groq. When the primary model’s quota runs out, the request moves to a fallback model and the answer is labeled. Visitors’ questions are not sent to Google.</>,
        adrs: [adr.providers, adr.gemini],
      },
      {
        title: "One service that decides",
        body: <>All the logic lives in FastAPI, and the interface only displays. Keys stay on the server, and one Postgres holds the portfolio, the conversations, the quotas and the cache.</>,
        adrs: [adr.vercel],
      },
    ],
    decisions: "Decisions:",
    reviewTitle: "A 10-minute review path",
    reviewIntro: "For engineers evaluating the project, in order:",
    review: [
      <>This page.</>,
      <><Ext href={adrUrl(adr.loop[1])}>ADR-0001</Ext> (the loop), <Ext href={adrUrl(adr.citations[1])}>ADR-0006</Ext> (citations) and <Ext href={adrUrl(adr.retrieval[1])}>ADR-0011</Ext> (retrieval method).</>,
      <>The <Ext href={repoFile("docs/experiments/retrieval-2026-11-04.md")}>experiments report</Ext>, including what did not work.</>,
      <>The loop itself: <Ext href={repoFile("backend/portfolio_agent/agent/loop.py")}><Term>agent/loop.py</Term></Ext>.</>,
      <>Run it locally: <Term>make setup</Term>, then <Term>make test</Term>. Postgres needs Docker.</>,
    ],
    challengeTitle: "The open challenge",
    challenge: <>Try to make the agent invent a claim about Sarah, reveal its instructions, follow a visitor’s orders, or give out information it must not share.</>,
    challengeHow: <>Did it work? Click 👎 under the answer and check “This was a challenge attempt”. A real case becomes a permanent test and, once fixed, appears here with no identifying details.</>,
    counter: "Attempts that became tests:",
    noCases: "No cases on the list yet.",
    linksTitle: "Further reading",
    links: [
      ["The code on GitHub", repoUrl()],
      ["All ADRs", repoUrl("tree/main/docs/adr")],
      ["CI runs", repoUrl("actions")],
    ],
  },
};

function Box({ title, note, tone = "plain" }: { title: string; note?: string; tone?: "plain" | "strong" }) {
  const look = tone === "strong" ? "border-border-strong bg-surface-raised" : "border-border bg-surface-raised";
  return (
    <div className={`flex-1 rounded-md border px-3 py-2 ${look}`}>
      <p className="text-ui font-bold">{title}</p>
      {note && <p className="mono text-trace text-text-muted">{note}</p>}
    </div>
  );
}

function Arrow({ label }: { label: string }) {
  return (
    <p className="mono py-1 text-center text-trace text-text-muted" aria-hidden="true">
      ↓ {label}
    </p>
  );
}

// Always left to right and in English, like every diagram in the design (docs/design/README.md).
function Diagram({ title, alt }: { title: string; alt: string }) {
  return (
    <figure className="rounded-lg border border-border bg-surface-sunken p-3 md:p-4">
      <figcaption className="sr-only">
        {title}. {alt}
      </figcaption>
      <div dir="ltr" lang="en" aria-hidden="true">
        <Box title="Browser" note="Next.js · chat · trace panel" />
        <Arrow label="POST /api/chat · answer streams back over SSE" />
        <div className="rounded-md border border-dashed border-border-input p-2">
          <p className="mono mb-2 text-trace text-text-muted">FastAPI on Vercel · fra1</p>
          <div className="flex flex-col gap-2 md:flex-row">
            <Box title="Guards" note="length · quotas" />
            <Box title="Agent loop" note="up to 4 rounds" tone="strong" />
            <Box title="Stream filters" note="citations · canary · email · phone" />
          </div>
        </div>
        <Arrow label="tool calls and model calls" />
        <div className="flex flex-col gap-2 md:flex-row">
          <Box title="Tools" note="search_portfolio · get_project" />
          <Box title="Groq" note="primary model · fallbacks · rerank" />
          <Box title="Neon Postgres" note="eu-central-1 · pgvector · pg_trgm" />
        </div>
        <Arrow label="before every deploy" />
        <Box title="GitHub Actions" note="tests · evals · deploy to Vercel" />
      </div>
    </figure>
  );
}

export async function generateMetadata({ params }: PageProps<"/[lang]/how-it-works">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return { title: `${copy[lang].title} · ${getDictionary(lang).meta.title}` };
}

export default async function HowItWorksPage({ params }: PageProps<"/[lang]/how-it-works">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const c = copy[lang];

  return (
    <DocPage lang={lang} eyebrow={c.eyebrow} title={c.title} lede={c.lede}>
      <Section title={c.diagramTitle}>
        <Diagram title={c.diagramTitle} alt={c.diagramAlt} />
      </Section>

      <Section title={c.componentsTitle}>
        {c.components.map((item) => (
          <div key={item.title}>
            <h3 className="text-[18px] font-bold">{item.title}</h3>
            <p>{item.body}</p>
            <p className="text-small text-text-muted">
              {c.decisions}{" "}
              {item.adrs.map(([label, file], i) => (
                <span key={file}>
                  {i > 0 && ", "}
                  <Ext href={adrUrl(file)}>{label}</Ext>
                </span>
              ))}
            </p>
          </div>
        ))}
      </Section>

      <Section title={c.reviewTitle}>
        <p>{c.reviewIntro}</p>
        <ol className="flex list-decimal flex-col gap-1.5 ps-6">
          {c.review.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      </Section>

      <Section title={c.challengeTitle}>
        <p>{c.challenge}</p>
        <p>{c.challengeHow}</p>
        <Callout title={`${c.counter} ${challengeCases.length}`}>
          {challengeCases.length === 0 ? c.noCases : challengeCases.map((item) => `${item.date}: ${item.description}`).join(" · ")}
        </Callout>
      </Section>

      <Section title={c.linksTitle}>
        <ul className="flex flex-col gap-1.5">
          {c.links.map(([label, href]) => (
            <li key={href}>
              <Ext href={href}>{label}</Ext>
            </li>
          ))}
        </ul>
      </Section>
    </DocPage>
  );
}

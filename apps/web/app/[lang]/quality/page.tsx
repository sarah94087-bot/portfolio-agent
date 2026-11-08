import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import data from "@/data/quality.json";
import { Callout, DocPage, Ext, Section, TableFrame, Term, adrUrl, repoFile, td, th } from "@/components/ui/DocPage";
import { interval, num, parseQuality, signed, signedFine, type Experiment, type Quality, type Score } from "@/lib/quality";
import { getDictionary, hasLocale, type Locale } from "../dictionaries";

// S9 (US-9.1, US-9.2). Every number comes from data/quality.json, built from evals/results.
const quality = parseQuality(data);

type Copy = {
  eyebrow: string;
  title: string;
  lede: string;
  statusTitle: string;
  status: (q: Quality) => ReactNode;
  scoreTitle: string;
  scoreIntro: (q: Quality) => ReactNode;
  group: Record<Score["group"], string>;
  columns: { measure: string; value: string; interval: string; threshold: string; result: string };
  passed: string;
  failed: string;
  noThreshold: string;
  pendingTitle: string;
  pendingIntro: string;
  pendingColumns: { measure: string; threshold: string; status: string };
  pendingStatus: string;
  pending: [string, string][];
  experimentsTitle: string;
  experimentsIntro: ReactNode;
  methodColumns: { method: string; all: string; he: string; crossLingual: string; mrr: string };
  chosenTag: string;
  meta: (e: Experiment) => string;
  methods: Record<string, string>;
  hybridTitle: string;
  hybridWhy: ReactNode;
  rerankTitle: string;
  rerankWhy: (q: Quality) => ReactNode;
  limitsTitle: string;
  limits: (q: Quality) => ReactNode[];
  reproduceTitle: string;
  reproduce: ReactNode;
};

const measureName = (s: Score, group: Copy["group"]) => `${s.metric === "mrr" ? "MRR" : "Recall@5"} · ${group[s.group]}`;

const copy: Record<Locale, Copy> = {
  he: {
    eyebrow: "כמה הסוכן טוב, ואיך זה נמדד",
    title: "איכות",
    lede: "כל מספר כאן מחושב מקבצי התוצאות שב-repo. גם מה שעוד לא נמדד, ומה שלא טוב מספיק, מופיע כאן.",
    statusTitle: "עדיין אין ציון רשמי",
    status: (q) => (
      <>
        המספרים בעמוד הם ממדידות פיתוח, על <Term>{q.latest.questions}</Term> שאלות מקבוצת <Term>dev</Term>. קבוצת <Term>test</Term> שמורה להרצה הרשמית ועדיין לא רצה. תאריך ההרצה, גרסת ההנחיה והמגמה לאורך גרסאות יתווספו אחריה.
      </>
    ),
    scoreTitle: "החיפוש: המדידה האחרונה",
    scoreIntro: (q) => (
      <>
        נמדד ב-<Term>{q.latest.date}</Term>, ב-commit <Term>{q.latest.commit}</Term>. <Term>Recall@5</Term> הוא החלק מהקטעים הנכונים שנמצאו בחמש התוצאות הראשונות. הטווח הוא רווח סמך של 95%.
      </>
    ),
    group: { all: "כולל", he: "עברית", en: "אנגלית", cross_lingual: "בין שפות" },
    columns: { measure: "מדד", value: "ערך", interval: "טווח", threshold: "סף", result: "תוצאה" },
    passed: "עובר",
    failed: "לא עובר",
    noThreshold: "אין סף",
    pendingTitle: "התשובות וההגנות",
    pendingIntro: "הספים נקבעו מראש. התוצאות יפורסמו אחרי ההרצה הרשמית.",
    pendingColumns: { measure: "מדד", threshold: "סף", status: "מצב" },
    pendingStatus: "ממתין",
    pending: [
      ["נאמנות למקורות, ברמת טענה", "≥ 0.98"],
      ["המצאות מאומתות", "0"],
      ["דיוק ציטוטים", "≥ 0.95"],
      ["תקינות ציטוטים", "100%"],
      ["סירוב נכון", "≥ 95%"],
      ["סירוב שגוי", "≤ 5%"],
      ["התאמת שפה", "100%"],
      ["דליפת הנחיות, הזרקה מוצלחת, דליפת מידע פרטי", "0"],
      ["התאמה חזקה שגויה למשרה", "0"],
      ["כיסוי פערים בהתאמה למשרה", "≥ 0.90"],
    ],
    experimentsTitle: "ניסויי השליפה",
    experimentsIntro: (
      <>
        כל שיטה רצה על אותן שאלות, וההשוואה נעשית שאלה מול שאלה. הפירוט המלא ב<Ext href={repoFile("docs/experiments/retrieval-2026-11-04.md")}>דוח הניסויים</Ext>.
      </>
    ),
    methodColumns: { method: "שיטה", all: "Recall@5", he: "עברית", crossLingual: "בין שפות", mrr: "MRR" },
    chosenTag: "נבחרה",
    meta: (e) => `${e.date} · ${e.commit} · ${e.questions} שאלות dev`,
    methods: { R1: "R1 · מילים", R2: "R2 · וקטורים", R3: "R3 · היברידי", R4: "R4 · היברידי ו-rerank" },
    hybridTitle: "האם מיזוג מצדיק רכיב נוסף?",
    hybridWhy: (
      <>
        R1 ו-R2 טועים בשאלות שונות, ולכן המיזוג טוב משניהם באופן מובהק. <Ext href={adrUrl("0011-retrieval-method")}>ADR-0011</Ext>
      </>
    ),
    rerankTitle: "האם rerank שווה את הזמן ואת המכסה?",
    rerankWhy: (q) => (
      <>
        R3 לבדו לא עבר את הסף הכולל. R4 מוסיף <Term>{signed(q.rerank.difference.all.mean)}</Term> בטווח <Term>{interval(q.rerank.difference.all)}</Term>, והוא נבחר למרות העלות: כ-2,300 טוקנים לשאלה. <Ext href={adrUrl("0014-reranking")}>ADR-0014</Ext>
      </>
    ),
    limitsTitle: "מגבלות ידועות",
    limits: (q) => [
      <>שאלות <Term>dev</Term> שימשו גם לשיפור המערכת, ולכן המספרים עשויים להיות אופטימיים.</>,
      <>המדידה נעשתה על <Term>{q.latest.chunks}</Term> קטעים. התיק גדל מאז, והמדידה לא חזרה על המצב החדש.</>,
      <>בעברית השיפור של R4 מובהק בקושי: הגבול התחתון הוא <Term>{signedFine(q.rerank.difference.he.low)}</Term>.</>,
      <>R4 שיפר <Term>{q.rerank.improved}</Term> שאלות והרע <Term>{q.rerank.worsened}</Term>. ב-<Term>{q.rerank.still_missing}</Term> שאלות עדיין חסר קטע בחמש הראשונות.</>,
      <>מודל ה-rerank אינו דטרמיניסטי. הטבלה מציגה את הריצה האחרונה מתוך שלוש.</>,
      <>כשהמכסה היומית של המודל נסגרת, החיפוש חוזר לסדר של R3, שהוא פחות טוב.</>,
      <>בקשה ראשונה אחרי זמן בלי שימוש איטית יותר, ושאלה שמגיעה מיד אחרי שאלה כבדה עלולה לעבור למודל גיבוי.</>,
    ],
    reproduceTitle: "לשחזר את המספרים",
    reproduce: (
      <>
        הציונים לכל שאלה נשמרים ב-<Ext href="https://github.com/sarah94087-bot/portfolio-agent/tree/main/evals/results"><Term>evals/results</Term></Ext>, והפקודה <Term>python evals/publish_quality.py</Term> מחשבת מהם את העמוד הזה. הרצה מחדש של הניסוי: <Term>python -m retrieval.run_stage4</Term> מתוך <Term>evals/</Term>, מול Postgres מקומי.
      </>
    ),
  },
  en: {
    eyebrow: "How good the agent is, and how that is measured",
    title: "Quality",
    lede: "Every number here is computed from the result files in the repo. What has not been measured yet, and what is not good enough, is shown too.",
    statusTitle: "No official score yet",
    status: (q) => (
      <>
        The numbers on this page are development measurements, on <Term>{q.latest.questions}</Term> questions from the <Term>dev</Term> split. The <Term>test</Term> split is reserved for the official run, which has not happened. The run date, prompt version and the trend across versions will be added after it.
      </>
    ),
    scoreTitle: "Search: the latest measurement",
    scoreIntro: (q) => (
      <>
        Measured on <Term>{q.latest.date}</Term>, at commit <Term>{q.latest.commit}</Term>. <Term>Recall@5</Term> is the share of the correct passages found in the top five results. The range is a 95% confidence interval.
      </>
    ),
    group: { all: "overall", he: "Hebrew", en: "English", cross_lingual: "cross-lingual" },
    columns: { measure: "Measure", value: "Value", interval: "Range", threshold: "Threshold", result: "Result" },
    passed: "Pass",
    failed: "Fail",
    noThreshold: "No threshold",
    pendingTitle: "Answers and defenses",
    pendingIntro: "The thresholds were set in advance. Results will be published after the official run.",
    pendingColumns: { measure: "Measure", threshold: "Threshold", status: "Status" },
    pendingStatus: "Pending",
    pending: [
      ["Faithfulness to sources, per claim", "≥ 0.98"],
      ["Confirmed fabrications", "0"],
      ["Citation precision", "≥ 0.95"],
      ["Citation validity", "100%"],
      ["Correct refusals", "≥ 95%"],
      ["False refusals", "≤ 5%"],
      ["Language match", "100%"],
      ["Prompt leaks, successful injections, private data leaks", "0"],
      ["False strong match in job fit", "0"],
      ["Gap coverage in job fit", "≥ 0.90"],
    ],
    experimentsTitle: "Retrieval experiments",
    experimentsIntro: (
      <>
        Every method ran on the same questions, compared question by question. Full detail is in the <Ext href={repoFile("docs/experiments/retrieval-2026-11-04.md")}>experiments report</Ext>.
      </>
    ),
    methodColumns: { method: "Method", all: "Recall@5", he: "Hebrew", crossLingual: "Cross-lingual", mrr: "MRR" },
    chosenTag: "Chosen",
    meta: (e) => `${e.date} · ${e.commit} · ${e.questions} dev questions`,
    methods: { R1: "R1 · keywords", R2: "R2 · vectors", R3: "R3 · hybrid", R4: "R4 · hybrid + rerank" },
    hybridTitle: "Does merging justify another component?",
    hybridWhy: (
      <>
        R1 and R2 miss different questions, so the merge is significantly better than either. <Ext href={adrUrl("0011-retrieval-method")}>ADR-0011</Ext>
      </>
    ),
    rerankTitle: "Is reranking worth the time and the quota?",
    rerankWhy: (q) => (
      <>
        R3 alone did not reach the overall threshold. R4 adds <Term>{signed(q.rerank.difference.all.mean)}</Term>, range <Term>{interval(q.rerank.difference.all)}</Term>, and was chosen despite the cost of about 2,300 tokens per question. <Ext href={adrUrl("0014-reranking")}>ADR-0014</Ext>
      </>
    ),
    limitsTitle: "Known limitations",
    limits: (q) => [
      <>The <Term>dev</Term> questions were also used to improve the system, so these numbers may be optimistic.</>,
      <>Measured on <Term>{q.latest.chunks}</Term> passages. The portfolio has grown since, and the measurement has not been repeated on it.</>,
      <>In Hebrew, R4’s improvement is barely significant: the lower bound is <Term>{signedFine(q.rerank.difference.he.low)}</Term>.</>,
      <>R4 improved <Term>{q.rerank.improved}</Term> questions and worsened <Term>{q.rerank.worsened}</Term>. <Term>{q.rerank.still_missing}</Term> questions still miss a passage in the top five.</>,
      <>The rerank model is not deterministic. The table shows the last of three runs.</>,
      <>When the model’s daily quota closes, search falls back to the R3 order, which is weaker.</>,
      <>The first request after an idle period is slower, and a question sent right after a heavy one may move to a fallback model.</>,
    ],
    reproduceTitle: "Reproduce the numbers",
    reproduce: (
      <>
        Per-question scores are kept in <Ext href="https://github.com/sarah94087-bot/portfolio-agent/tree/main/evals/results"><Term>evals/results</Term></Ext>, and <Term>python evals/publish_quality.py</Term> computes this page from them. To rerun the experiment: <Term>python -m retrieval.run_stage4</Term> from <Term>evals/</Term>, against a local Postgres.
      </>
    ),
  },
};

function ExperimentTable({ e, c, label }: { e: Experiment; c: Copy; label: string }) {
  const m = c.methodColumns;
  return (
    <TableFrame label={label}>
      <thead>
        <tr>
          <th scope="col" className={th}>{m.method}</th>
          <th scope="col" className={th}>{m.all}</th>
          <th scope="col" className={th}>{m.he}</th>
          <th scope="col" className={th}>{m.crossLingual}</th>
          <th scope="col" className={th}>{m.mrr}</th>
        </tr>
      </thead>
      <tbody>
        {e.rows.map((r) => {
          const chosen = r.method === e.chosen;
          return (
            <tr key={r.method} className={chosen ? "font-bold" : undefined}>
              <th scope="row" className={`${td} whitespace-nowrap text-start`}>
                {c.methods[r.method] ?? r.method}
                {chosen && <span className="ms-2 rounded-sm bg-accent px-1.5 text-small text-on-accent">{c.chosenTag}</span>}
              </th>
              <td className={`${td} mono whitespace-nowrap`}>
                <bdi>{num(r.all.mean)} {interval(r.all)}</bdi>
              </td>
              <td className={`${td} mono`}>{num(r.he.mean)}</td>
              <td className={`${td} mono`}>{num(r.cross_lingual.mean)}</td>
              <td className={`${td} mono`}>{num(r.mrr.mean)}</td>
            </tr>
          );
        })}
      </tbody>
    </TableFrame>
  );
}

export async function generateMetadata({ params }: PageProps<"/[lang]/quality">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  return { title: `${copy[lang].title} · ${getDictionary(lang).meta.title}` };
}

export default async function QualityPage({ params }: PageProps<"/[lang]/quality">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const c = copy[lang];
  const q = quality;

  return (
    <DocPage lang={lang} eyebrow={c.eyebrow} title={c.title} lede={c.lede}>
      <Callout title={c.statusTitle}>{c.status(q)}</Callout>

      <Section title={c.scoreTitle}>
        <p>{c.scoreIntro(q)}</p>
        <TableFrame label={c.scoreTitle}>
          <thead>
            <tr>
              <th scope="col" className={th}>{c.columns.measure}</th>
              <th scope="col" className={th}>{c.columns.value}</th>
              <th scope="col" className={th}>{c.columns.interval}</th>
              <th scope="col" className={th}>{c.columns.threshold}</th>
              <th scope="col" className={th}>{c.columns.result}</th>
            </tr>
          </thead>
          <tbody>
            {q.scorecard.map((s) => (
              <tr key={`${s.metric}-${s.group}`}>
                <th scope="row" className={`${td} whitespace-nowrap text-start font-normal`}>{measureName(s, c.group)}</th>
                <td className={`${td} mono font-bold`}>{num(s.mean)}</td>
                <td className={`${td} mono whitespace-nowrap`}><bdi>{interval(s)}</bdi></td>
                <td className={`${td} mono whitespace-nowrap`}><bdi>{s.threshold === null ? "—" : `≥ ${num(s.threshold)}`}</bdi></td>
                <td className={`${td} whitespace-nowrap`}>{s.passed === null ? c.noThreshold : s.passed ? `✓ ${c.passed}` : `✕ ${c.failed}`}</td>
              </tr>
            ))}
          </tbody>
        </TableFrame>
      </Section>

      <Section title={c.pendingTitle}>
        <p>{c.pendingIntro}</p>
        <TableFrame label={c.pendingTitle}>
          <thead>
            <tr>
              <th scope="col" className={th}>{c.pendingColumns.measure}</th>
              <th scope="col" className={th}>{c.pendingColumns.threshold}</th>
              <th scope="col" className={th}>{c.pendingColumns.status}</th>
            </tr>
          </thead>
          <tbody>
            {c.pending.map(([name, threshold]) => (
              <tr key={name}>
                <th scope="row" className={`${td} text-start font-normal`}>{name}</th>
                <td className={`${td} mono whitespace-nowrap`}><bdi>{threshold}</bdi></td>
                <td className={`${td} whitespace-nowrap text-text-muted`}>{c.pendingStatus}</td>
              </tr>
            ))}
          </tbody>
        </TableFrame>
      </Section>

      <Section title={c.experimentsTitle}>
        <p>{c.experimentsIntro}</p>
        <h3 className="mt-2 text-[18px] font-bold">{c.hybridTitle}</h3>
        <p className="mono text-trace text-text-muted"><bdi>{c.meta(q.hybrid)}</bdi></p>
        <ExperimentTable e={q.hybrid} c={c} label={c.hybridTitle} />
        <p>{c.hybridWhy}</p>
        <h3 className="mt-2 text-[18px] font-bold">{c.rerankTitle}</h3>
        <p className="mono text-trace text-text-muted"><bdi>{c.meta(q.rerank)}</bdi></p>
        <ExperimentTable e={q.rerank} c={c} label={c.rerankTitle} />
        <p>{c.rerankWhy(q)}</p>
      </Section>

      <Section title={c.limitsTitle}>
        <ul className="flex list-disc flex-col gap-1.5 ps-6">
          {c.limits(q).map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </Section>

      <Section title={c.reproduceTitle}>
        <p>{c.reproduce}</p>
      </Section>
    </DocPage>
  );
}

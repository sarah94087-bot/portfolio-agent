// Server-only by convention: client components get the strings they need as props.

export const locales = ["he", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "he";

export const hasLocale = (value: string): value is Locale =>
  (locales as readonly string[]).includes(value);

export const directionOf = (locale: Locale) => (locale === "he" ? "rtl" : "ltr");

// Copy for S1 and the shell, taken from the Claude Design boards "Main" and "S1-EN".
// Neither language is the translated one: edit both together.
const he = {
  meta: {
    title: "הסוכן של שרה",
    description: "סוכן AI שעונה על שאלות על הניסיון של שרה הלוי, עם מקורות לכל טענה",
  },
  header: {
    agentName: "הסוכן של שרה",
    aiTag: "סוכן AI",
    nav: "ניווט ראשי",
    howItWorks: "איך זה עובד",
    quality: "איכות",
    language: "שפה",
    downloadCv: "הורדת קו״ח",
  },
  welcome: {
    eyebrow: "עונה מתוך תיק העבודות של שרה הלוי",
    titleLead: "אני סוכן AI,",
    titleHighlight: "לא שרה.",
    titleRest: "אני עונה רק ממה שכתוב בתיק שלה.",
    lede: "לכל טענה יש מקור שאפשר ללחוץ עליו, ואפשר לפתוח ולראות איך התשובה נבנתה. אם אין לי מידע על משהו, אגיד את זה.",
    startersLabel: "שאלות לפתיחה",
    starters: [
      "על מה היא עובדת הכי טוב?",
      "מה הפרויקט הכי מורכב שלה?",
      "איך היא ניגשת לבעיה הנדסית חדשה?",
      "יש לי משרה, תבדוק התאמה",
    ],
    privacy: "השיחות נשמרות 30 יום ועוברות דרך ספקי מודלים חיצוניים.",
    privacyLink: "מדיניות פרטיות",
  },
  composer: {
    questionLabel: "שאלה על הניסיון של שרה",
    questionPlaceholder: "שאלו משהו על הניסיון של שרה…",
    jobLabel: "תיאור המשרה",
    jobPlaceholder: "הדביקו כאן את תיאור המשרה…",
    pasteJob: "הדבקת משרה",
    backToQuestion: "חזרה לשאלה",
    send: "שליחה",
    counter: "{n} מתוך {max} תווים",
    overLimit: "ארוך מדי לשליחה",
  },
};

export type Dictionary = typeof he;

const en: Dictionary = {
  meta: {
    title: "Sarah's agent",
    description: "An AI agent that answers questions about Sarah Halevi's experience, with a source for every claim",
  },
  header: {
    agentName: "Sarah's agent",
    aiTag: "AI agent",
    nav: "Main",
    howItWorks: "How it works",
    quality: "Quality",
    language: "Language",
    downloadCv: "Download CV",
  },
  welcome: {
    eyebrow: "Answers from the portfolio of Sarah Halevi",
    titleLead: "I'm an AI agent,",
    titleHighlight: "not Sarah.",
    titleRest: "I only answer from what's in her portfolio.",
    lede: "Every claim has a source you can open, and you can inspect how the answer was built. If I don't have information on something, I'll say so.",
    startersLabel: "Starter questions",
    starters: [
      "What is she strongest at?",
      "What's her most complex project?",
      "How does she approach a new engineering problem?",
      "I have a job posting, check the fit",
    ],
    privacy: "Conversations are stored for 30 days and pass through external model providers.",
    privacyLink: "Privacy policy",
  },
  composer: {
    questionLabel: "Question about Sarah's experience",
    questionPlaceholder: "Ask about Sarah's experience…",
    jobLabel: "Job description",
    jobPlaceholder: "Paste the job description here…",
    pasteJob: "Paste a job posting",
    backToQuestion: "Back to a question",
    send: "Send",
    counter: "{n} of {max} characters",
    overLimit: "Too long to send",
  },
};

const dictionaries: Record<Locale, Dictionary> = { he, en };

export const getDictionary = (locale: Locale): Dictionary => dictionaries[locale];

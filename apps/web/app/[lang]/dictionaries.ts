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
  // S2. Impersonal wording, never a gendered "you" (docs/06-agent-design.md, section 10).
  chat: {
    answerLabel: "תשובת הסוכן",
    followUpPlaceholder: "שאלה נוספת…",
    thinking: "הסוכן חושב…",
    searching: "מחפש בתיק הפרויקטים…",
    opening: "פותח את הרשומה…",
    restarting: "המודל נפל באמצע. עובר למודל גיבוי…",
    sources: "מקורות",
    source: "מקור {n}",
    close: "סגירה",
    steps: { one: "צעד אחד", other: "{n} צעדים" },
    seconds: "{n} שנ׳",
    tokens: "{n} טוקנים",
    sourcesCount: { one: "מקור אחד", other: "{n} מקורות" },
    fallback: "מודל גיבוי",
    cached: "מהמטמון",
    retry: "לנסות שוב",
    errors: {
      disconnected: "החיבור נקטע לפני שהתשובה הסתיימה.",
      unreachable: "לא הצלחנו להגיע לשרת. אפשר לנסות שוב בעוד רגע.",
      minute: "יותר מדי הודעות בדקה האחרונה. אפשר לנסות שוב בעוד {n} שניות.",
      day: "המכסה היומית של השיחה עם הסוכן נוצלה. אפשר לחזור מחר, או להוריד את קורות החיים.",
      conversation: "השיחה הזו הגיעה לאורך המרבי. אפשר להתחיל שיחה חדשה.",
      unavailable: "כרגע אין מודל זמין לענות. אפשר לנסות שוב בעוד כמה דקות, או להוריד את קורות החיים.",
      tooLong: "ההודעה ארוכה מדי. המגבלה היא 1,000 תווים.",
      internal: "משהו השתבש אצלנו.",
    },
    newConversation: "שיחה חדשה",
    // US-2.7, board S2-States (e).
    feedback: {
      up: "תשובה מועילה",
      down: "תשובה לא מועילה",
      thanks: "תודה.",
      thanksMore: "תודה. אפשר להוסיף פירוט.",
      commentLabel: "מה לא עבד? (אופציונלי)",
      counter: "{n} / {max}",
      challenge: "זה ניסיון באתגר",
      challengeHint: "מוזמנים לנסות לגרום לסוכן לשקר. דיווחים עוברים דרך הכפתור הזה.",
      send: "שליחת דיווח",
      cancel: "ביטול",
      sent: "תודה על הדיווח.",
      failed: "המשוב לא נשמר. אפשר לנסות שוב.",
      limited: "נשלח היום הרבה משוב. אפשר לנסות שוב מחר.",
    },
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
  chat: {
    answerLabel: "The agent's answer",
    followUpPlaceholder: "Ask a follow-up…",
    thinking: "The agent is thinking…",
    searching: "Searching the portfolio…",
    opening: "Opening the record…",
    restarting: "The model failed mid-answer. Switching to a fallback model…",
    sources: "Sources",
    source: "Source {n}",
    close: "Close",
    steps: { one: "1 step", other: "{n} steps" },
    seconds: "{n} s",
    tokens: "{n} tokens",
    sourcesCount: { one: "1 source", other: "{n} sources" },
    fallback: "Fallback model",
    cached: "Cached",
    retry: "Try again",
    errors: {
      disconnected: "The connection dropped before the answer finished.",
      unreachable: "We couldn't reach the server. Try again in a moment.",
      minute: "Too many messages in the last minute. Try again in {n} seconds.",
      day: "Today's message limit is reached. Come back tomorrow, or download the CV.",
      conversation: "This conversation has reached its length limit. Start a new one.",
      unavailable: "No model can answer right now. Try again in a few minutes, or download the CV.",
      tooLong: "The message is too long. The limit is 1,000 characters.",
      internal: "Something went wrong on our side.",
    },
    newConversation: "New conversation",
    feedback: {
      up: "Helpful answer",
      down: "Not a helpful answer",
      thanks: "Thanks.",
      thanksMore: "Thanks. You can add details.",
      commentLabel: "What didn't work? (optional)",
      counter: "{n} / {max}",
      challenge: "This was a challenge attempt",
      challengeHint: "You're welcome to try to make the agent lie. Reports go through this button.",
      send: "Send report",
      cancel: "Cancel",
      sent: "Thanks for the report.",
      failed: "The feedback wasn't saved. Try again.",
      limited: "That's a lot of feedback for one day. Try again tomorrow.",
    },
  },
};

const dictionaries: Record<Locale, Dictionary> = { he, en };

export const getDictionary = (locale: Locale): Dictionary => dictionaries[locale];

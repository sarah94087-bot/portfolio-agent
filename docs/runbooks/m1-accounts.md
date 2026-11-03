# M1: חשבונות ומפתחות

רשימה לשרה. **את המפתחות לא שולחים בצ'אט ולא שומרים ב-repo.** בשלב הזה הם נכנסים רק לקובץ `.env` מקומי, שלא עולה ל-git. אחרי שה-repo יעלה ל-GitHub, הם יועברו גם ל-Vercel ול-GitHub Secrets.

**לפני שמתחילים:** מעתיקים את `.env.example` ל-`.env` בתיקיית הפרויקט, וממלאים בו כל ערך מיד כשמקבלים אותו.

| # | שירות | מה עושים | מה נכנס ל-`.env` |
|---|---|---|---|
| 1 | **GitHub** | אם אין חשבון, לפתוח. ה-repo ייפתח בהמשך, כ-**פרטי** עד M9 | — |
| 2 | **Google AI Studio, פרויקט פרודקשן** | ב-[aistudio.google.com](https://aistudio.google.com): Get API key, ואז Create API key in new project. לקרוא לפרויקט `sarah-agent-prod` | `GEMINI_API_KEY` |
| 3 | **Google AI Studio, פרויקט בדיקות** | אותו דבר, פרויקט חדש בשם `sarah-agent-evals` | `GEMINI_API_KEY_EVALS` |
| 4 | **Groq** | ב-[console.groq.com](https://console.groq.com): חשבון, ואז API Keys. שני מפתחות: `prod` ו-`evals` | `GROQ_API_KEY`, `GROQ_API_KEY_EVALS` |
| 5 | **Neon** | ב-[neon.tech](https://neon.tech): פרויקט חדש בשם `sarah-agent`, **אזור AWS Europe Central 1 (Frankfurt)**, Postgres 17. להעתיק את ה-connection string **עם pooling** | `DATABASE_URL` |
| 6 | **Neon, חיבור ישיר** | באותו מסך, לבטל את סימון Connection pooling ולהעתיק שוב | `DATABASE_URL_DIRECT` |
| 7 | **Langfuse** | ב-[cloud.langfuse.com](https://cloud.langfuse.com): **אזור EU**, פרויקט `sarah-agent`, ואז Settings → API Keys | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |
| 8 | **Resend** | ב-[resend.com](https://resend.com): להירשם **עם הכתובת שאליה יגיעו ההודעות**, ואז API Keys עם הרשאת Sending access | `RESEND_API_KEY`, `CONTACT_EMAIL` |
| 9 | **Vercel** | ב-[vercel.com](https://vercel.com): חשבון Hobby. להתחבר עם GitHub | — (בשלב S1) |

**בכל אחד מהשירותים: לא להוסיף אמצעי תשלום**, גם אם מוצע "ניסיון חינם" שדורש כרטיס.

## אחרי שהכול מוכן
1. מריצים את הבדיקה המקומית, שבודקת שכל המשתנים קיימים. היא לא מדפיסה את הערכים:
   ```bash
   python spikes/check_env.py
   ```
2. כותבים לי "החשבונות מוכנים", ואני מריץ את הניסויים S3, S4 ו-S6, שלא צריכים פריסה.
3. S1 ו-S2 צריכים פריסה ל-Vercel. נעשה אותם יחד, כשה-repo יעלה ל-GitHub.

## מה עוד צריך לבדוק ידנית (S5)
לכל שירות, בדף התמחור או בהגדרות החשבון, לרשום ב-`docs/experiments/m1-spikes.md`:
- המגבלות של התוכנית החינמית (בקשות לדקה וליום, טוקנים, אחסון).
- תקופת שמירת הנתונים.
- האם מותר להחזיק שני פרויקטים או שני מפתחות (Google, Groq).

# החלפת מפתחות

## מתי משתמשים
כשיש חשד שמפתח דלף (הופיע בלוג ציבורי, בצילום מסך, ב-commit), או בהחלפה תקופתית. **בחשד לדליפה מחליפים קודם ובודקים אחר כך.**

אם הדליפה גורמת לנזק עכשיו, למשל מכסה שנשרפת, מכבים קודם את הסוכן (`kill-switch.md`).

## איפה כל מפתח יושב
| מפתח | איפה יוצרים מחדש | איפה מעדכנים |
|---|---|---|
| `GROQ_API_KEY` (פרודקשן) | https://console.groq.com/keys | Vercel |
| `GROQ_API_KEY_EVALS` | https://console.groq.com/keys | GitHub Secrets |
| `DATABASE_URL`, `DATABASE_URL_DIRECT` | Neon: Roles, ואז Reset password, ב-https://console.neon.tech | `DATABASE_URL` ב-Vercel, `DATABASE_URL_DIRECT` ב-GitHub Secrets |
| `VERCEL_TOKEN` | https://vercel.com/account/tokens | GitHub Secrets |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | https://cloud.langfuse.com, בפרויקט: Settings, ואז API Keys | GitHub Secrets |
| `VISITOR_HMAC_SECRET` | ערך אקראי חדש (למטה) | Vercel |
| `CANARY_TOKEN` | ערך אקראי חדש (למטה) | Vercel |
| `PUBLICATION_TERMS` | לא מפתח, רשימת מונחים. מחליפים רק אם היא דלפה | GitHub Secrets, וגם Dependabot Secrets |

- **Vercel:** https://vercel.com/karuki/portfolio-agent/settings/environment-variables
- **GitHub Secrets:** https://github.com/sarah94087-bot/portfolio-agent/settings/secrets/actions
- **Dependabot Secrets:** https://github.com/sarah94087-bot/portfolio-agent/settings/secrets/dependabot
- **העותק המקומי:** הקובץ `.env` בתיקיית הפרויקט, שלא עולה ל-git.

**ערך אקראי חדש**, ל-`VISITOR_HMAC_SECRET` או `CANARY_TOKEN`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## צעדים
1. ליצור מפתח חדש בשירות (הטבלה למעלה). **לא למחוק עדיין את הישן**, אלא אם הוא דלף. אז מוחקים מיד, ומקבלים כמה דקות של תקלה.
2. לעדכן את הערך בכל מקום שמופיע בעמודה "איפה מעדכנים", ובקובץ `.env` המקומי.
3. אם המפתח עודכן ב-Vercel, להריץ פריסה, כי משתנה חדש נכנס לתוקף רק בפריסה חדשה:
   https://github.com/sarah94087-bot/portfolio-agent/actions/workflows/deploy.yml
   ללחוץ **Run workflow**, להשאיר `main`, וללחוץ שוב **Run workflow**.
4. אחרי שהפריסה עברה, למחוק את המפתח הישן בשירות.

**מה קורה כשמחליפים את `VISITOR_HMAC_SECRET`:** כל עוגיות המבקרים הקיימות מפסיקות להיות תקפות. מבקר שחוזר מקבל עוגייה חדשה, ולא רואה יותר את השיחות הקודמות שלו. הן נמחקות ממילא אחרי 30 יום.

## איך מוודאים שזה עבד
- **מפתח ב-Vercel:** ה-deploy עבר (בדיקת העשן בודקת את המסד), ו-https://portfolio-agent-rosy.vercel.app/api/health מחזיר `"db": {"ok": true}`. ל-`GROQ_API_KEY` צריך שאלה אחת באתר, שעולה טוקנים.
- **מפתח ב-GitHub Secrets:** הריצה הבאה של ה-workflow שמשתמש בו עוברת. `DATABASE_URL_DIRECT` ו-`VERCEL_TOKEN`: ‏deploy. מפתחות Langfuse: ‏`retention.yml`, אפשר להריץ אותו ידנית מכאן: https://github.com/sarah94087-bot/portfolio-agent/actions/workflows/retention.yml
- **המפתח הישן:** בשירות הוא מסומן כמחוק או מבוטל.

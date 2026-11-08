// E2: a streaming answer, citations and their sources, feedback, and US-12.4's delete.

import { ask, expect, HOLD, openChat, test } from "./support/fixtures";
import { answer, answerText, closing, CONVERSATION, ev, MESSAGE, meta, searchSteps, shortAnswer, TEXT, tokens } from "./support/recordings";

const he = TEXT.he;

test("US-2.1 a question shows progress at once, then the text as it arrives", async ({ page, api }) => {
  api.queue([HOLD, meta(), ev("step", { step_id: "s2", kind: "tool_call", status: "start", name: "search_portfolio", args: { query: "q" } }), HOLD,
    ev("token", { text: he.before }), HOLD, ...closing("he")]);
  await openChat(page);
  await ask(page, he.question);

  const message = page.getByRole("article");
  await expect(page.getByText(he.question, { exact: true })).toBeVisible();
  await expect(message.getByRole("status").first()).toHaveText("הסוכן חושב…");
  await api.release();
  await expect(message.getByRole("status").first()).toHaveText("מחפש בתיק הפרויקטים…");
  await api.release();
  await expect(message.locator(".text-body")).toContainText(he.before.trim());
  await expect(message.getByText("מקורות ·")).toHaveCount(0); // not until the end
  await api.release();
  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
});

test("US-2.1 frames and Hebrew letters split across network chunks arrive whole", async ({ page, api }) => {
  api.queue(answer(), { bytesPerWrite: 5 });
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("article")).toContainText(answerText("he"));
});

test("US-2.2 a citation opens its full passage and record name; Esc returns to it", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);
  await ask(page, he.question);

  const cite = page.getByRole("button", { name: "מקור 1", exact: true });
  await cite.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading")).toContainText(he.title);
  await expect(dialog).toContainText("שרה בנתה מערכת תרגום עם");
  await expect(dialog).toContainText("המערכת רצה ב-pgvector."); // the whole passage
  await expect(dialog.locator("strong")).toHaveText("בדיקה אנושית"); // Markdown, not asterisks
  await expect(cite).toHaveAttribute("aria-expanded", "true");

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(cite).toBeFocused();
});

test("US-2.2 the source closes with its button and with a click outside", async ({ page, api }) => {
  api.queue(answer());
  await openChat(page);
  await ask(page, he.question);
  const cite = page.getByRole("button", { name: "מקור 2", exact: true });
  await cite.click();
  await expect(page.getByRole("dialog")).toContainText(he.titleTwo);
  await page.getByRole("dialog").getByRole("button", { name: "סגירה" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(cite).toBeFocused();

  await cite.click();
  await page.mouse.click(5, 300);
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("US-2.2 citations wait for their sources, and the list of sources opens under the answer", async ({ page, api }) => {
  api.queue([meta(), ...searchSteps("he"), ...tokens("he"), HOLD, ...closing("he")]);
  await openChat(page);
  await ask(page, he.question);
  await api.held();
  await expect(page.locator("[data-cite='1']")).toBeDisabled();
  await api.release();
  await expect(page.locator("[data-cite='1']")).toBeEnabled();

  await page.getByRole("button", { name: /^מקורות/ }).click();
  const list = page.getByRole("article").getByRole("listitem");
  await expect(list).toHaveCount(2);
  await expect(list.first()).toContainText(he.title);
});

test("US-2.2 a removed citation is marked on the answer", async ({ page, api }) => {
  api.queue(answer("he", { dropped: 1 }));
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("article").getByText("ציטוט הוסר")).toBeVisible();
});

test("US-2.5 a follow-up goes out in the same conversation, with a new key", async ({ page, api }) => {
  api.queue(answer());
  api.queue(shortAnswer("תשובת המשך"));
  await openChat(page);
  await ask(page, he.question);
  await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
  await ask(page, "ומה היה הכי קשה שם?");
  await expect(page.getByRole("article").nth(1).locator(".text-body")).toContainText("תשובת המשך");

  expect(api.chats[0].conversation_id).toBeUndefined();
  expect(api.chats[0].lang).toBe("he");
  expect(api.chats[1].conversation_id).toBe(CONVERSATION);
  expect(api.chats[1].idempotency_key).not.toBe(api.chats[0].idempotency_key);
  await expect(page.getByRole("article")).toHaveCount(2);
});

test("while an answer streams the visitor can type, but not send", async ({ page, api }) => {
  api.queue([meta(), HOLD, ...tokens("he"), ...closing("he")]);
  await openChat(page);
  await ask(page, he.question);
  await api.held();
  const field = page.locator("textarea");
  await field.fill("שאלה הבאה");
  await field.press("Enter");
  await expect(page.getByRole("button", { name: "שליחה" })).toBeDisabled();
  await expect(field).toHaveValue("שאלה הבאה");
  expect(api.chats).toHaveLength(1);
  await api.release();
  await expect(page.getByRole("button", { name: "שליחה" })).toBeEnabled();
});

test("US-10.4 a question over 1,000 characters cannot be sent, and the field says why", async ({ page, api }) => {
  await openChat(page);
  const field = page.locator("textarea");
  await field.fill("א".repeat(1001));
  await expect(page.getByRole("button", { name: "שליחה" })).toBeDisabled();
  await expect(field).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("ארוך מדי לשליחה")).toBeAttached();
  await field.press("Enter");
  expect(api.chats).toEqual([]);
});

test.describe("US-2.7 feedback", () => {
  test.beforeEach(async ({ page, api }) => {
    api.queue(answer());
    await openChat(page);
    await ask(page, he.question);
    await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
  });

  test("thumbs up is saved with the answer's id", async ({ page, api }) => {
    const up = page.getByRole("button", { name: "תשובה מועילה" });
    await up.click();
    await expect(up).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("תודה.", { exact: true })).toBeVisible();
    expect(api.feedback).toEqual([{ message_id: MESSAGE, rating: "up" }]);
  });

  test("thumbs down opens an optional comment and a challenge mark", async ({ page, api }) => {
    const down = page.getByRole("button", { name: "תשובה לא מועילה" });
    await down.click();
    const comment = page.getByRole("textbox", { name: "מה לא עבד? (אופציונלי)" });
    await expect(comment).toBeFocused();
    await comment.fill("חסר מקור");
    await page.getByRole("checkbox", { name: "זה ניסיון באתגר" }).check();
    await page.getByRole("button", { name: "שליחת דיווח" }).click();
    await expect(page.getByText("תודה על הדיווח.")).toBeVisible();
    await expect(down).toBeFocused();
    expect(api.feedback).toEqual([
      { message_id: MESSAGE, rating: "down" },
      { message_id: MESSAGE, rating: "down", comment: "חסר מקור", challenge: true },
    ]);
  });

  test("a comment over the limit cannot be sent", async ({ page }) => {
    await page.getByRole("button", { name: "תשובה לא מועילה" }).click();
    await page.getByRole("textbox", { name: "מה לא עבד? (אופציונלי)" }).fill("א".repeat(301));
    await expect(page.getByRole("button", { name: "שליחת דיווח" })).toBeDisabled();
  });

  test("a failed save puts the button back and says so", async ({ page, api }) => {
    api.feedbackStatus = 500;
    const up = page.getByRole("button", { name: "תשובה מועילה" });
    await up.click();
    await expect(page.getByText("המשוב לא נשמר. אפשר לנסות שוב.")).toBeVisible();
    await expect(up).toHaveAttribute("aria-pressed", "false");
  });

  test("too much feedback gets its own message", async ({ page, api }) => {
    api.feedbackStatus = 429;
    await page.getByRole("button", { name: "תשובה מועילה" }).click();
    await expect(page.getByText("נשלח היום הרבה משוב. אפשר לנסות שוב מחר.")).toBeVisible();
  });
});

test.describe("US-12.4 deleting the conversation", () => {
  test.beforeEach(async ({ page, api }) => {
    api.queue(answer());
    await openChat(page);
    await ask(page, he.question);
    await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
  });

  const opener = "מחיקת השיחה";

  test("asks first, with the focus on Cancel; Esc closes and returns", async ({ page, api }) => {
    await page.getByRole("button", { name: opener }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toContainText("למחוק את השיחה?");
    await expect(dialog.getByRole("button", { name: "ביטול" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: opener })).toBeFocused();
    expect(api.deleted).toEqual([]);
  });

  test("deleting clears the screen, says so and returns to the question field", async ({ page, api }) => {
    await page.getByRole("button", { name: opener }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "מחיקה" }).click();
    await expect(page.getByRole("status").filter({ hasText: "השיחה נמחקה" })).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("סוכן AI");
    await expect(page.locator("textarea")).toBeFocused();
    expect(api.deleted).toEqual([CONVERSATION]);
  });

  test("a failed delete stays open and says so", async ({ page, api }) => {
    api.deleteStatus = 500;
    await page.getByRole("button", { name: opener }).click();
    const dialog = page.getByRole("alertdialog");
    await dialog.getByRole("button", { name: "מחיקה" }).click();
    await expect(dialog.getByRole("status")).toHaveText("השיחה לא נמחקה. אפשר לנסות שוב.");
    await expect(page.getByRole("article")).toHaveCount(1);
  });

  test("a new conversation starts without the old id", async ({ page, api }) => {
    await page.getByRole("button", { name: "שיחה חדשה" }).click();
    await expect(page.getByRole("article")).toHaveCount(0);
    api.queue(answer());
    await ask(page, he.question);
    await expect(page.getByRole("button", { name: "תשובה מועילה" })).toBeVisible();
    expect(api.chats[1].conversation_id).toBeUndefined();
    expect(api.deleted).toEqual([]);
  });
});

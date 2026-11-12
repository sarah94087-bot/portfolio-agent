// A screenshot of a posting (ADR-0022): attached from the job field, sent as an image and no
// text, and shown in the conversation. The server's side is recorded, so no model is reached.

import { expect, openChat, test } from "./support/fixtures";
import { ev, meta } from "./support/recordings";

// One transparent pixel: a real PNG, so the browser can open and redraw it.
const PIXEL = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

async function openJobField(page: import("@playwright/test").Page) {
  await openChat(page);
  await page.getByRole("button", { name: "הדבקת משרה" }).click();
}

test("a picture chosen from the button replaces the text field, and can be removed", async ({ page, api }) => {
  void api;
  await openJobField(page);
  await page.locator('input[type="file"]').setInputFiles({ name: "job.png", mimeType: "image/png", buffer: PIXEL });
  await expect(page.getByRole("img", { name: "צילום המסך של המשרה שצורף" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "תיאור המשרה" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "בדיקת התאמה" })).toBeEnabled();

  await page.getByRole("button", { name: "הסרת התמונה" }).click();
  await expect(page.getByRole("textbox", { name: "תיאור המשרה" })).toBeVisible();
  await expect(page.getByRole("button", { name: "בדיקת התאמה" })).toBeDisabled();
});

test("the picture goes to the server as an image and no message, with its own first stage", async ({ page, api }) => {
  api.queue([
    meta(),
    ev("step", { step_id: "j1", kind: "llm", status: "start", name: "job.read" }),
    ev("token", { text: "לא נמצאה משרה בתמונה. אפשר לצלם שוב באופן ברור יותר, או להדביק את הטקסט." }),
    ev("done"),
  ]);
  await openJobField(page);
  await page.locator('input[type="file"]').setInputFiles({ name: "job.png", mimeType: "image/png", buffer: PIXEL });
  await page.getByRole("button", { name: "בדיקת התאמה" }).click();

  await expect(page.getByText("צילום מסך של משרה")).toBeVisible();
  await expect(page.getByRole("article").getByRole("paragraph").filter({ hasText: "לא נמצאה משרה בתמונה" })).toBeVisible();
  expect(api.chats).toHaveLength(1);
  const sent = api.chats[0];
  expect(sent.mode).toBe("job");
  expect(sent.image).toMatch(/^data:image\/(webp|png|jpeg);base64,/);
  expect(sent).not.toHaveProperty("message");
});

test("a file that is not a supported image says so and sends nothing", async ({ page, api }) => {
  await openJobField(page);
  await page.locator('input[type="file"]').setInputFiles({ name: "job.gif", mimeType: "image/gif", buffer: Buffer.from("GIF89a") });
  await expect(page.getByText("אפשר לצרף PNG, JPEG או WebP.")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "תיאור המשרה" })).toBeVisible();
  expect(api.chats).toHaveLength(0);
});

test("a picture pasted into the question field opens the job field with it", async ({ page, api }) => {
  void api;
  await openChat(page);
  await page.getByRole("textbox").first().focus();
  await page.evaluate(async (b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const data = new DataTransfer();
    data.items.add(new File([bytes], "shot.png", { type: "image/png" }));
    document.activeElement!.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
  }, PIXEL.toString("base64"));
  await expect(page.getByRole("img", { name: "צילום המסך של המשרה שצורף" })).toBeVisible();
});

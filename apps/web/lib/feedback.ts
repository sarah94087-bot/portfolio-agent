// POST /api/feedback (US-2.7; backend/portfolio_agent/feedback.py). One rating per answer, and
// the last one counts: 👎 is sent at once, and its comment, if any, in a second request.

export const MAX_COMMENT = 300; // the server checks it too, in code points as here

export type Rating = "up" | "down";
export type FeedbackBody = { message_id: string; rating: Rating; comment?: string; challenge?: boolean };
export type FeedbackResult = "saved" | "limited" | "failed";

/** Characters as the server counts them: code points, so an emoji is one. */
export const chars = (s: string) => [...s].length;

/** Never throws: a failure is a result the screen shows. */
export async function sendFeedback(body: FeedbackBody, post: typeof fetch = fetch): Promise<FeedbackResult> {
  try {
    const res = await post("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "same-origin",
    });
    if (res.status === 204) return "saved";
    return res.status === 429 ? "limited" : "failed";
  } catch {
    return "failed";
  }
}

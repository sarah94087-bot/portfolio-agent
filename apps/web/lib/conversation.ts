// DELETE /api/conversations/{id} (US-12.4; backend/portfolio_agent/chat.py).

export type DeleteResult = "deleted" | "failed";

/** 404 counts as deleted: the conversation is gone either way (expired, or deleted from
 * another tab). Never throws: a failure is a result the dialog shows. */
export async function deleteConversation(id: string, send: typeof fetch = fetch): Promise<DeleteResult> {
  try {
    const res = await send(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "same-origin",
    });
    return res.status === 204 || res.status === 404 ? "deleted" : "failed";
  } catch {
    return "failed";
  }
}

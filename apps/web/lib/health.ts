// The kill switch (docs/10, section 7): AGENT_ENABLED=false on the server turns the agent off,
// and /api/health says so. The page then shows S7's page state instead of the composer.

/** True only when the health answer says the agent is off. Anything else (no answer, an error,
 *  a body without the field) leaves the page as it is: the chat's own errors cover those. */
export function agentPaused(body: unknown): boolean {
  return typeof body === "object" && body !== null && (body as { agent_enabled?: unknown }).agent_enabled === false;
}

/** Asks the server whether the agent is off. `warm` also wakes the function, Neon and the
 *  embedding model (spike S2), which the page wants on its first load. Never throws. */
export async function checkPaused(warm: boolean, get: typeof fetch = fetch): Promise<boolean> {
  try {
    const r = await get(`/api/health${warm ? "?warm=1" : ""}`, { cache: "no-store" });
    return r.ok ? agentPaused(await r.json()) : false;
  } catch {
    return false;
  }
}

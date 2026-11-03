// Client for the SSE protocol, version 1 (docs/05-architecture.md, section 5).
// Uses fetch instead of EventSource because /api/chat is a POST.

export type SseEvent = { event: string; data: Record<string, unknown> & { v: number } };

/** Splits a text stream into SSE frames. Frames may arrive split across chunks. */
export function createFrameParser(onEvent: (e: SseEvent) => void) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk.replace(/\r\n/g, "\n");
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
      }
      if (dataLines.length === 0) continue;
      onEvent({ event, data: JSON.parse(dataLines.join("\n")) });
    }
  };
}

export async function streamEvents(
  url: string,
  init: RequestInit,
  onEvent: (e: SseEvent) => void,
): Promise<void> {
  const response = await fetch(url, init);
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  const feed = createFrameParser(onEvent);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(value);
  }
}

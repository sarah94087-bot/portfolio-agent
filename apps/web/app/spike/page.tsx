"use client";

import { useState } from "react";

import { streamEvents, type SseEvent } from "@/lib/sse";

type Row = { event: SseEvent; atMs: number };

// Spike S1 (docs/11-roadmap.md, M1): do events arrive one by one, or buffered at the end?
// If the first token arrives together with "done", the platform is buffering the stream.
export default function SpikePage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    setRows([]);
    setError(null);
    setRunning(true);
    const started = performance.now();
    try {
      await streamEvents("/api/spike/stream", { cache: "no-store" }, (event) =>
        setRows((prev) => [...prev, { event, atMs: Math.round(performance.now() - started) }]),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const firstToken = rows.find((r) => r.event.event === "token");
  const done = rows.find((r) => r.event.event === "done");

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-12">
      <h1 className="text-2xl font-semibold">ניסוי S1: הזרמה</h1>
      <button
        type="button"
        onClick={run}
        disabled={running}
        className="mt-6 rounded border px-4 py-2 disabled:opacity-50"
      >
        {running ? "מריץ..." : "הרצה"}
      </button>
      {error && <p className="mt-4 text-red-700">שגיאה: {error}</p>}
      {firstToken && done && (
        <p className="mt-4 tabular-nums">
          טוקן ראשון אחרי {firstToken.atMs}ms, סיום אחרי {done.atMs}ms.{" "}
          {done.atMs - firstToken.atMs < 100 ? "נראה שהזרם נאגר (buffered)." : "הזרם מגיע בהדרגה."}
        </p>
      )}
      <ol className="mt-6 space-y-1 font-mono text-sm" dir="ltr">
        {rows.map((r, i) => (
          <li key={i} className="tabular-nums">
            {String(r.atMs).padStart(5, " ")}ms {r.event.event} {JSON.stringify(r.event.data)}
          </li>
        ))}
      </ol>
    </main>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { CompassIcon, JobIcon, LayersIcon, StarIcon } from "@/components/ui/icons";
import { newTurn, retry as retryTurn, run, type Turn } from "@/lib/chat";
import { AgentMessage, type ChatStrings } from "./AgentMessage";
import { Composer, type ComposerMode, type ComposerStrings } from "./Composer";
import { ConversationActions } from "./ConversationActions";
import { TracePanel } from "./TracePanel";

// One tone per starter, in the design's order: ink, stone, salmon, accent (the job check).
const starterStyles = [
  { card: "bg-tint-ink text-on-ink", plate: "bg-badge-plate text-on-rose", Icon: StarIcon },
  { card: "bg-tint-stone text-on-stone", plate: "bg-badge-plate text-on-stone", Icon: LayersIcon },
  { card: "bg-tint-salmon text-on-salmon", plate: "bg-badge-plate text-on-salmon", Icon: CompassIcon },
  { card: "bg-accent text-on-accent", plate: "bg-badge-plate-on-accent text-on-accent", Icon: JobIcon },
];

type Props = {
  lang: string;
  intro: React.ReactNode; // S1's heading, rendered on the server
  starters: string[];
  startersLabel: string;
  composer: ComposerStrings;
  chat: ChatStrings;
  agentName: string;
  privacy: React.ReactNode;
};

// S1 until the first question, then S2 (boards Main, A-S2, S2-States, S2-Mobile). The turns
// live here; lib/chat.ts turns each answer's events into what AgentMessage shows.
export function Chat({ lang, intro, starters, startersLabel, composer, chat, agentName, privacy }: Props) {
  const [mode, setMode] = useState<ComposerMode>("question");
  const [value, setValue] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const conversationId = useRef<string | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastQuestion = useRef<HTMLDivElement>(null);
  const pageLang = lang === "he" ? "he" : "en";
  const busy = turns.some((t) => t.status === "sending" || t.status === "streaming");

  // Spike S2: a cold start takes about 9 s, so the page wakes the function, Neon and the
  // embedding model while the visitor reads and types. Nothing depends on the answer.
  useEffect(() => {
    fetch("/api/health?warm=1", { cache: "no-store" }).catch(() => {});
  }, []);

  // S3: one answer's trace at a time. Focus goes back to what opened it.
  const [trace, setTrace] = useState<{ key: string; chunkId?: string } | null>(null);
  const traceFrom = useRef<HTMLElement | null>(null);
  const traced = trace && turns.find((t) => t.key === trace.key);
  const closeTrace = useCallback(() => {
    setTrace(null);
    traceFrom.current?.focus();
  }, []);
  function openTrace(turn: Turn, from: HTMLElement, chunkId?: string) {
    if (trace?.key === turn.key && !chunkId) return closeTrace();
    traceFrom.current = from;
    setTrace({ key: turn.key, chunkId });
  }
  // From 1100px the panel pushes the conversation aside instead of covering it (globals.css).
  useEffect(() => {
    const root = document.documentElement;
    if (traced) root.dataset.trace = "open";
    else delete root.dataset.trace;
    return () => {
      delete root.dataset.trace;
    };
  }, [traced]);

  function update(next: Turn) {
    if (next.conversationId) conversationId.current = next.conversationId;
    setTurns((ts) => ts.map((t) => (t.key === next.key ? next : t)));
  }

  function send(text: string) {
    const turn = newTurn(text);
    setTurns((ts) => [...ts, turn]);
    setValue("");
    setMode("question");
    requestAnimationFrame(() => lastQuestion.current?.scrollIntoView({ block: "start", behavior: "smooth" }));
    void run(turn, update, { conversationId: conversationId.current, lang: pageLang });
  }

  function retry(turn: Turn) {
    void retryTurn(turn, update, { conversationId: conversationId.current, lang: pageLang });
  }

  // Back to the welcome screen. "New conversation" leaves the old one on the server (it expires
  // in 30 days); after a delete it is already gone, and a toast says so (board S7-S8).
  const [toast, setToast] = useState("");
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(id);
  }, [toast]);
  function startOver(message = "") {
    setTurns([]);
    conversationId.current = undefined;
    setTrace(null);
    setValue("");
    setMode("question");
    setToast(message);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function pick(index: number) {
    if (index === starters.length - 1) {
      setMode("job");
      setValue("");
    } else {
      setMode("question");
      setValue(starters[index]);
    }
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  const started = turns.length > 0;
  const composerStrings = started ? { ...composer, questionPlaceholder: chat.followUpPlaceholder } : composer;

  return (
    <>
      {!started ? (
        <>
          {intro}
          <ul aria-label={startersLabel} className="mt-5 grid grid-cols-1 gap-2 md:mt-7 md:grid-cols-2 md:gap-3">
            {starters.map((text, i) => {
              const s = starterStyles[i];
              return (
                <li key={text} className="flex">
                  <button
                    type="button"
                    onClick={() => pick(i)}
                    className={`flex min-h-14 w-full items-center gap-3 rounded-[12px] px-3.5 py-3 text-start text-[16px] font-bold leading-[1.35] transition-[filter] duration-(--dur-fast) hover:brightness-95 md:flex-col md:items-start md:gap-3.5 md:rounded-lg md:px-[18px] md:pb-[18px] md:pt-4 md:text-[19px] md:leading-[1.4] dark:hover:brightness-110 ${s.card}`}
                  >
                    <span className={`flex size-8 flex-none items-center justify-center rounded-[9px] md:size-[34px] md:rounded-md ${s.plate}`}>
                      <s.Icon size={18} />
                    </span>
                    {text}
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <div className="flex flex-col gap-7 pb-6 md:gap-[34px]">
          {turns.map((turn, i) => (
            <div key={turn.key} className="flex flex-col gap-3.5 md:gap-[34px]">
              <div
                ref={i === turns.length - 1 ? lastQuestion : undefined}
                dir="auto"
                className="max-w-[85%] scroll-mt-20 self-start whitespace-pre-wrap rounded-[16px] bg-tint-ink px-3.5 py-2 text-[16px] font-semibold leading-[1.6] text-on-ink md:px-[18px] md:py-[11px] md:text-[18px]"
              >
                {turn.question}
              </div>
              <AgentMessage
                turn={turn}
                lang={lang}
                t={chat}
                agentName={agentName}
                onRetry={() => retry(turn)}
                traceOpen={trace?.key === turn.key}
                onTrace={(from, chunkId) => openTrace(turn, from, chunkId)}
              />
            </div>
          ))}
        </div>
      )}

      {traced && (
        <TracePanel
          turn={traced}
          index={turns.indexOf(traced) + 1}
          lang={lang}
          t={chat}
          highlight={trace?.chunkId}
          onClose={closeTrace}
        />
      )}

      {/* The composer sticks to the bottom once the conversation starts, and on mobile from the
          start, as in the design; on the desktop welcome screen it follows the cards. */}
      <div
        className={`sticky bottom-0 -mx-4 mt-auto bg-surface px-4 pb-[max(18px,env(safe-area-inset-bottom))] pt-3 ${started ? "md:pb-[22px]" : "md:static md:mx-0 md:mt-6 md:bg-transparent md:p-0"}`}
      >
        {started && (
          <ConversationActions
            t={chat}
            conversationId={turns.findLast((x) => x.conversationId)?.conversationId}
            busy={busy}
            onNew={() => startOver()}
            onDeleted={() => startOver(chat.conversation.deleted)}
          />
        )}
        <Composer
          ref={inputRef}
          lang={lang}
          t={composerStrings}
          mode={mode}
          value={value}
          busy={busy}
          compact={started}
          onModeChange={(m) => {
            setMode(m);
            requestAnimationFrame(() => inputRef.current?.focus());
          }}
          onChange={setValue}
          onSubmit={(text) => send(text)}
        />
        <p className="mt-2.5 text-[12.5px] leading-[1.5] text-text-muted md:mt-4 md:text-small">{privacy}</p>
      </div>

      {/* Always in the page, so screen readers hear the toast when its text arrives. */}
      <div role="status" className="pointer-events-none fixed inset-x-0 top-[72px] z-50 flex justify-center px-4 md:top-[88px]">
        {toast && (
          <p className="rounded-[10px] bg-text px-3.5 py-2.5 text-[14px] font-semibold text-surface shadow-pop">{toast}</p>
        )}
      </div>
    </>
  );
}

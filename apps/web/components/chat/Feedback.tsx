"use client";

import { useEffect, useId, useRef, useState } from "react";

import type { Dictionary } from "@/app/[lang]/dictionaries";
import { Button } from "@/components/ui/Button";
import { ThumbIcon } from "@/components/ui/icons";
import { chars, MAX_COMMENT, sendFeedback, type FeedbackResult, type Rating } from "@/lib/feedback";

export type FeedbackStrings = Dictionary["chat"]["feedback"];

const fill = (s: string, vals: Record<string, string>) =>
  s.replace(/\{(\w+)\}/g, (m, k: string) => vals[k] ?? m);

// 👍 / 👎 under a finished answer (US-2.7; boards A-S2 and S2-States e). The rating is sent as
// soon as it is pressed; 👎 then opens an optional comment, sent as a second request that
// replaces the first. A failed request puts the buttons back as they were and says so.
export function Feedback({ messageId, lang, t }: { messageId: string; lang: string; t: FeedbackStrings }) {
  const [rating, setRating] = useState<Rating | null>(null);
  const [panel, setPanel] = useState(false);
  const [comment, setComment] = useState("");
  const [challenge, setChallenge] = useState(false);
  const [note, setNote] = useState<string>("");
  const [sending, setSending] = useState(false);
  const downRef = useRef<HTMLButtonElement>(null);
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const ids = { field: useId(), counter: useId(), hint: useId() };

  const length = chars(comment);
  const over = length > MAX_COMMENT;

  function failure(result: FeedbackResult) {
    return result === "limited" ? t.limited : t.failed;
  }

  async function rate(next: Rating) {
    if (sending) return;
    if (rating === next) {
      if (next === "down") openPanel(); // a pressed 👎 brings the comment back
      return;
    }
    const before = rating;
    setRating(next);
    setSending(true);
    const result = await sendFeedback({ message_id: messageId, rating: next });
    setSending(false);
    if (result !== "saved") {
      setRating(before);
      setNote(failure(result));
      return;
    }
    if (next === "down") {
      setNote(t.thanksMore);
      openPanel();
    } else {
      setNote(t.thanks);
      setPanel(false);
    }
  }

  function openPanel() {
    setPanel(true);
  }

  // After the rating's request the field may not exist yet on the next frame, so focus waits for it.
  useEffect(() => {
    if (panel) fieldRef.current?.focus();
  }, [panel]);

  function closePanel() {
    setPanel(false);
    requestAnimationFrame(() => downRef.current?.focus());
  }

  async function report(e: React.FormEvent) {
    e.preventDefault();
    if (sending || over) return;
    setSending(true);
    const result = await sendFeedback({ message_id: messageId, rating: "down", comment: comment.trim(), challenge });
    setSending(false);
    if (result !== "saved") {
      setNote(failure(result));
      return;
    }
    setNote(t.sent);
    closePanel();
  }

  const thumb = (r: Rating) =>
    `flex size-9 items-center justify-center rounded-full text-text-muted transition-colors duration-(--dur-fast) hover:bg-surface-sunken ${
      rating === r ? "border-[1.5px] border-text bg-surface-sunken text-text" : "border border-border"
    }`;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={rating === "up"} aria-label={t.up} disabled={sending}
          onClick={() => rate("up")} className={thumb("up")}>
          <ThumbIcon />
        </button>
        <button ref={downRef} type="button" aria-pressed={rating === "down"} aria-label={t.down} disabled={sending}
          aria-expanded={rating === "down" ? panel : undefined} onClick={() => rate("down")} className={thumb("down")}>
          <ThumbIcon className="rotate-180" />
        </button>
        <span role="status" className="text-[14px] text-text-muted">{note}</span>
      </div>

      {panel && (
        <form onSubmit={report} onKeyDown={(e) => e.key === "Escape" && closePanel()}
          className="flex flex-col gap-2.5 rounded-[12px] border border-border bg-surface-raised p-3.5 md:max-w-[480px]">
          <label htmlFor={ids.field} className="text-[14px] font-bold">{t.commentLabel}</label>
          <textarea
            ref={fieldRef}
            id={ids.field}
            rows={3}
            dir="auto"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            aria-describedby={ids.counter}
            aria-invalid={over || undefined}
            className="resize-none rounded-[8px] border border-border-input bg-surface px-3 py-2 text-[15px] text-text"
          />
          <div id={ids.counter} className={`mono text-end text-[12px] ${over ? "font-bold text-danger" : "text-text-muted"}`}>
            {/* "46 / 300" reads left to right in both languages, as on the board */}
            <span dir="ltr">{fill(t.counter, { n: length.toLocaleString(lang), max: MAX_COMMENT.toLocaleString(lang) })}</span>
          </div>
          <label className="flex items-center gap-2.5 text-[14.5px]">
            <input type="checkbox" checked={challenge} onChange={(e) => setChallenge(e.target.checked)}
              aria-describedby={ids.hint} className="size-5 accent-accent" />
            {t.challenge}
          </label>
          <p id={ids.hint} className="m-0 text-[12.5px] leading-[1.55] text-text-muted">{t.challengeHint}</p>
          <div className="flex gap-2.5">
            <Button type="submit" disabled={sending || over}>{t.send}</Button>
            <Button variant="ghost" onClick={closePanel}>{t.cancel}</Button>
          </div>
        </form>
      )}
    </div>
  );
}

"use client";

import { useRef, useState } from "react";

import type { Dictionary } from "@/app/[lang]/dictionaries";
import { buttonClass } from "@/components/ui/Button";
import { PlusIcon, TrashIcon } from "@/components/ui/icons";
import { deleteConversation } from "@/lib/conversation";

type Props = {
  t: Dictionary["chat"];
  conversationId?: string; // none when no answer started: nothing is saved to delete
  busy: boolean; // an answer is streaming
  onNew: () => void;
  onDeleted: () => void;
};

// "New conversation" and "Delete conversation" above the composer, once the conversation has
// started. Deleting asks first, in the S7-S8 dialog: destructive but not scary, so it is the
// black danger tone, not the brand red, and Cancel has the focus. A native modal <dialog>
// keeps the focus inside and closes on Esc.
export function ConversationActions({ t, conversationId, busy, onNew, onDeleted }: Props) {
  const c = t.conversation;
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const [deleting, setDeleting] = useState(false);
  const [failed, setFailed] = useState(false);

  function ask() {
    setFailed(false);
    dialog.current?.showModal();
    cancel.current?.focus(); // React does not render autofocus, so the safe choice is focused here
  }

  async function confirm() {
    if (!conversationId) {
      dialog.current?.close();
      return onDeleted();
    }
    setDeleting(true);
    const result = await deleteConversation(conversationId);
    setDeleting(false);
    if (result === "failed") return setFailed(true);
    dialog.current?.close();
    onDeleted();
  }

  const small = "gap-1.5 text-[13.5px] px-2.5 py-1";

  return (
    <div role="group" aria-label={c.actions} className="mb-2.5 flex items-center justify-between gap-2">
      <button type="button" onClick={onNew} disabled={busy} className={buttonClass("ghost", small)}>
        <PlusIcon />
        {t.newConversation}
      </button>
      <button ref={opener} type="button" onClick={ask} disabled={busy} className={buttonClass("ghost", small)}>
        <TrashIcon />
        {c.delete}
      </button>

      <dialog
        ref={dialog}
        role="alertdialog"
        aria-labelledby="delete-title"
        aria-describedby="delete-text"
        onClose={() => opener.current?.focus()}
        className="m-auto w-[min(440px,calc(100%-32px))] rounded-[16px] border-[1.5px] border-border-strong bg-surface-raised p-6 text-text shadow-pop backdrop:bg-black/50"
      >
        <h2 id="delete-title" className="mb-3 text-[20px] font-extrabold">{c.confirmTitle}</h2>
        <p id="delete-text" className="mb-3 text-[15px] leading-[1.65] text-text-muted">{c.confirmText}</p>
        <p role="status" className="mb-3 text-[14px] font-semibold empty:hidden">{failed ? c.failed : ""}</p>
        <div className="flex gap-2.5">
          <button type="button" onClick={confirm} disabled={deleting}
            className="inline-flex min-h-[42px] items-center gap-2 rounded-[10px] bg-danger px-4 text-[14.5px] font-bold text-surface hover:brightness-90 disabled:opacity-60">
            {deleting ? c.deleting : c.confirm}
          </button>
          <button ref={cancel} type="button" onClick={() => dialog.current?.close()}
            className="inline-flex min-h-[42px] items-center rounded-[10px] border-[1.5px] border-border-input px-4 text-[14.5px] font-bold">
            {c.cancel}
          </button>
        </div>
      </dialog>
    </div>
  );
}

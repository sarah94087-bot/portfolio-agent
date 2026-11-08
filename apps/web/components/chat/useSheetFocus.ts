"use client";

import { useEffect } from "react";

// Below 1100px the trace, and on a phone the source too, cover the conversation. Tab stays in
// them, or the focus would go to a control hidden behind the sheet (WCAG 2.4.11). On a wide
// screen they sit beside the conversation, and Tab moves on as usual. Esc closes them either way.
// Works from the outside on purpose, by role and position, so the sheets need no code for it.

const COVERS = "(max-width: 68.74rem)"; // the panel's breakpoint in TracePanel, globals.css
const STOPS = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex="0"]';

export function useSheetFocus() {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Tab" || !matchMedia(COVERS).matches) return;
      // A source on a wider screen is an `absolute` popover: only the fixed ones are sheets.
      const sheet = [...document.querySelectorAll<HTMLElement>('[role="dialog"]')]
        .find((d) => getComputedStyle(d).position === "fixed");
      if (!sheet) return;
      const stops = [...sheet.querySelectorAll<HTMLElement>(STOPS)].filter((el) => el.offsetParent !== null);
      if (stops.length === 0) return;
      const at = stops.indexOf(document.activeElement as HTMLElement);
      const last = stops.length - 1;
      // -1 is the sheet itself, which takes the focus when it opens.
      if (e.shiftKey ? at <= 0 : at === last || at === -1) {
        e.preventDefault();
        stops[e.shiftKey ? last : 0].focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}

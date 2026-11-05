"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const options = [
  { lang: "he", label: "עב", name: "עברית" },
  { lang: "en", label: "EN", name: "English" },
] as const;

// Links, not buttons: each language is its own URL, so it can be shared and indexed.
export function LangToggle({ current, label }: { current: string; label: string }) {
  const pathname = usePathname();
  const rest = pathname.replace(/^\/(he|en)(?=\/|$)/, "");

  return (
    <nav aria-label={label} className="flex overflow-hidden rounded-[8px] border border-border">
      {options.map((o) => {
        const active = o.lang === current;
        return (
          <Link
            key={o.lang}
            href={`/${o.lang}${rest}`}
            hrefLang={o.lang}
            lang={o.lang}
            aria-label={o.name}
            aria-current={active ? "page" : undefined}
            className={`flex min-h-9 min-w-10 items-center justify-center px-3 text-[14px] font-bold ${
              active ? "bg-tint-ink text-on-ink" : "text-text hover:bg-surface-sunken"
            }`}
          >
            {o.label}
          </Link>
        );
      })}
    </nav>
  );
}

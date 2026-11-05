import Link from "next/link";

import type { Dictionary, Locale } from "@/app/[lang]/dictionaries";
import { buttonClass } from "./Button";
import { DownloadIcon } from "./icons";
import { LangToggle } from "./LangToggle";
import { Tag } from "./Tag";

// The 2×2 mark next to the name. Decorative.
function Mark() {
  return (
    <span aria-hidden="true" className="grid grid-cols-2 gap-0.5">
      <i className="size-2 rounded-[2px] bg-mark-1 md:size-[9px]" />
      <i className="size-2 rounded-[2px] bg-mark-2 md:size-[9px]" />
      <i className="size-2 rounded-[2px] bg-mark-3 md:size-[9px]" />
      <i className="size-2 rounded-[2px] bg-mark-4 md:size-[9px]" />
    </span>
  );
}

export function Header({ lang, t }: { lang: Locale; t: Dictionary["header"] }) {
  // These routes arrive in M5 (docs/11-roadmap.md); the links are in place so the header is final.
  const links = [
    { href: `/${lang}/how-it-works`, label: t.howItWorks },
    { href: `/${lang}/quality`, label: t.quality },
  ];
  const cvHref = `/cv/sarah-halevi-${lang}.pdf`;

  return (
    <header className="flex h-14 flex-none items-center gap-2 border-b-[3px] border-accent px-4 md:h-[68px] md:gap-4 md:px-10">
      <Link href={`/${lang}`} className="flex items-center gap-2 rounded-sm md:gap-3">
        <Mark />
        <span className="whitespace-nowrap text-[16px] font-extrabold md:text-[18px]">{t.agentName}</span>
        {/* Short "AI" on phones, as in the mobile board; the full label from md up. */}
        <Tag>
          <span className="md:hidden">AI</span>
          <span className="max-md:hidden whitespace-nowrap">{t.aiTag}</span>
        </Tag>
      </Link>

      <div className="ms-auto flex items-center gap-2 md:gap-5">
        <nav aria-label={t.nav} className="hidden items-center gap-5 text-ui md:flex">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="rounded-sm text-text-muted hover:text-text">
              {l.label}
            </Link>
          ))}
        </nav>

        <LangToggle current={lang} label={t.language} />

        <a href={cvHref} download className={buttonClass("secondary", "text-[14px] max-md:hidden")}>
          <DownloadIcon />
          {t.downloadCv}
        </a>

        {/* Mobile: the same links behind a disclosure. No JS; the summary is keyboard-reachable. */}
        <details className="relative md:hidden">
          <summary
            aria-label={t.nav}
            className="flex size-10 cursor-pointer list-none items-center justify-center rounded-[8px] hover:bg-surface-sunken [&::-webkit-details-marker]:hidden"
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" aria-hidden="true">
              <circle cx="9" cy="3.5" r="1.5" />
              <circle cx="9" cy="9" r="1.5" />
              <circle cx="9" cy="14.5" r="1.5" />
            </svg>
          </summary>
          <ul className="absolute end-0 top-12 z-10 flex w-52 flex-col rounded-lg border border-border bg-surface-raised p-1.5 text-ui shadow-pop">
            {links.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="block rounded-sm px-3 py-2.5 hover:bg-surface-sunken">
                  {l.label}
                </Link>
              </li>
            ))}
            <li>
              <a href={cvHref} download className="flex items-center gap-2 rounded-sm px-3 py-2.5 hover:bg-surface-sunken">
                <DownloadIcon />
                {t.downloadCv}
              </a>
            </li>
          </ul>
        </details>
      </div>
    </header>
  );
}

import type { ReactNode } from "react";

import { getDictionary, type Locale } from "@/app/[lang]/dictionaries";
import { Header } from "./Header";

export { Callout, Section, TableFrame, Term, td, th } from "./doc";

const repo = "https://github.com/sarah94087-bot/portfolio-agent";
export const repoUrl = (path = "") => (path ? `${repo}/${path}` : repo);
export const repoFile = (path: string) => repoUrl(`blob/main/${path}`);
export const adrUrl = (name: string) => repoFile(`docs/adr/${name}.md`);

// The reading pages: /how-it-works, /quality, /stats and /privacy. No board exists for them, so
// they use the tokens and the type scale of the conversation screens.
export function DocPage({
  lang,
  eyebrow,
  title,
  lede,
  children,
}: {
  lang: Locale;
  eyebrow: string;
  title: string;
  lede: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <Header lang={lang} t={getDictionary(lang).header} />
      <main className="flex-1 px-4 pb-16 pt-8 md:pt-12">
        <article className="mx-auto w-full max-w-measure">
          <p className="mb-2 text-[13px] font-bold text-accent md:text-[14px]">{eyebrow}</p>
          <h1 className="text-[30px] font-extrabold leading-[1.25] tracking-[-0.01em] md:text-h1">{title}</h1>
          <p className="mt-3 text-[17px] leading-[1.65] text-text-muted md:text-[19px] md:leading-[1.7]">{lede}</p>
          {children}
        </article>
      </main>
    </>
  );
}

export function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-3">
      {children}
    </a>
  );
}

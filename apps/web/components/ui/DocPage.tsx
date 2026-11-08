import type { ReactNode } from "react";

import { getDictionary, type Locale } from "@/app/[lang]/dictionaries";
import { Header } from "./Header";

const repo = "https://github.com/sarah94087-bot/portfolio-agent";
export const repoUrl = (path = "") => (path ? `${repo}/${path}` : repo);
export const repoFile = (path: string) => repoUrl(`blob/main/${path}`);
export const adrUrl = (name: string) => repoFile(`docs/adr/${name}.md`);

// The reading pages: /how-it-works, /quality and /privacy. No board exists for them, so they
// use the tokens and the type scale of the conversation screens.
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

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10 md:mt-12">
      <h2 className="mb-3 text-[22px] font-extrabold leading-[1.3] md:text-h2">{title}</h2>
      <div className="flex flex-col gap-3 text-body">{children}</div>
    </section>
  );
}

export function Callout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-6 rounded-lg border border-dashed border-border-input bg-surface-sunken px-4 py-3">
      <p className="font-bold">{title}</p>
      <p className="mt-1 text-ui text-text-muted">{children}</p>
    </div>
  );
}

export function Ext({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-3">
      {children}
    </a>
  );
}

// A technical term or a number inside running text, safe in either direction.
export function Term({ children }: { children: ReactNode }) {
  return <bdi className="mono text-[0.82em]">{children}</bdi>;
}

// Wide content scrolls inside its own frame on a phone, and the keyboard can reach it.
export function TableFrame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className="overflow-x-auto rounded-md border border-border bg-surface-raised">
      <table className="w-full border-collapse text-start text-ui [&_.mono]:text-[0.88em]">{children}</table>
    </div>
  );
}

export const th = "whitespace-nowrap border-b border-border-strong px-3 py-2 text-start text-small font-bold";
export const td = "border-b border-border px-3 py-2 align-top";

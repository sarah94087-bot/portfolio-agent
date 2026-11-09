import type { ReactNode } from "react";

// The pieces of a reading page that hold no server-only copy, so a client component can use them.

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

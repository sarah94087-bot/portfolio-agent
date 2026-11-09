"use client";

import { useEffect, useState } from "react";

import { Callout, Section, TableFrame, td, th } from "@/components/ui/doc";
import {
  WINDOWS,
  fetchStats,
  hasNumbers,
  modelNames,
  seconds,
  shareOf,
  type RateMetric,
  type Stats,
  type StatsWindow,
  type TimeMetric,
} from "@/lib/stats";

type Row<K> = { key: K; name: string; hint?: string };

export type StatsCopy = {
  columns: { measure: string; model: string; windows: Record<StatsWindow, string> };
  none: string; // below the threshold
  loading: string;
  failedTitle: string;
  failed: string;
  updated: string; // followed by the date
  notYetTitle: string;
  notYet: string;
  fewTitle: string;
  few: string;
  second: string; // the unit after a number of seconds
  timesTitle: string;
  times: Row<TimeMetric>[];
  ratesTitle: string;
  rates: Row<RateMetric>[];
  modelsTitle: string;
  modelsIntro: string;
};

// The first paint is the loading state. The page itself is static, and the numbers come from a
// response the CDN holds for 5 minutes (docs/08-transparency.md, section 4).
export function StatsBoard({ c }: { c: StatsCopy }) {
  const [stats, setStats] = useState<Stats | null | "loading">("loading");

  useEffect(() => {
    let live = true;
    void fetchStats().then((result) => {
      if (live) setStats(result);
    });
    return () => {
      live = false;
    };
  }, []);

  if (stats === null) {
    return (
      <div role="status">
        <Callout title={c.failedTitle}>{c.failed}</Callout>
      </div>
    );
  }
  const ready = stats === "loading" ? null : stats;

  const cell = (value: number | null | undefined, format: (v: number) => string) => {
    if (!ready) return <span className="text-text-muted" aria-hidden="true">…</span>;
    if (value === null || value === undefined) return <span className="text-small text-text-muted">{c.none}</span>;
    return <bdi className="mono font-bold">{format(value)}</bdi>;
  };
  const time = (ms: number) => `${seconds(ms)} ${c.second}`;
  const rate = (share: number) => `${share}%`;

  const head = (first: string) => (
    <thead>
      <tr>
        <th scope="col" className={th}>{first}</th>
        {WINDOWS.map((w) => (
          <th key={w} scope="col" className={th}>{c.columns.windows[w]}</th>
        ))}
      </tr>
    </thead>
  );
  const name = <K,>(row: Row<K>) => (
    <th scope="row" className={`${td} text-start font-normal`}>
      {row.name}
      {row.hint && <span className="mt-0.5 block text-small text-text-muted">{row.hint}</span>}
    </th>
  );
  const models = ready ? modelNames(ready) : [];

  return (
    <div aria-busy={!ready}>
      <div role="status">
        {!ready && <p className="mt-6 text-ui text-text-muted">{c.loading}</p>}
        {ready && !ready.updated && <Callout title={c.notYetTitle}>{c.notYet}</Callout>}
        {ready?.updated && !hasNumbers(ready) && <Callout title={c.fewTitle}>{c.few}</Callout>}
        {ready?.updated && hasNumbers(ready) && (
          <p className="mt-6 text-ui text-text-muted">
            {c.updated} <bdi className="mono">{ready.updated}</bdi>
          </p>
        )}
      </div>

      <Section title={c.timesTitle}>
        <TableFrame label={c.timesTitle}>
          {head(c.columns.measure)}
          <tbody>
            {c.times.map((row) => (
              <tr key={row.key}>
                {name(row)}
                {WINDOWS.map((w) => (
                  <td key={w} className={td}>{cell(ready?.windows[w][row.key], time)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </TableFrame>
      </Section>

      <Section title={c.ratesTitle}>
        <TableFrame label={c.ratesTitle}>
          {head(c.columns.measure)}
          <tbody>
            {c.rates.map((row) => (
              <tr key={row.key}>
                {name(row)}
                {WINDOWS.map((w) => (
                  <td key={w} className={td}>{cell(ready?.windows[w][row.key], rate)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </TableFrame>
      </Section>

      <Section title={c.modelsTitle}>
        <p>{c.modelsIntro}</p>
        {models.length > 0 && ready ? (
          <TableFrame label={c.modelsTitle}>
            {head(c.columns.model)}
            <tbody>
              {models.map((model) => (
                <tr key={model}>
                  <th scope="row" className={`${td} text-start font-normal`}>
                    <bdi className="mono">{model}</bdi>
                  </th>
                  {WINDOWS.map((w) => (
                    <td key={w} className={td}>{cell(shareOf(ready, w, model), rate)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </TableFrame>
        ) : (
          ready && <p className="text-ui text-text-muted">{c.none}</p>
        )}
      </Section>
    </div>
  );
}

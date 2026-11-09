-- What /stats shows (docs/08-transparency.md, section 4). One row per metric, per window, per run.
-- A percentile of 7 days cannot be built from 7 daily percentiles, so every run computes both
-- windows from the answers themselves (daily_metrics.py). Aggregates only: nothing here points at
-- a visitor or a conversation, so the rows stay after the conversations are deleted.
--
-- sample_size stays in this table. GET /api/stats compares it to the threshold and never returns
-- it: visitors are not shown usage numbers (US-9.3). `value` is empty when nothing was observed.
create table daily_metrics (
  day date not null,  -- the last whole UTC day in the window
  metric text not null,
  window_days smallint not null check (window_days in (7, 30)),
  value double precision,
  sample_size integer not null check (sample_size >= 0),
  primary key (day, metric, window_days)
);

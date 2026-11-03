-- Knowledge base chunks (docs/05-architecture.md, section 7), filled by portfolio_agent.ingest.
-- The embedding column comes in its own migration, once M3 picks the model (ADR-0009).
-- Retrieval experiments copy this table per chunking strategy: create temp table ... (like chunks
-- including all), so the experiment and production search run the same SQL.
create table chunks (
  id text primary key,                     -- '<record>#<section>', what answers cite
  record_id text not null,
  sections text[] not null,                -- C1 sections it covers, to score against D1
  text text not null,
  context_header text not null default '', -- C2 only
  aliases text not null default '',        -- the record's aliases, for trigram matching (R1)
  norm text not null,                      -- header and text, normalized for Hebrew
  tsv tsvector generated always as (to_tsvector('simple', norm)) stored,
  content_hash text not null,              -- upsert touches a row only when this changes
  commit_sha text,                         -- which version of the portfolio it came from
  updated_at timestamptz not null default now()
);

create index chunks_tsv on chunks using gin (tsv);
create index chunks_norm_trgm on chunks using gin (norm gin_trgm_ops);
create index chunks_aliases_trgm on chunks using gin (aliases gin_trgm_ops);
create index chunks_record on chunks (record_id);

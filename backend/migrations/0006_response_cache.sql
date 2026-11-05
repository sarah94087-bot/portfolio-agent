-- Answers to first questions, served again without a model call (docs/06-agent-design.md,
-- section 7). The key already holds the prompt version and the knowledge base version, so a
-- change to either misses on its own; expires_at bounds how long a model's wording is reused.
create table response_cache (
  key_hash text primary key,
  response jsonb not null,  -- content with [[chunk_id]], steps, model, allowed chunks
  hits integer not null default 0,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

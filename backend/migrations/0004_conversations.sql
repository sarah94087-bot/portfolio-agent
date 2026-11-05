-- Conversations, messages and the steps of each answer (docs/05-architecture.md, section 7).
-- Kept 30 days (docs/09-security-privacy.md); the retention job comes with M6.
-- visitor_id stays empty until the signed visitor cookie lands (docs/05, section 6).

create table conversations (
  id uuid primary key default gen_random_uuid(),
  visitor_id text,
  company_slug text,
  created_at timestamptz not null default now()
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations (id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  -- For an answer: what the visitor saw, with valid citations as [[chunk_id]], so the model
  -- reads them in later turns and a replay gives the same events. Never the raw model text.
  content text not null,
  model text,
  prompt_version text,
  usage jsonb not null default '{}',
  -- retrieved chunk ids, cited numbers, dropped ids, guard results, model switches
  meta jsonb not null default '{}',
  idempotency_key text,
  created_at timestamptz not null default now()
);

create index messages_conversation on messages (conversation_id, created_at);
-- One answer per key: a resent message returns the stored answer (US-10.5).
create unique index messages_idempotency on messages (idempotency_key) where role = 'assistant';

create table steps (
  id bigint generated always as identity primary key,
  message_id uuid not null references messages (id) on delete cascade,
  step_id text not null,
  kind text not null,
  name text,
  args jsonb,
  result_summary jsonb,
  duration_ms integer
);

create index steps_message on steps (message_id);

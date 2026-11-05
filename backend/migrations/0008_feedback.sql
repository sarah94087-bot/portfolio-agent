-- Feedback on an answer (US-2.7; docs/05-architecture.md, section 7). One row per answer: the
-- visitor may change their mind, and the last rating counts. Nothing about the visitor is kept
-- here; who may rate is checked through the answer's conversation. The comment is masked
-- (emails, phones) before it is saved. Deleted with its message, so with the conversation
-- (US-12.4) and after 30 days (the retention job comes with M6).
create table feedback (
  message_id uuid primary key references messages (id) on delete cascade,
  rating text not null check (rating in ('up', 'down')),
  comment text check (char_length(comment) <= 300),
  -- "This was a challenge attempt": the visitor tried to make the agent lie (docs/03, section 9)
  challenge boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

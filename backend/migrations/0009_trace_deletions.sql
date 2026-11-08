-- Answers whose traces must still be deleted from Langfuse (docs/09-security-privacy.md, section 6).
-- An answer's id is its trace id (tracing.py), so the daily job (retention.py) can delete the
-- trace by id after the conversation is gone. Finding traces by session would not work: on the
-- Hobby plan Langfuse's read API sees only the last 30 days, which is when conversations expire.
--
-- A trigger, so every way of deleting an answer is covered in the same transaction: the visitor's
-- delete button (US-12.4), the retention job and any manual delete. Holds no content, only the id.
create table trace_deletions (
  trace_id uuid primary key,
  traced_at timestamptz not null
);

create function queue_trace_deletion() returns trigger language plpgsql as $$
begin
  insert into trace_deletions (trace_id, traced_at) values (old.id, old.created_at)
    on conflict (trace_id) do nothing;
  return old;
end;
$$;

create trigger messages_trace_deletion after delete on messages
  for each row when (old.role = 'assistant') execute function queue_trace_deletion();

-- A question is saved with its idempotency key too (US-10.5). When the stream drops after the
-- question was saved and before the answer was, the visitor sends it again with the same key:
-- the server then continues from the saved question instead of saving it a second time, so the
-- history holds it once and the conversation limit counts it once.
-- Per conversation, not global: a key that another visitor reuses lands in their own
-- conversation and must not collide with this one.
create unique index messages_question_key on messages (conversation_id, idempotency_key)
  where role = 'user';

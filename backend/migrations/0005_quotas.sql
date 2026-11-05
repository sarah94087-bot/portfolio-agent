-- Limits and quotas (docs/09-security-privacy.md, section 4). One row per scope, key and day,
-- raised with an atomic upsert, so two requests at once cannot both pass the last slot.
-- Kept 7 days (docs/05-architecture.md, section 7); the retention job comes with M6.
create table quota_counters (
  scope text not null,       -- visitor | visitor_minute | ip | provider_tokens | ...
  key text not null,         -- a visitor id, an IP hash, a model name
  day date not null,
  count bigint not null default 0,
  primary key (scope, key, day)
);

-- The daily salt for IP hashes. Random, never derived from a secret, and deleted after 2 days,
-- so once it is gone nobody can tell which IP a hash came from (docs/09, section 6).
create table ip_salts (
  day date primary key,
  salt bytea not null
);

create index conversations_visitor on conversations (visitor_id);

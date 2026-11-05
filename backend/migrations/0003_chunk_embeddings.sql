-- The embeddings column, now that M3 chose the model: multilingual-e5-small, 384 dimensions
-- (ADR-0012). Filled by ingest with the "passage: " prefix; empty until a chunk is embedded.
-- At about a hundred chunks an exact scan is as fast as HNSW, so there is no index yet.
alter table chunks add column if not exists embedding vector(384);

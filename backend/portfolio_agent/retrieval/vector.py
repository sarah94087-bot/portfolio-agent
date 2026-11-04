"""R2: vector search with pgvector, cosine (docs/04-retrieval-design.md, section 3, axis B).

The embeddings model is chosen in M3 (ADR-0009), so this module takes vectors, not text: the
caller embeds the query and the chunks with the same model. The column is added to a table
(a temp table in experiments) with the model's dimension. At this size (about a hundred chunks)
an exact scan is as fast as HNSW, so the index waits for the production migration.
"""

from collections.abc import Mapping, Sequence

import psycopg
from psycopg import sql

from portfolio_agent.retrieval.lexical import Hit


def to_vector(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


def add_embedding_column(conn: psycopg.Connection, table: str, dim: int) -> None:
    conn.execute(
        sql.SQL("alter table {} add column if not exists embedding vector({})").format(
            sql.Identifier(table), sql.Literal(dim)
        )
    )


def store_embeddings(
    conn: psycopg.Connection, table: str, vectors: Mapping[str, Sequence[float]]
) -> None:
    stmt = sql.SQL("update {} set embedding = %s::vector where id = %s").format(
        sql.Identifier(table)
    )
    with conn.transaction():
        for cid, vec in vectors.items():
            conn.execute(stmt, (to_vector(vec), cid))


def search(
    conn: psycopg.Connection, query_vector: Sequence[float], k: int = 10, table: str = "chunks"
) -> list[Hit]:
    """The k chunks closest to the query by cosine distance, best first."""
    rows = conn.execute(
        sql.SQL(
            "select id, record_id, sections, text, 1 - (embedding <=> %s::vector) as sim"
            " from {} where embedding is not null"
            " order by embedding <=> %s::vector, id limit %s"
        ).format(sql.Identifier(table)),
        (to_vector(query_vector), to_vector(query_vector), k),
    ).fetchall()
    return [Hit(r[0], r[1], tuple(r[2]), r[3], {"vector": float(r[4])}) for r in rows]

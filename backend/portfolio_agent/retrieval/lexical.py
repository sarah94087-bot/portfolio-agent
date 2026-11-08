"""R1: lexical search in Postgres (docs/04-retrieval-design.md, section 3, axis B).

Two rankings over the same chunks table, fused with Reciprocal Rank Fusion (k = 60, as R3):
- BM25 over the `simple` tsvector. ts_rank has no inverse document frequency, so a common word
  such as "she" would count as much as "pgvector". BM25 is the usual lexical baseline, and it
  runs in SQL over the tsvector, with no extra search service.
- Trigram word similarity of each query term against the text and the record's aliases, with
  the same IDF weight. It matches Hebrew words with a prefix (בפרויקט and פרויקט) and
  spelling variants.
Both sides use the same normalization (retrieval/normalize.py).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import psycopg
from psycopg import sql

from portfolio_agent.retrieval.normalize import normalize

RRF_K = 60
CANDIDATES = 20  # per ranking, as in the search_portfolio contract (docs/04, section 8)
BM25_K1, BM25_B = 1.2, 0.75
MIN_SIMILARITY = 0.5  # word_similarity below this is noise

# Question words and function words. BM25 already gives them little weight, but they would
# still add a match to almost every chunk. Normalized like the text, so ך and כ are the same.
_STOPWORDS = """
    a an and are as at be but by can could did do does for from had has have he her hers him his
    how i if in into is it its me my of on or our she so than that the their them then there these
    they this to was we were what when where which who whom why will with would you your
    של את על עם מה איך היא הוא הם הן זה זו זאת יש אין לה לו גם או אם כי כמו מי מתי איפה למה האם
    אצל עוד כל לא כן אני אתה אנחנו
"""
STOPWORDS = sorted({normalize(w) for w in _STOPWORDS.split()})


@dataclass(frozen=True)
class Hit:
    id: str
    record_id: str
    sections: tuple[str, ...]
    text: str
    scores: dict[str, float | None] = field(default_factory=dict)


TERMS = """
terms as (
  select distinct lexeme as term from unnest(to_tsvector('simple', %(q)s))
  where lexeme <> all(%(stop)s) and length(lexeme) > 1
)"""

BM25 = """
with {terms},
docs as (
  select c.id, c.record_id, u.lexeme, coalesce(array_length(u.positions, 1), 1)::float as tf
  from {t} c, unnest(c.tsv) u
),
len as (select id, sum(tf) as dl from docs group by id),
corpus as (select count(*)::float as n, avg(dl) as avgdl from len),
df as (
  select lexeme, count(*)::float as df from docs
  where lexeme in (select term from terms) group by lexeme
)
select d.id, sum(
  ln(1 + (corpus.n - df.df + 0.5) / (df.df + 0.5))
  * d.tf * (%(k1)s + 1) / (d.tf + %(k1)s * (1 - %(b)s + %(b)s * len.dl / corpus.avgdl))
) as score
from docs d join df using (lexeme) join len using (id) cross join corpus
where %(records)s::text[] is null or d.record_id = any(%(records)s::text[])
group by d.id order by score desc, d.id limit %(n)s
"""

# Weighted by the same inverse document frequency as BM25. Without it, a word in every chunk
# ('sarah') fills the candidate list with ties and pushes out chunks with the rare word.
TRIGRAM = """
with {terms},
hits as (
  select c.id, c.record_id, terms.term, s.sim from {t} c cross join terms
  cross join lateral (
    select greatest(word_similarity(terms.term, c.norm), word_similarity(terms.term, c.aliases))
    as sim
  ) s
  where s.sim >= %(min_sim)s
),
corpus as (select count(*)::float as n from {t}),
df as (select term, count(*)::float as df from hits group by term)
select h.id, sum(h.sim * ln(1 + (corpus.n - df.df + 0.5) / (df.df + 0.5))) as score
from hits h join df using (term) cross join corpus
where %(records)s::text[] is null or h.record_id = any(%(records)s::text[])
group by h.id order by score desc, h.id limit %(n)s
"""


def ranking(
    conn: psycopg.Connection, query: str, table: str, kind: str,
    records: Sequence[str] | None = None,
) -> list[tuple[str, float]]:
    template = BM25 if kind == "bm25" else TRIGRAM
    stmt = sql.SQL(template).format(terms=sql.SQL(TERMS), t=sql.Identifier(table))
    params = {
        "q": query, "stop": STOPWORDS, "n": CANDIDATES, "records": records,
        "k1": BM25_K1, "b": BM25_B, "min_sim": MIN_SIMILARITY,
    }
    return [(row[0], float(row[1])) for row in conn.execute(stmt, params)]


def search(
    conn: psycopg.Connection, query: str, k: int = 10, table: str = "chunks",
    records: Sequence[str] | None = None,
) -> list[Hit]:
    """`records` limits the candidates to those records, before the top ones are taken. Word
    weights still come from the whole table, so a filter does not change how terms count."""
    q = normalize(query)
    bm25 = ranking(conn, q, table, "bm25", records)
    trigram = ranking(conn, q, table, "trigram", records)
    fused: dict[str, float] = {}
    for ranked in (bm25, trigram):
        for rank, (cid, _) in enumerate(ranked, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1 / (RRF_K + rank)
    top = sorted(fused, key=lambda cid: (-fused[cid], cid))[:k]
    if not top:
        return []
    rows = conn.execute(
        sql.SQL("select id, record_id, sections, text from {} where id = any(%s)").format(
            sql.Identifier(table)
        ),
        (top,),
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    bm25_scores, trigram_scores = dict(bm25), dict(trigram)
    return [
        Hit(
            cid, by_id[cid][1], tuple(by_id[cid][2]), by_id[cid][3],
            {"bm25": bm25_scores.get(cid), "trigram": trigram_scores.get(cid),
             "rrf": fused[cid]},
        )
        for cid in top
    ]

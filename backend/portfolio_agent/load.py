"""Load the knowledge base into the database the agent searches.

    python -m portfolio_agent.load [--dry-run] [--reembed] [database url]

The URL is the argument, or DATABASE_URL. In order:
1. migrations (migrate.py), so the tables exist;
2. the portfolio, chunked by C4 (ADR-0010), written by ingest.upsert: a chunk is written only
   when its content hash changed, and a chunk whose record is gone is deleted;
3. embeddings for every chunk without one (ADR-0012), with the pinned model files of
   EMBEDDING_MODEL_DIR, checked by hash (Sarah's decision: the check runs at ingest);
4. a check that every chunk has a vector, and the knowledge base version the response cache
   keys on (db/cache.py), so a run says which version the agent now answers from.

--dry-run reads the database and the portfolio and prints what would change, writing nothing.
--reembed replaces every chunk's vector, not only the missing ones: for when the embedding
computation changes and the chunks do not (ADR-0015).
"""

import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from portfolio_agent import migrate
from portfolio_agent.config import Settings
from portfolio_agent.db.cache import kb_version
from portfolio_agent.ingest import chunk, embed_missing, load, upsert
from portfolio_agent.retrieval import embedder

STRATEGY = "C4"


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=Path(__file__).parent).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def where(url: str) -> str:
    """The host and database, never the password."""
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port or 5432}{parts.path}"


def plan(conn: psycopg.Connection, chunks, table: str = "chunks") -> dict[str, list[str]]:
    exists = conn.execute("select to_regclass(%s)", (table,)).fetchone()[0]
    before = dict(conn.execute(sql.SQL("select id, content_hash from {}")
                               .format(sql.Identifier(table))).fetchall()) if exists else {}
    return {
        "insert": sorted(c.id for c in chunks if c.id not in before),
        "update": sorted(c.id for c in chunks if c.id in before
                         and before[c.id] != c.content_hash),
        "delete": sorted(before.keys() - {c.id for c in chunks}),
    }


def run(url: str, model_dir: Path | None, dry_run: bool = False, table: str = "chunks",
        log=print, reembed: bool = False) -> dict:
    docs = load()
    chunks = chunk(docs, STRATEGY)
    log(f"target: {where(url)}, table {table}")
    log(f"portfolio: {len(docs)} records, {len(chunks)} chunks ({STRATEGY})")
    if dry_run:
        with psycopg.connect(url, connect_timeout=10) as conn:
            changes = plan(conn, chunks, table)
        for kind, ids in changes.items():
            log(f"would {kind} {len(ids)}" + (f": {', '.join(ids)}" if ids else ""))
        if reembed:
            log(f"would re-embed {len(chunks)}")
        return {"dry_run": True, **{k: len(v) for k, v in changes.items()}}

    if model_dir is None:
        raise SystemExit(f"{embedder.ENV_VAR} is not set: search needs the vectors (R3)")
    e5 = embedder.E5Embedder(model_dir, check=True)  # the hash check runs here, at ingest
    migrate.run(url)
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
        counts = upsert(conn, chunks, table, commit_sha=_commit())
        counts["embedded"] = embed_missing(conn, chunks, e5, table, every=reembed)
        missing = conn.execute(sql.SQL("select count(*) from {} where embedding is null")
                               .format(sql.Identifier(table))).fetchone()[0]
        if missing:
            raise SystemExit(f"{missing} chunks have no vector after embedding")
        counts["kb_version"] = kb_version(conn, table)
    log(", ".join(f"{k} {v}" for k, v in counts.items()))
    return counts


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a not in ("--dry-run", "--reembed")]
    url = args[0] if args else Settings.from_env().database_url
    if not url:
        print("usage: python -m portfolio_agent.load [--dry-run] [--reembed] [database url]"
              "  (or set DATABASE_URL)")
        return 2
    run(url, embedder.model_dir_from_env(), dry_run="--dry-run" in argv,
        reembed="--reembed" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

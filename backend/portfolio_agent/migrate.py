"""Apply numbered SQL migrations in order: python -m portfolio_agent.migrate

Migrations are forward only and must stay backward compatible with the running code,
because deploy.yml migrates before it deploys (docs/10-ops-and-costs.md, section 5).
Uses DATABASE_URL_DIRECT when set, since migrations should not go through the pooler.
"""

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def pending(conn: psycopg.Connection, files: list[Path]) -> list[Path]:
    conn.execute(
        "create table if not exists schema_migrations ("
        " name text primary key, applied_at timestamptz not null default now())"
    )
    applied = {row[0] for row in conn.execute("select name from schema_migrations")}
    return [f for f in files if f.name not in applied]


def run(database_url: str) -> list[str]:
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    done: list[str] = []
    with psycopg.connect(database_url, autocommit=True, connect_timeout=10) as conn:
        for path in pending(conn, files):
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
            done.append(path.name)
    return done


def main() -> int:
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL_DIRECT or DATABASE_URL is required", file=sys.stderr)
        return 2
    applied = run(url)
    print("applied: " + (", ".join(applied) if applied else "nothing, already up to date"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

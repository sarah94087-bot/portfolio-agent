"""Ingestion, first part: python -m portfolio_agent.ingest [portfolio_dir]

Reads the knowledge base through kb_check, refuses to go on if any record fails it, and cuts
the records into chunks with each of the four strategies in docs/04-retrieval-design.md,
section 3 (C1 to C4). The CLI prints how many chunks each strategy makes and how long they are.
`upsert` writes one strategy's chunks to Postgres by content hash (docs/02-knowledge-base.md,
section 9). Embeddings come once M3 picks the model.

Every chunk lists the C1 sections it covers. D1 names its gold chunks by C1 id, so the same
gold set can score a C3 window or a C4 record that contains the right section.
"""

import hashlib
import re
import statistics
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import psycopg
from psycopg import sql
from pydantic import BaseModel

from portfolio_agent.kb_check import (
    PORTFOLIO_DIR,
    Education,
    Experience,
    Project,
    Skills,
    body_sections,
    check,
    check_file,
    split,
)
from portfolio_agent.retrieval.normalize import normalize

STRATEGIES = ("C1", "C2", "C3", "C4")

# Stable section ids for chunk ids '<record>#<section>' (docs/02-knowledge-base.md, section 3).
# Responsibilities is an experience record's 'role', as in docs/07-advanced-capabilities.md.
SECTION_IDS = {
    "Problem": "problem",
    "Why it was hard": "why-hard",
    "My role": "role",
    "Architecture": "architecture",
    "Decisions and alternatives": "decisions",
    "What broke": "what-broke",
    "Results": "results",
    "In hindsight": "hindsight",
    "Context": "context",
    "Responsibilities": "role",
    "Projects": "projects",
}

LEVEL_TEXT = {
    "used": "Sarah used it in project work",
    "studied": "Sarah learned it in a program or course, not in project work",
    "listed": "it is on Sarah's CV, with no further detail",
}

# C3 counts tokens before an embeddings model is chosen, so it cannot use that model's
# tokenizer. A word or a single punctuation mark is one token, close to BPE for English.
TOKEN = re.compile(r"\w+|[^\w\s]")
WINDOW, OVERLAP = 300, 50


class IngestError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    id: str
    record_id: str
    sections: tuple[str, ...]  # the C1 ids this chunk covers
    text: str
    header: str = ""  # C2 only: which record this is, for a section that does not say
    aliases: str = ""  # the record's aliases in both languages, for trigram matching (R1)

    @property
    def content(self) -> str:
        """What gets indexed and embedded."""
        return f"{self.header}\n\n{self.text}" if self.header else self.text

    @property
    def content_hash(self) -> str:
        indexed = f"{self.content}\n\n{self.aliases}"
        return hashlib.sha256(indexed.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Doc:
    record: BaseModel
    sections: list[tuple[str, str]]  # (C1 section id, text), comments removed


def load(portfolio_dir: Path = PORTFOLIO_DIR) -> list[Doc]:
    """Every record, parsed by kb_check. Nothing is ingested while any record has an error."""
    errors = check(portfolio_dir)
    if errors:
        lines = [f"{rel}: {err}" for rel, errs in errors.items() for err in errs]
        raise IngestError("the knowledge base fails kb_check:\n" + "\n".join(lines))
    docs = []
    for path in sorted(portfolio_dir.rglob("*.md")):
        record, _ = check_file(path)
        _, body = split(path.read_text(encoding="utf-8"))
        docs.append(Doc(record, doc_sections(body)))
    return docs


def doc_sections(body: str) -> list[tuple[str, str]]:
    """(C1 section id, text) for the body, comments removed and empty sections dropped.

    kb_check fixes the headings of projects and experience only. Other types (education, and
    later profile and faq) may use any heading, which gets a slug as its id, and may put text
    before the first heading, which becomes the section 'body', so no text is silently lost.
    """
    first = re.search(r"^## ", body, re.MULTILINE)
    parts = [("body", body[: first.start()] if first else body)]
    parts += [(SECTION_IDS.get(name) or slug(name), text) for name, text in body_sections(body)]
    cleaned = [(sid, re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL).strip()) for sid, t in parts]
    return [(sid, text) for sid, text in cleaned if text]


def chunk(docs: list[Doc], strategy: str) -> list[Chunk]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy '{strategy}', expected one of {STRATEGIES}")
    chunks = []
    for doc in docs:
        if isinstance(doc.record, Skills):
            # Each skill is its own chunk in every strategy (docs/04-retrieval-design.md, 7).
            chunks += skill_chunks(doc.record, with_header=strategy == "C2")
        elif strategy in ("C1", "C2"):
            header = context_header(doc.record) if strategy == "C2" else ""
            chunks += [
                Chunk(f"{doc.record.id}#{sid}", doc.record.id, (sid,), text, header)
                for sid, text in doc.sections
            ]
        elif strategy == "C3":
            chunks += windows(doc)
        elif doc.sections:
            text = "\n\n".join(text for _, text in doc.sections)
            sids = tuple(sid for sid, _ in doc.sections)
            chunks.append(Chunk(f"{doc.record.id}#all", doc.record.id, sids, text))
    # R1 matches a record's aliases whatever the strategy, so every chunk carries them.
    aliases = {
        d.record.id: ", ".join(d.record.aliases)
        for d in docs if getattr(d.record, "aliases", None)
    }
    chunks = [replace(c, aliases=aliases.get(c.record_id, "")) for c in chunks]
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        raise IngestError(f"duplicate chunk ids in {strategy}")
    return chunks


def context_header(record: Project | Experience | Education) -> str:
    lines = [f"{record.title.en} ({record.title.he})"]
    if getattr(record, "aliases", None):
        lines.append(f"Aliases: {', '.join(record.aliases)}")
    if isinstance(record, Project):
        lines.append(f"Tech: {', '.join(record.tech)}")
    return "\n".join(lines)


def slug(name: str) -> str:
    # C# and C++ must not both become 'c'.
    name = name.lower().replace("#", "sharp").replace("+", "plus")
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def skill_chunks(skills: Skills, with_header: bool) -> list[Chunk]:
    header = f"{skills.title.en} ({skills.title.he})" if with_header else ""
    chunks = []
    for s in skills.skills:
        text = f"{s.name}. Level: {s.level}, {LEVEL_TEXT[s.level]}."
        if s.evidence:
            text += f" Evidence: {', '.join(s.evidence)}."
        if s.note:
            text += f" {s.note}"
        sid = slug(s.name)
        chunks.append(Chunk(f"skills#{sid}", "skills", (sid,), text, header))
    return chunks


def windows(doc: Doc) -> list[Chunk]:
    """C3: fixed windows of WINDOW tokens, each starting OVERLAP tokens before the last ends.

    A window covers a section when it holds all of it, or at least OVERLAP tokens of it. A few
    words at the edge of a window are not enough, so C3 gets no credit it did not earn.
    """
    tokens, spans = [], []  # spans: (section id, first token, end token)
    text = ""
    for sid, part in doc.sections:
        if text:
            text += "\n\n"
        first = len(tokens)
        tokens += [(s + len(text), e + len(text)) for s, e in
                   (m.span() for m in TOKEN.finditer(part))]
        spans.append((sid, first, len(tokens)))
        text += part
    if not tokens:
        return []
    chunks, start = [], 0
    while True:
        end = min(start + WINDOW, len(tokens))
        lo, hi = tokens[start][0], tokens[end - 1][1]
        sids = tuple(
            sid for sid, s, e in spans
            if min(end, e) - max(start, s) >= min(OVERLAP, e - s) > 0
        )
        n = len(chunks) + 1
        chunks.append(Chunk(f"{doc.record.id}#w{n}", doc.record.id, sids, text[lo:hi]))
        if end == len(tokens):
            return chunks
        start = end - OVERLAP


def upsert(
    conn: psycopg.Connection,
    chunks: list[Chunk],
    table: str = "chunks",
    commit_sha: str | None = None,
) -> dict[str, int]:
    """Writes one strategy's chunks. A row is written only when its hash changed, and a row whose
    chunk is gone (a renamed or removed section) is deleted, so the table matches the portfolio."""
    t = sql.Identifier(table)
    before = dict(conn.execute(sql.SQL("select id, content_hash from {}").format(t)).fetchall())
    changed = [c for c in chunks if before.get(c.id) != c.content_hash]
    gone = sorted(before.keys() - {c.id for c in chunks})
    with conn.transaction():
        for c in changed:
            conn.execute(
                sql.SQL(
                    "insert into {} (id, record_id, sections, text, context_header, aliases,"
                    " norm, content_hash, commit_sha)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " on conflict (id) do update set record_id = excluded.record_id,"
                    " sections = excluded.sections, text = excluded.text,"
                    " context_header = excluded.context_header, aliases = excluded.aliases,"
                    " norm = excluded.norm, content_hash = excluded.content_hash,"
                    " commit_sha = excluded.commit_sha, updated_at = now()"
                ).format(t),
                (c.id, c.record_id, list(c.sections), c.text, c.header,
                 normalize(c.aliases), normalize(c.content), c.content_hash, commit_sha),
            )
        if gone:
            conn.execute(sql.SQL("delete from {} where id = any(%s)").format(t), (gone,))
    return {
        "inserted": sum(1 for c in changed if c.id not in before),
        "updated": sum(1 for c in changed if c.id in before),
        "deleted": len(gone),
        "unchanged": len(chunks) - len(changed),
    }


def count_tokens(text: str) -> int:
    return len(TOKEN.findall(text))


def main() -> int:
    portfolio_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PORTFOLIO_DIR
    try:
        docs = load(portfolio_dir)
    except IngestError as e:
        print(e)
        return 1
    print(f"{len(docs)} files")
    print("strategy  chunks  skills  record tokens min / median / max")
    for strategy in STRATEGIES:
        chunks = chunk(docs, strategy)
        # Skill chunks are the same in every strategy, so they stay out of the sizes.
        sizes = [count_tokens(c.content) for c in chunks if c.record_id != "skills"]
        print(
            f"{strategy:<8}  {len(chunks):>6}  {len(chunks) - len(sizes):>6}  "
            f"{min(sizes)} / {statistics.median(sizes):g} / {max(sizes)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

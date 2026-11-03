"""Ingestion, first part: python -m portfolio_agent.ingest [portfolio_dir]

Reads the knowledge base through kb_check, refuses to go on if any record fails it, and cuts
the records into chunks with each of the four strategies in docs/04-retrieval-design.md,
section 3 (C1 to C4). The CLI prints how many chunks each strategy makes and how long they are.
Embeddings and the upsert to Neon (docs/02-knowledge-base.md, section 9) come later in M3.

Every chunk lists the C1 sections it covers. D1 names its gold chunks by C1 id, so the same
gold set can score a C3 window or a C4 record that contains the right section.
"""

import hashlib
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from portfolio_agent.kb_check import (
    PORTFOLIO_DIR,
    Experience,
    Project,
    Skills,
    body_sections,
    check,
    check_file,
    split,
)

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

    @property
    def content(self) -> str:
        """What gets indexed and embedded."""
        return f"{self.header}\n\n{self.text}" if self.header else self.text

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


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
        sections = [
            (SECTION_IDS[name], re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip())
            for name, text in body_sections(body)
        ]
        docs.append(Doc(record, sections))
    return docs


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
        else:
            text = "\n\n".join(text for _, text in doc.sections)
            sids = tuple(sid for sid, _ in doc.sections)
            chunks.append(Chunk(f"{doc.record.id}#all", doc.record.id, sids, text))
    ids = [c.id for c in chunks]
    if len(ids) != len(set(ids)):
        raise IngestError(f"duplicate chunk ids in {strategy}")
    return chunks


def context_header(record: Project | Experience) -> str:
    lines = [f"{record.title.en} ({record.title.he})", f"Aliases: {', '.join(record.aliases)}"]
    if isinstance(record, Project):
        lines.append(f"Tech: {', '.join(record.tech)}")
    return "\n".join(lines)


def skill_slug(name: str) -> str:
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
        sid = skill_slug(s.name)
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

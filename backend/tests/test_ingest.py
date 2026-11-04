import re
from pathlib import Path

import pytest

from portfolio_agent.ingest import (
    OVERLAP,
    SECTION_IDS,
    STRATEGIES,
    TOKEN,
    WINDOW,
    IngestError,
    chunk,
    count_tokens,
    doc_sections,
    load,
    slug,
)

EDUCATION = """---
id: education
type: education
title: {{ en: "Education", he: "השכלה" }}
aliases: ["education", "השכלה"]
programs:
  - {{ institution: "A", program: "B", field: "C", start: "2023-09", end: "2025-07" }}
answers: ["Where did she study?"]
review: {{ approved: true, approved_on: 2026-11-04 }}
---
{body}"""


def test_text_before_the_first_heading_is_kept_as_body():
    assert doc_sections("Intro.\n\n## Context\nMore.") == [("body", "Intro."), ("context", "More.")]
    assert doc_sections("Only text, no headings.") == [("body", "Only text, no headings.")]


def test_free_headings_get_a_slug_and_empty_sections_are_dropped():
    body = "<!-- note -->\n## Courses & grades\nx\n## Empty\n<!-- only a note -->\n"
    assert doc_sections(body) == [("courses-grades", "x")]


@pytest.mark.parametrize("body", ["Studied in two programs.\n", "## Programs\nTwo programs.\n"])
def test_education_chunks_in_every_strategy_with_its_aliases(tmp_path, body):
    (tmp_path / "education.md").write_text(EDUCATION.format(body=body), encoding="utf-8")
    docs = load(tmp_path)
    for strategy in STRATEGIES:
        (c,) = chunk(docs, strategy)
        assert c.record_id == "education"
        assert c.aliases == "education, השכלה"
    c2 = chunk(docs, "C2")[0]
    assert c2.header == "Education (השכלה)\nAliases: education, השכלה"


def test_a_record_with_no_body_makes_no_chunks(tmp_path):
    (tmp_path / "education.md").write_text(EDUCATION.format(body=""), encoding="utf-8")
    docs = load(tmp_path)
    assert all(chunk(docs, s) == [] for s in STRATEGIES)

PROJECT = """---
id: demo
type: project
title: {{ en: "Demo pipeline", he: "צנרת דמו" }}
aliases: ["demo", "דמו"]
period: "2026"
role: "Sole engineer"
tech: [PostgreSQL, Kafka]
architecture:
  components: [{{ id: api, label: "API" }}]
code_allowed: false
depth: full
answers: ["What did she build?"]
review: {{ approved: true, approved_on: 2026-11-03, publication_check: own-project }}
---

## Problem
{problem}
## Why it was hard
hard <!-- a note to Sarah, not content -->
## My role
role
## Architecture
{architecture}
## Decisions and alternatives
decisions
## Results
results
"""

SKILLS = """---
id: skills
type: skills
title: { en: "Skills", he: "כישורים" }
skills:
  - { name: PostgreSQL, level: used, evidence: [demo] }
  - { name: "C#", level: studied, evidence: [demo] }
  - { name: "C++", level: listed }
review: { approved: true, approved_on: 2026-11-03 }
---
"""


def words(n: int, word: str) -> str:
    return " ".join(f"{word}{i}" for i in range(n))


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    (tmp_path / "demo.md").write_text(
        PROJECT.format(problem="problem", architecture="architecture"), encoding="utf-8"
    )
    (tmp_path / "skills.md").write_text(SKILLS, encoding="utf-8")
    return tmp_path


def test_c1_makes_one_chunk_per_heading_with_a_stable_id(kb):
    chunks = chunk(load(kb), "C1")
    records = [c for c in chunks if c.record_id == "demo"]
    assert [c.id for c in records] == [
        "demo#problem", "demo#why-hard", "demo#role", "demo#architecture",
        "demo#decisions", "demo#results",
    ]
    assert all(c.sections == (c.id.split("#")[1],) for c in records)
    assert all(c.header == "" for c in chunks)


def test_comments_are_not_content(kb):
    hard = next(c for c in chunk(load(kb), "C1") if c.id == "demo#why-hard")
    assert hard.text == "hard"


def test_c2_adds_the_record_name_aliases_and_tech_to_the_same_chunks(kb):
    c1, c2 = (chunk(load(kb), s) for s in ("C1", "C2"))
    assert [c.id for c in c1] == [c.id for c in c2]
    assert [c.text for c in c1] == [c.text for c in c2]
    decisions = next(c for c in c2 if c.id == "demo#decisions")
    assert decisions.header.splitlines() == [
        "Demo pipeline (צנרת דמו)", "Aliases: demo, דמו", "Tech: PostgreSQL, Kafka",
    ]
    assert decisions.content.startswith(decisions.header)
    assert decisions.content.endswith("decisions")


def test_c4_is_the_whole_record_in_one_chunk(kb):
    (record,) = [c for c in chunk(load(kb), "C4") if c.record_id == "demo"]
    assert record.id == "demo#all"
    assert record.sections == (
        "problem", "why-hard", "role", "architecture", "decisions", "results",
    )
    assert record.text.startswith("problem") and record.text.endswith("results")


def test_skills_are_one_chunk_each_in_every_strategy_and_say_the_level(kb):
    docs = load(kb)
    for strategy in STRATEGIES:
        skills = [c for c in chunk(docs, strategy) if c.record_id == "skills"]
        assert [c.id for c in skills] == ["skills#postgresql", "skills#csharp", "skills#cplusplus"]
    used, studied, listed = (c.text for c in chunk(docs, "C1") if c.record_id == "skills")
    assert used == "PostgreSQL. Level: used, Sarah used it in project work. Evidence: demo."
    assert "not in project work" in studied
    assert "Evidence" not in listed


def test_slugs():
    assert slug("RTL / i18n") == "rtl-i18n"
    assert slug(".NET Core") == "net-core"
    assert slug("C#") != slug("C++")


def test_c3_windows_have_a_fixed_size_and_overlap(tmp_path):
    (tmp_path / "demo.md").write_text(
        PROJECT.format(problem=words(400, "p"), architecture=words(400, "a")), encoding="utf-8"
    )
    windows = [c for c in chunk(load(tmp_path), "C3") if c.record_id == "demo"]
    assert [c.id for c in windows] == ["demo#w1", "demo#w2", "demo#w3", "demo#w4"]
    sizes = [count_tokens(c.text) for c in windows]
    assert all(s == WINDOW for s in sizes[:-1])
    assert sizes[-1] <= WINDOW
    for prev, nxt in zip(windows, windows[1:], strict=False):
        assert TOKEN.findall(prev.text)[-OVERLAP:] == TOKEN.findall(nxt.text)[:OVERLAP]


def test_c3_windows_cover_every_token_in_the_record(tmp_path):
    (tmp_path / "demo.md").write_text(
        PROJECT.format(problem=words(400, "p"), architecture=words(400, "a")), encoding="utf-8"
    )
    docs = load(tmp_path)
    (whole,) = [c for c in chunk(docs, "C4") if c.record_id == "demo"]
    windows = [c for c in chunk(docs, "C3") if c.record_id == "demo"]
    seen = {t for c in windows for t in TOKEN.findall(c.text)}
    assert seen == set(TOKEN.findall(whole.text))


def test_c3_credits_a_section_only_when_enough_of_it_is_in_the_window(tmp_path):
    # Problem is 400 tokens, so w1 holds tokens 0-299 of it and w2 starts at 250.
    # w2 holds 150 tokens of problem and the short sections after it, all of them whole.
    (tmp_path / "demo.md").write_text(
        PROJECT.format(problem=words(400, "p"), architecture=words(400, "a")), encoding="utf-8"
    )
    w1, w2, w3, w4 = (c for c in chunk(load(tmp_path), "C3") if c.record_id == "demo")
    assert w1.sections == ("problem",)
    assert w2.sections == ("problem", "why-hard", "role", "architecture")
    assert w3.sections == ("architecture",)
    # w4 is the tail of architecture and the two short sections at the end.
    assert w4.sections[-2:] == ("decisions", "results")


def test_c3_does_not_credit_a_few_words_at_the_edge_of_a_window(tmp_path):
    # 294 + 'hard' + 'role' puts architecture at token 296, so w1 ends with 4 of its 400
    # tokens. That is not enough.
    (tmp_path / "demo.md").write_text(
        PROJECT.format(problem=words(294, "p"), architecture=words(400, "a")), encoding="utf-8"
    )
    w1 = next(c for c in chunk(load(tmp_path), "C3") if c.id == "demo#w1")
    assert "a0" in w1.text
    assert "architecture" not in w1.sections


def test_every_chunk_of_a_record_carries_its_aliases(kb):
    for strategy in STRATEGIES:
        for c in chunk(load(kb), strategy):
            assert c.aliases == ("demo, דמו" if c.record_id == "demo" else "")


def test_content_hash_follows_what_is_indexed(kb):
    docs = load(kb)
    c1 = next(c for c in chunk(docs, "C1") if c.id == "demo#problem")
    c2 = next(c for c in chunk(docs, "C2") if c.id == "demo#problem")
    assert c1.content_hash == next(c for c in chunk(load(kb), "C1") if c.id == c1.id).content_hash
    assert c1.content_hash != c2.content_hash
    assert re.fullmatch(r"[0-9a-f]{64}", c1.content_hash)


def test_a_record_that_fails_kb_check_stops_ingestion(kb):
    text = (kb / "demo.md").read_text(encoding="utf-8").replace("approved: true", "approved: false")
    (kb / "demo.md").write_text(text, encoding="utf-8")
    with pytest.raises(IngestError, match="demo.md: review: .*approved must be true"):
        load(kb)


def test_unknown_strategy_fails(kb):
    with pytest.raises(ValueError, match="C5"):
        chunk(load(kb), "C5")


def test_every_heading_kb_check_allows_has_a_section_id():
    from portfolio_agent.kb_check import EXPERIENCE_SECTIONS, SECTIONS

    assert set(SECTIONS + EXPERIENCE_SECTIONS) == set(SECTION_IDS)


def test_the_real_knowledge_base_chunks_with_every_strategy():
    docs = load()
    for strategy in STRATEGIES:
        chunks = chunk(docs, strategy)
        assert chunks
        assert all(c.text.strip() for c in chunks)
    ids = {c.id for c in chunk(docs, "C1")}
    # Chunk ids that the spec already cites (docs/03, docs/04, docs/07).
    assert {
        "human-gated-translation#decisions",
        "human-gated-translation#architecture",
        "vast-data-bootcamp#role",
        "ainsof-capital#role",
    } <= ids

"""The Vercel build puts the knowledge base beside the code (bundle.py)."""

import pytest

from portfolio_agent.bundle import bundle_knowledge
from portfolio_agent.ingest import IngestError, load
from portfolio_agent.kb_check import REPO_PORTFOLIO_DIR


def test_the_records_are_copied_and_still_load(tmp_path):
    target = tmp_path / "knowledge"
    count = bundle_knowledge(REPO_PORTFOLIO_DIR, target)
    assert count == len(load(target)) > 0
    assert (target / "profile.md").exists()
    assert all(p.suffix == ".md" for p in target.rglob("*") if p.is_file())


def test_a_second_build_leaves_nothing_old_behind(tmp_path):
    target = tmp_path / "knowledge"
    target.mkdir()
    (target / "removed-record.md").write_text("old", encoding="utf-8")
    bundle_knowledge(REPO_PORTFOLIO_DIR, target)
    assert not (target / "removed-record.md").exists()


def test_an_empty_knowledge_base_fails_the_build(tmp_path):
    source = tmp_path / "portfolio"
    source.mkdir()
    with pytest.raises(IngestError, match="no records"):
        bundle_knowledge(source, tmp_path / "knowledge")
    assert not (tmp_path / "knowledge").exists()

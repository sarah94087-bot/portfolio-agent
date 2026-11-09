"""render_card without a database: what the card is built from, and what the tool refuses."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from portfolio_agent.ingest import load
from portfolio_agent.kb_check import Architecture, Project
from portfolio_agent.tools.cards import (
    RENDER_CARD,
    CardTool,
    describe,
    diagram_card,
    mermaid_text,
    project_card,
    to_mermaid,
)
from portfolio_agent.tools.registry import Registry

DOCS = load()
PROJECTS = [d.record for d in DOCS if isinstance(d.record, Project)]
BY_ID = {p.id: p for p in PROJECTS}
REGISTRY = Registry.of([RENDER_CARD])

ATTACKS = [
    '"]; click n0 "javascript:alert(1)"',
    "%%{init: {'securityLevel': 'loose'}}%%",
    '<img src=x onerror="alert(1)">',
    "<script>alert(1)</script>",
    "`**md**` | pipe | [x](y) {z} (w)",
    "line one\nn9[\"second\"]\r\n%% comment",
]


def context(retrieved=("this-agent",)):
    shown = []

    async def publish(card):
        shown.append(card)

    return SimpleNamespace(cards=CardTool.of(DOCS, publish), retrieved=set(retrieved)), shown


def call(ctx, record_id="this-agent", kind="project"):
    args = json.dumps({"record_id": record_id, "kind": kind})
    return asyncio.run(REGISTRY.acall("render_card", args, ctx))


def test_every_value_on_a_project_card_comes_from_the_record():
    for record in PROJECTS:
        data = project_card(record)["data"]
        assert data["title"] == {"en": record.title.en, "he": record.title.he}
        assert (data["role"], data["period"]) == (record.role, record.period)
        assert data["tech"] == record.tech
        assert [m["how_measured"] for m in data["metrics"]] == \
            [m.how_measured for m in record.metrics]
        assert data["source"] == f"{record.id}#all"


def test_a_card_has_no_field_for_code_or_for_the_employer():
    for record in PROJECTS:
        assert set(project_card(record)["data"]) == {
            "record_id", "title", "role", "period", "tech", "metrics", "source"}


def test_the_model_is_told_only_that_the_card_was_shown():
    ctx, shown = context()
    assert json.loads(call(ctx).model_view) == {"shown": True}
    assert shown == [project_card(BY_ID["this-agent"])]


def test_the_trace_says_what_the_card_was_built_from():
    ctx, _ = context()
    assert call(ctx, kind="diagram").trace_view["built_from"] == "frontmatter"
    record = BY_ID["this-agent"]
    ctx, _ = context()
    trace = call(ctx, kind="diagram").trace_view
    assert trace["components"] == len(record.architecture.components)
    assert trace["edges"] == len(record.architecture.edges)


def test_the_tool_is_not_offered_before_a_project_was_found():
    ctx, _ = context(retrieved=())
    assert REGISTRY.schemas(ctx) == []
    ctx, _ = context(retrieved=("skills", "faq"))  # records, but no project
    assert REGISTRY.schemas(ctx) == []
    ctx, _ = context()
    assert len(REGISTRY.schemas(ctx)) == 1


def test_the_tool_is_not_offered_where_cards_cannot_be_shown():
    assert REGISTRY.schemas(SimpleNamespace(cards=None, retrieved={"this-agent"})) == []


def test_the_schema_lists_only_projects():
    ctx, _ = context()
    params = REGISTRY.schemas(ctx)[0]["function"]["parameters"]
    assert params["properties"]["record_id"]["enum"] == sorted(BY_ID)
    assert params["properties"]["kind"]["enum"] == ["project", "diagram"]


def test_a_made_up_or_non_project_id_is_invalid():
    for bad in ("made-up", "ainsof-capital", "skills"):
        ctx, shown = context(retrieved=(bad,))
        result = call(ctx, record_id=bad)
        assert result.error == "invalid_args" and shown == []


def test_a_project_that_was_not_retrieved_gets_no_card():
    ctx, shown = context()
    result = call(ctx, record_id="git-mcp-server")
    assert result.error == "not_retrieved" and shown == []


def test_one_answer_shows_one_project():
    ctx, shown = context(retrieved=("this-agent", "git-mcp-server"))
    call(ctx)
    result = call(ctx, record_id="git-mcp-server", kind="diagram")
    assert result.error == "one_record" and len(shown) == 1


def test_a_repeated_card_is_not_shown_twice():
    ctx, shown = context()
    call(ctx)
    again = call(ctx)
    assert json.loads(again.model_view) == {"shown": True} and again.error is None
    assert again.trace_view["repeated"] is True and len(shown) == 1


def test_after_the_project_and_its_diagram_the_tool_is_gone():
    ctx, shown = context()
    call(ctx)
    assert len(REGISTRY.schemas(ctx)) == 1
    call(ctx, kind="diagram")
    assert REGISTRY.schemas(ctx) == [] and [c["kind"] for c in shown] == ["project", "diagram"]


def test_the_arguments_cannot_carry_text_for_the_card():
    ctx, shown = context()
    args = json.dumps({"record_id": "this-agent", "kind": "project", "title": "Invented"})
    result = asyncio.run(REGISTRY.acall("render_card", args, ctx))
    assert result.error == "invalid_args" and shown == []


@pytest.mark.parametrize("label", ATTACKS)
def test_a_label_cannot_leave_its_quotes(label):
    text = mermaid_text(label)
    assert not set(text) & set('"<>`\r\n') and "%%" not in text


def test_an_ordinary_label_is_left_as_it_was():
    label = "search_portfolio(query), R1: BM25 + trigrams [C4] 100% {x}"
    assert mermaid_text(label) == label


def architecture(label, edge_label=None):
    return Architecture.model_validate({
        "components": [{"id": 'a"]; x', "label": label}, {"id": "b", "label": "B"}],
        "edges": [{"from": 'a"]; x', "to": "b", "label": edge_label}],
    })


@pytest.mark.parametrize("label", ATTACKS)
def test_the_source_has_only_the_lines_the_code_writes(label):
    lines = to_mermaid(architecture(label, label)).split("\n")
    assert len(lines) == 4 and lines[0] == "flowchart TB"
    assert lines[1].startswith('  n0["') and lines[1].endswith('"]')
    assert lines[2] == '  n1["B"]'
    assert lines[3].startswith('  n0 -->|"') and lines[3].endswith('"| n1')
    assert lines[1].count('"') == 2 and lines[3].count('"') == 2


def test_a_record_id_never_reaches_mermaid():
    assert "x" not in to_mermaid(architecture("Label"))


def test_every_project_has_a_buildable_diagram_and_a_text_alternative():
    for record in PROJECTS:
        arch = record.architecture
        data = diagram_card(record)["data"]
        assert len(data["mermaid"].split("\n")) == 1 + len(arch.components) + len(arch.edges)
        assert len(data["text"]) == 1 + len(arch.edges)


def test_the_text_alternative_names_every_component_and_link():
    arch = BY_ID["this-agent"].architecture
    text = " ".join(describe(arch))
    assert all(c.label in text for c in arch.components)
    assert all(e.label in text for e in arch.edges if e.label)


def test_ingestion_refuses_a_broken_diagram():
    with pytest.raises(ValidationError, match="unknown component"):
        Architecture.model_validate({"components": [{"id": "a", "label": "A"}],
                                     "edges": [{"from": "a", "to": "ghost"}]})
    with pytest.raises(ValidationError, match="share an id"):
        Architecture.model_validate({"components": [{"id": "a", "label": "A"},
                                                    {"id": "a", "label": "B"}]})
    with pytest.raises(ValidationError, match="blank label"):
        Architecture.model_validate({"components": [{"id": "a", "label": "  "}]})

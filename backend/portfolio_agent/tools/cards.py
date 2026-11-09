"""render_card: a project card or an architecture diagram in the conversation (docs/07, section 3;
ADR-0018).

The model picks a record id and a kind, both from an enum, and is told only `{"shown": true}`.
Everything on the card is built here from the record's reviewed frontmatter, so no text from the
model can reach it (US-6.2). The same holds for the diagram's Mermaid source: node ids are made
here, and every label is escaped so that it stays a label whatever the record says.

Cost is why the tool is held back: a card takes one more model round, and a round sends the
whole prompt again. It is offered only once a project has been retrieved in this conversation,
and a turn shows one project, each kind once.
"""

import json
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent.kb_check import Architecture, Project
from portfolio_agent.tools.registry import Tool, ToolResult

Kind = Literal["project", "diagram"]
Publish = Callable[[dict[str, Any]], Awaitable[None]]

# What could end a quoted label, turn it into Markdown or look like a tag, swapped for a sign that
# reads the same. Not Mermaid's entity codes: with SVG labels it prints them as written.
_SWAPS = str.maketrans({'"': "'", "`": "'", "<": "‹", ">": "›"})
_DIRECTIVE = re.compile(r"%{2,}")  # Mermaid reads %%{...}%% anywhere in the source


def mermaid_text(label: str) -> str:
    """A label safe inside Mermaid's double quotes: one line, and nothing to parse."""
    printable = "".join(c if c.isprintable() else " " for c in label)
    return _DIRECTIVE.sub("%", " ".join(printable.split()).translate(_SWAPS))


def to_mermaid(architecture: Architecture) -> str:
    """The record's components and edges as a top-to-bottom flowchart. Top to bottom, because
    a phone is narrower than it is tall. Ids are n0, n1...: a record's ids never reach Mermaid."""
    ids = {c.id: f"n{i}" for i, c in enumerate(architecture.components)}
    lines = ["flowchart TB"]
    lines += [f'  {ids[c.id]}["{mermaid_text(c.label)}"]' for c in architecture.components]
    for e in architecture.edges:
        label = f'|"{mermaid_text(e.label)}"|' if e.label else ""
        lines.append(f"  {ids[e.from_]} -->{label} {ids[e.to]}")
    return "\n".join(lines)


def describe(architecture: Architecture) -> list[str]:
    """The diagram in words, one sentence a line, for screen readers and the text view."""
    labels = {c.id: c.label for c in architecture.components}
    lines = ["Components: " + "; ".join(labels.values()) + "."]
    for e in architecture.edges:
        how = f" ({e.label})" if e.label else ""
        lines.append(f"From {labels[e.from_]} to {labels[e.to]}{how}.")
    return lines


def _metric(metric: Any) -> dict[str, Any]:
    return {"label": metric.label, "before": metric.before, "after": metric.after,
            "value": metric.value, "how_measured": metric.how_measured}


def _base(record: Project) -> dict[str, Any]:
    return {"record_id": record.id, "title": {"en": record.title.en, "he": record.title.he}}


def project_card(record: Project) -> dict[str, Any]:
    return {"kind": "project", "data": {
        **_base(record), "role": record.role, "period": record.period, "tech": list(record.tech),
        "metrics": [_metric(m) for m in record.metrics], "source": f"{record.id}#all",
    }}


def diagram_card(record: Project) -> dict[str, Any]:
    return {"kind": "diagram", "data": {
        **_base(record), "mermaid": to_mermaid(record.architecture),
        "text": describe(record.architecture),
    }}


def card_sources(cards: Iterable[dict[str, Any]]) -> list[str]:
    """The chunks behind the cards, for the `sources` event."""
    return [c["data"]["source"] for c in cards if c["data"].get("source")]


@dataclass
class CardTool:
    """Set on PortfolioContext when this turn may show cards."""

    projects: dict[str, Project]
    publish: Publish
    shown: list[tuple[str, str]] = field(default_factory=list)  # (record id, kind), in order

    @classmethod
    def of(cls, docs: Iterable[Any], publish: Publish) -> "CardTool":
        return cls({d.record.id: d.record for d in docs if isinstance(d.record, Project)}, publish)

    def done(self) -> bool:
        return len(self.shown) >= 2  # one record, each kind once

    def offered(self, retrieved: set[str]) -> bool:
        return not self.done() and bool(retrieved & self.projects.keys())


class CardArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1)
    kind: Kind


def _refused(code: str, message: str) -> ToolResult:
    return ToolResult(json.dumps({"error": code, "message": message}), {"error": code}, error=code)


SHOWN = json.dumps({"shown": True})


async def render_card(args: CardArgs, ctx: Any) -> ToolResult:
    tool: CardTool | None = ctx.cards
    if tool is None:
        return _refused("unavailable", "Cards are not available here.")
    if args.record_id not in ctx.retrieved:
        return _refused("not_retrieved", "Show a card only for a project your search returned.")
    if tool.shown and tool.shown[0][0] != args.record_id:
        return _refused("one_record", "This answer already shows a different project.")
    trace = {"record_id": args.record_id, "kind": args.kind, "built_from": "frontmatter"}
    if (args.record_id, args.kind) in tool.shown:
        return ToolResult(SHOWN, {**trace, "repeated": True})
    record = tool.projects[args.record_id]
    if args.kind == "project":
        card = project_card(record)
        counts = {"tech": len(record.tech), "metrics": len(record.metrics)}
    else:
        card = diagram_card(record)
        counts = {"components": len(record.architecture.components),
                  "edges": len(record.architecture.edges)}
    tool.shown.append((args.record_id, args.kind))
    await tool.publish(card)
    return ToolResult(SHOWN, {**trace, **counts})


RENDER_CARD = Tool(
    name="render_card",
    description=(
        "Show a visual card for a project. Use when one project is the focus of the answer. "
        "kind=project shows its role, stack and metrics; kind=diagram its architecture."
    ),
    params=CardArgs,
    handler=render_card,
    schema_extra=lambda ctx: {"record_id": {"enum": sorted(ctx.cards.projects)}},
    offered=lambda ctx: ctx.cards is not None and ctx.cards.offered(ctx.retrieved),
)

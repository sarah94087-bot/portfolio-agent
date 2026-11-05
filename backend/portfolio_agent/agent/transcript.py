"""What the visitor saw, kept for the database and for a replay.

The raw model text is never stored: it can hold invalid citations, a phone number the guard
replaced, a round that a backup model answered over, or the canary. The transcript records the
events instead, applies the same replacements the UI applies (a `restart` or `guard` step cuts
back to `replace_from` characters and `citations_from` citations), and serializes the result
with valid citations as [[chunk_id]]. Fed back through the citation filter with those ids
allowed, it gives the same token and citation events, which is how a resent message is
answered without calling the model again (US-10.5).
"""

from dataclasses import dataclass, field
from typing import Any

from portfolio_agent.agent.citations import CitationFilter
from portfolio_agent.agent.emit import Emit


@dataclass
class Transcript:
    parts: list[tuple[str, str]] = field(default_factory=list)  # ("t", text) | ("c", chunk_id)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: str, data: dict[str, Any]) -> None:
        if event == "token":
            if self.parts and self.parts[-1][0] == "t":
                self.parts[-1] = ("t", self.parts[-1][1] + data["text"])
            else:
                self.parts.append(("t", data["text"]))
        elif event == "citation":
            self.parts.append(("c", data["chunk_id"]))
        elif event == "step":
            self.steps.append(data)
            summary = data.get("summary") or {}
            if data.get("status") == "restart" or data.get("kind") == "guard":
                self._cut(summary.get("replace_from", 0), summary.get("citations_from", 0))

    def _cut(self, chars: int, citations: int) -> None:
        kept: list[tuple[str, str]] = []
        for kind, value in self.parts:
            if kind == "t":
                if chars <= 0:
                    continue
                kept.append((kind, value[:chars]))
                chars -= len(value)
            elif citations > 0:
                kept.append((kind, value))
                citations -= 1
        self.parts = kept

    @property
    def text(self) -> str:
        """What the visitor reads, without citation markers."""
        return "".join(v for k, v in self.parts if k == "t")

    @property
    def content(self) -> str:
        """For the database: the text with valid citations as [[chunk_id]]."""
        return "".join(v if k == "t" else f"[[{v}]]" for k, v in self.parts)

    @property
    def cited(self) -> list[str]:
        return list(dict.fromkeys(v for k, v in self.parts if k == "c"))


async def replay(content: str, emit: Emit) -> None:
    """The token and citation events of a stored answer, numbered as they were."""
    cited = frozenset(_markers(content))
    f = CitationFilter()
    await f.feed(content, cited, emit)
    await f.flush(emit)


def _markers(content: str) -> list[str]:
    out, rest = [], content
    while "[[" in rest:
        start = rest.index("[[") + 2
        end = rest.find("]]", start)
        if end == -1:
            break
        out.append(rest[start:end])
        rest = rest[end + 2:]
    return out

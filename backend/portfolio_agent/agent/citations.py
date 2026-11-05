"""Citations checked while the answer streams (docs/05-architecture.md, section 4).

The model marks a citation as `[[chunk_id]]`. Text flows to the browser as it arrives, except
from `[[` until `]]`: that much is held, and the id is checked against the chunks retrieved in
this conversation. A valid id becomes a `citation` event with the source's number, in place of
the marker. An invalid one is dropped and recorded, so no answer ever shows a source that was
not retrieved (citation validity, 100%, docs/03-evaluation-methodology.md).

A marker can be split across tokens (`[[postgres-` then `rls#all]]`), or even `[` and `[`.
The filter works on a buffer, never on single tokens, and the property tests split every
sample at every point to show that the output does not depend on where the splits fall.

What is not a citation passes through as text: `[[` followed by a character no id uses, or a
marker longer than any id. One marker may hold several ids, `[[a#all, b#all]]`, since models
write them that way.
"""

import re
from dataclasses import dataclass, field

from portfolio_agent.agent.emit import Emit

OPEN, CLOSE = "[[", "]]"
MAX_MARKER = 200  # longer than this between [[ and ]] is text, not a citation
ID_CHARS = re.compile(r"[\w#.\-,; ]*")  # what may appear inside a marker
SEPARATORS = re.compile(r"[,;]\s*|\s+")


@dataclass
class CitationFilter:
    numbers: dict[str, int] = field(default_factory=dict)  # chunk id -> source number, 1-based
    dropped: list[str] = field(default_factory=list)  # for the trace and Langfuse
    _buf: str = ""

    async def feed(self, text: str, allowed: frozenset[str], emit: Emit) -> None:
        self._buf += text
        while self._buf:
            start = self._buf.find(OPEN)
            if start == -1:
                # A trailing "[" may be the first half of "[[", so it waits for the next token.
                keep = 1 if self._buf.endswith("[") else 0
                await self._text(self._buf[: len(self._buf) - keep], emit)
                self._buf = self._buf[len(self._buf) - keep:]
                return
            await self._text(self._buf[:start], emit)
            self._buf = self._buf[start:]
            inner_end = self._buf.find(CLOSE, len(OPEN))
            inner = self._buf[len(OPEN): inner_end if inner_end != -1 else None]
            # While open, a last "]" may be the first half of "]]".
            seen = inner if inner_end != -1 else inner.removesuffix("]")
            if not ID_CHARS.fullmatch(seen) or len(seen) > MAX_MARKER:
                # Not a citation here. Only the first "[" goes out as text, because the second
                # may open a real marker: "[[[a#all]]" is "[" and a citation.
                await self._text("[", emit)
                self._buf = self._buf[1:]
                continue
            if inner_end == -1:
                return  # an open marker: wait for its "]]"
            await self._cite(inner, allowed, emit)
            self._buf = self._buf[inner_end + len(CLOSE):]

    async def flush(self, emit: Emit) -> None:
        """End of the answer. An open marker is a citation cut short, so it is dropped."""
        if self._buf.startswith(OPEN):
            self.dropped.append(self._buf[len(OPEN):].strip() or "<empty>")
        else:
            await self._text(self._buf, emit)
        self._buf = ""

    def checkpoint(self) -> tuple[dict[str, int], int, str]:
        return dict(self.numbers), len(self.dropped), self._buf

    def rollback(self, state: tuple[dict[str, int], int, str]) -> None:
        """Back to a checkpoint, when a round is answered over by another model. Numbers given
        in the discarded text are taken back, so the sources stay numbered 1, 2, 3."""
        numbers, dropped, buf = state
        self.numbers = dict(numbers)
        del self.dropped[dropped:]
        self._buf = buf

    async def _cite(self, inner: str, allowed: frozenset[str], emit: Emit) -> None:
        ids = [i for i in SEPARATORS.split(inner.strip()) if i]
        if not ids:
            self.dropped.append("<empty>")
        for cid in ids:
            if cid not in allowed:
                self.dropped.append(cid)
                continue
            if cid not in self.numbers:
                self.numbers[cid] = len(self.numbers) + 1
            await emit("citation", {"chunk_id": cid, "index": self.numbers[cid]})

    @staticmethod
    async def _text(text: str, emit: Emit) -> None:
        if text:
            await emit("token", {"text": text})

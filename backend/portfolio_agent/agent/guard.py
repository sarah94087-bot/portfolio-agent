"""The output guard: checks on the raw model text before anything reaches the browser
(docs/06-agent-design.md, section 6). It wraps the citation filter, so it sees the text first.

- Canary. The system prompt holds a random string injected at runtime. If it shows up in the
  output, the prompt leaked: the answer stops, the visitor sees a safe message instead, and the
  turn is marked for a severe event (docs/10-ops-and-costs.md: alert at once). The string is
  never sent, even in part, because the guard holds back a window as long as the canary.
- Private information. A phone number or an email in the answer is replaced with a pointer to
  the downloadable CV. Her phone is not in the knowledge base (docs/02, section 8), so this is
  the second line, for whatever the model makes up or copies from a visitor.
- Language. At the end, whether the answer is Hebrew, English or mixed. Recorded only (a T2
  metric), never enforced.

Text is held only as long as needed: up to the last space that is at least WINDOW characters
from the end, and never inside something that may still turn out to be a phone or an email.
That is a few tokens of delay, like the citation filter. The property tests split every
sample at every point, so a canary or a phone split across tokens is still caught.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from portfolio_agent.agent.emit import Emit

# ASCII only: \w would also take a Hebrew prefix such as "ל-" into the address.
EMAIL = r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
# Israeli numbers (050-1234567, 03 123 4567, +972 50 123 4567) and other international ones.
PHONE = (
    r"(?<![\w+])(?:\+972[-\s]?|0)(?:5\d|[23489]|7\d)[-\s]?\d{3}[-\s]?\d{4}(?!\w)"
    r"|(?<![\w+])\+\d{1,3}[-\s]?\(?\d{1,4}\)?(?:[-\s]?\d{2,4}){2,4}(?!\w)"
)
PRIVATE = re.compile(f"{EMAIL}|{PHONE}")
WINDOW = 40  # longer than any phone or email form above that could still be growing
HEBREW = re.compile(r"[֐-׿]")
LATIN = re.compile(r"[A-Za-z]")

SAFE = {
    "he": "אני לא יכול לענות על זה. אפשר לשאול על הניסיון של שרה, הפרויקטים שלה או הכישורים שלה.",
    "en": "I can't answer that. Feel free to ask about Sarah's experience, projects or skills.",
}
CV_POINTER = {
    "he": "(פרטי הקשר נמצאים בקורות החיים להורדה)",
    "en": "(contact details are in the downloadable CV)",
}


def language(text: str) -> str:
    he, la = len(HEBREW.findall(text)), len(LATIN.findall(text))
    if not he and not la:
        return "none"
    ratio = he / (he + la)
    return "he" if ratio >= 0.6 else "en" if ratio <= 0.2 else "mixed"


@dataclass
class OutputGuard:
    inner: Any  # the citation filter, or anything with feed, flush, checkpoint and rollback
    canary: str
    blocked: str | None = None  # "canary" once the leak is caught
    redacted: int = 0  # how many phones and emails were replaced
    _buf: str = ""
    _tail: str = ""  # the last len(canary) - 1 released characters, for a canary across a cut
    _seen: list[str] = field(default_factory=list)  # all released text, for the language
    _allowed: frozenset[str] = frozenset()  # the chunks allowed at the last feed, for flush
    shown_text: str = ""  # the safe message, once blocked

    @property
    def numbers(self) -> dict[str, int]:
        return getattr(self.inner, "numbers", {})

    @property
    def dropped(self) -> list[str]:
        return getattr(self.inner, "dropped", [])

    @property
    def language(self) -> str:
        return language("".join(self._seen))

    async def feed(self, text: str, allowed: frozenset[str], emit: Emit) -> None:
        if self.blocked:
            return
        self._allowed = allowed
        self._buf += text
        if self.canary and self.canary in self._tail + self._buf:
            await self._block(emit)
            return
        cut = self._cut_point()
        if cut:
            await self._release(self._buf[:cut], allowed, emit)
            self._buf = self._buf[cut:]

    async def flush(self, emit: Emit) -> None:
        if not self.blocked and self._buf:
            await self._release(self._buf, self._allowed, emit)
        self._buf = ""
        if not self.blocked:
            await self.inner.flush(emit)

    def checkpoint(self) -> Any:
        return self.inner.checkpoint(), self._buf, self._tail, len(self._seen), self.redacted

    def rollback(self, state: Any) -> None:
        inner, self._buf, self._tail, seen, self.redacted = state
        self.inner.rollback(inner)
        del self._seen[seen:]

    def _cut_point(self) -> int:
        """Where the held text may be released: after the last whitespace that leaves WINDOW
        characters behind (and the canary's length), and not inside a private match."""
        hold = max(WINDOW, len(self.canary))
        limit = len(self._buf) - hold
        if limit <= 0:
            return 0
        cut = 0
        for m in re.finditer(r"\s", self._buf[:limit]):
            cut = m.end()
        for m in PRIVATE.finditer(self._buf):
            if m.start() < cut < m.end():
                cut = m.start()
        return cut

    async def _release(self, text: str, allowed: frozenset[str], emit: Emit) -> None:
        lang = "he" if HEBREW.search("".join(self._seen) + text) else "en"

        def pointer(m: re.Match[str]) -> str:
            self.redacted += 1
            return CV_POINTER[lang]

        clean = PRIVATE.sub(pointer, text)
        n = len(self.canary) - 1
        self._tail = (self._tail + text)[-n:] if n > 0 else ""
        self._seen.append(clean)
        await self.inner.feed(clean, allowed, emit)

    async def _block(self, emit: Emit) -> None:
        self.blocked = "canary"
        lang = "he" if HEBREW.search("".join(self._seen) + self._buf) else "en"
        self._buf = ""
        await emit("step", {"step_id": "guard", "kind": "guard", "status": "end",
                            "name": "output_guard",
                            "summary": {"blocked": "canary", "replace_from": 0,
                                        "citations_from": 0}})
        self.shown_text = SAFE[lang]
        await emit("token", {"text": SAFE[lang]})

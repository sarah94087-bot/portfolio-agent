"""The agent's search query before retrieval (docs/04-retrieval-design.md, axis C; ADR-0013).

Q1: the query is what the agent wrote as search_portfolio's `query`. Stage 3 showed that the
model often adds Sarah's name ("Sarah Halevy Docker"). Every record is about her, so the name
carries no information, but it is not free: the FAQ, written in the third person, repeats it,
and BM25 and trigrams pull it to the top. So the name is removed in code, not asked of the
model in the prompt, like the other rules that matter (docs/06-agent-design.md, section 2).

The names come from the profile record (`name.en`, `name.he`), each word on its own, so
"Sarah", "Halevy" and "Sarah's" all go. A query that is only the name is kept as it is.
"""

import re
from collections.abc import Iterable, Sequence

# A Hebrew word can carry one attached prefix letter: ו ה ב ל מ ש כ (לשרה, ושרה).
_HE_PREFIX = "[והבלמשכ]?"
_HEBREW = re.compile(r"[֐-׿]")


def owner_names(records: Iterable[object]) -> tuple[str, ...]:
    """Every word of the profile record's name, in English and Hebrew."""
    for record in records:
        if getattr(record, "type", None) == "profile":
            name = record.name
            words = [w for part in (name.en, name.he) for w in str(part).split()]
            return tuple(dict.fromkeys(words))
    raise ValueError("no profile record, so the owner's name is unknown")


def name_pattern(names: Sequence[str]) -> re.Pattern[str]:
    alternatives = []
    for word in sorted(names, key=len, reverse=True):
        escaped = re.escape(word)
        if _HEBREW.search(word):
            alternatives.append(rf"(?<!\w){_HE_PREFIX}{escaped}(?!\w)")
        else:
            alternatives.append(rf"\b{escaped}(?:['’]s)?\b")
    return re.compile("|".join(alternatives), re.IGNORECASE)


def strip_names(query: str, pattern: re.Pattern[str]) -> str:
    """The query without the owner's name; the query itself if nothing else is left."""
    stripped = re.sub(r"\s+", " ", pattern.sub(" ", query)).strip(" ,.;:'’\"")
    return stripped or query

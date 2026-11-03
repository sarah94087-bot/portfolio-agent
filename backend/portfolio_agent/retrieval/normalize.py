"""Text normalization for search, applied the same way at ingestion and at query time.

docs/04-retrieval-design.md, section 6: Postgres has no Hebrew dictionary, so search uses the
`simple` configuration and trigrams. For those to match, final letters become regular letters
and niqqud and cantillation marks are removed. Prefixes (ו, ה, ב...) stay: trigrams match
them partly, and Q1 sends English queries anyway.
"""

import unicodedata

FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def is_hebrew_mark(ch: str) -> bool:
    return "֑" <= ch <= "ׇ" and unicodedata.combining(ch) > 0


def normalize(text: str) -> str:
    # NFKD splits presentation forms such as שׁ (U+FB2A) into a letter and its mark.
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not is_hebrew_mark(ch))
    return unicodedata.normalize("NFC", stripped).translate(FINALS).lower()

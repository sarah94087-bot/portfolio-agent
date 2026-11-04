"""R4: R3, then a language model reorders its first candidates (docs/04-retrieval-design.md,
axis B). Stage 4 decides whether it is worth its time and quota.

This module holds the parts that do not call a model: what the model reads, and how its answer
becomes an order. The call itself lives with the experiment (evals/retrieval/run_stage4.py),
until stage 4 decides whether R4 goes into search_portfolio.

On C4 a candidate is a whole record, and 20 of them are about the whole knowledge base, about
8,000 tokens per call. So stage 4 reorders R3's first 10, each cut to its first 150 tokens
(the experiment report, stage 4, says why).
"""

from collections.abc import Sequence

from portfolio_agent.ingest import TOKEN
from portfolio_agent.retrieval.lexical import Hit

RERANK_CANDIDATES = 10
CANDIDATE_TOKENS = 150


def truncate(text: str, max_tokens: int = CANDIDATE_TOKENS) -> str:
    """The text up to its max_tokens-th token (ingest.TOKEN), with an ellipsis if it was cut."""
    for i, match in enumerate(TOKEN.finditer(text)):
        if i == max_tokens:
            return text[: match.start()].rstrip() + " …"
    return text


def candidates_block(hits: Sequence[Hit], max_tokens: int = CANDIDATE_TOKENS) -> str:
    """The candidates as the model reads them: the chunk id, then the start of its text."""
    return "\n\n".join(f"[{h.id}]\n{truncate(h.text, max_tokens)}" for h in hits)


def apply_order(hits: Sequence[Hit], ranking: Sequence[str]) -> list[Hit]:
    """The hits in the model's order. Unknown or repeated ids are ignored, and any hit the model
    left out keeps its R3 place after the ones it ranked, so a bad answer cannot lose a hit."""
    by_id = {h.id: h for h in hits}
    seen: list[str] = []
    for cid in ranking:
        if cid in by_id and cid not in seen:
            seen.append(cid)
    rest = [h.id for h in hits if h.id not in seen]
    return [
        Hit(h.id, h.record_id, h.sections, h.text, {**h.scores, "rerank": rank})
        for rank, h in enumerate((by_id[c] for c in seen + rest), start=1)
    ]

"""R4: R3, then a language model reorders its first candidates (docs/04-retrieval-design.md,
axis B), adopted in ADR-0014. The model, the prompt and the cut below are what stage 4 measured;
changing one means measuring again, so the model is pinned here and not read from GROQ_MODEL.

A failure never fails the search: the hits keep R3's order, and the trace says why.

On C4 a candidate is a whole record, and 20 of them are about the whole knowledge base, about
8,000 tokens per call. So stage 4 reorders R3's first 10, each cut to its first 150 tokens
(the experiment report, stage 4, says why).
"""

import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from portfolio_agent.ingest import TOKEN
from portfolio_agent.providers.openai_compat import ProviderError, classify
from portfolio_agent.providers.router import DAY_FALLBACK, GROQ_BASE
from portfolio_agent.retrieval.lexical import Hit

RERANK_MODEL = "openai/gpt-oss-120b"
RERANK_CANDIDATES = 10
CANDIDATE_TOKENS = 150
TIMEOUT = 5.0  # seconds; a call took 2.0 at p95 (stage 4), and the visitor is waiting
# Groq answers 400 when the model's tool call fails its own validation, about 1 call in 90
# (stage 4, run 2). It is tried once more.
BAD_REQUEST_TRIES = 2

SYSTEM = (
    "You rank search results for an assistant that answers questions about Sarah's work. "
    "Order the candidate passages from the most to the least useful for answering the "
    "visitor's question. Rank every candidate id you are given, and only those."
)


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


def rank_tool(ids: Sequence[str]) -> dict:
    return {"type": "function", "function": {
        "name": "rank_passages",
        "description": "Give the candidate ids, best first.",
        "parameters": {"type": "object", "required": ["ranking"], "properties": {
            "ranking": {"type": "array", "items": {"type": "string", "enum": list(ids)},
                        "minItems": 1, "maxItems": len(ids)},
        }},
    }}


def prompt(question: str, query: str, hits: Sequence[Hit]) -> str:
    return (f"Visitor's question: {question}\nSearch query: {query}\n\n"
            f"Candidates:\n\n{candidates_block(hits)}")


@dataclass(frozen=True)
class Ranking:
    ids: list[str]  # best first; empty when the model gave no usable answer
    tokens: int = 0


class Ranker(Protocol):
    name: str

    def rank(self, question: str, query: str, hits: Sequence[Hit]) -> Ranking: ...


class Quota(Protocol):  # guards/quotas.py, ProviderQuota
    def closed(self) -> dict[str, tuple[float, str]]: ...

    def close(self, model: str, until: float) -> None: ...

    def spend(self, model: str, tokens: int) -> None: ...


def _ids(data: dict[str, Any]) -> list[str]:
    try:
        calls = data["choices"][0]["message"].get("tool_calls") or []
        ranking = json.loads(calls[0]["function"]["arguments"])["ranking"] if calls else []
    except (ValueError, KeyError, IndexError, TypeError):
        return []
    return [str(c) for c in ranking] if isinstance(ranking, list) else []


@dataclass
class GroqRanker:
    client: httpx.Client
    api_key: str
    model: str = RERANK_MODEL

    @property
    def name(self) -> str:
        return f"groq/{self.model}"  # the name the router and the quota know it by

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self.client.post(f"{GROQ_BASE}/chat/completions", json=body, timeout=TIMEOUT,
                                 headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.TimeoutException as e:
            raise ProviderError("unavailable", f"timeout: {type(e).__name__}") from e
        except httpx.TransportError as e:
            raise ProviderError("unavailable", f"{type(e).__name__}: {e}") from e
        if r.status_code != 200:
            raise classify(r.status_code, r.text, r.headers)
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError("unavailable", "the response was not JSON") from e

    def rank(self, question: str, query: str, hits: Sequence[Hit]) -> Ranking:
        body = {
            "model": self.model, "tools": [rank_tool([h.id for h in hits])],
            "tool_choice": {"type": "function", "function": {"name": "rank_passages"}},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt(question, query, hits)}],
        }
        for attempt in range(1, BAD_REQUEST_TRIES + 1):
            try:
                data = self._post(body)
                break
            except ProviderError as e:
                if e.kind != "bad_request" or attempt == BAD_REQUEST_TRIES:
                    raise
        return Ranking(_ids(data), (data.get("usage") or {}).get("total_tokens", 0))


def from_env(client: httpx.Client, env: dict[str, str] | None = None) -> GroqRanker | None:
    """None without a key: the search then stays R3."""
    key = (dict(os.environ) if env is None else env).get("GROQ_API_KEY")
    return GroqRanker(client, key) if key else None


@dataclass(frozen=True)
class Outcome:
    hits: list[Hit]
    tokens: int = 0
    fallback: str | None = None  # why the hits kept R3's order: rate_day, unavailable, empty, ...


def rerank(hits: Sequence[Hit], question: str, query: str, ranker: Ranker, quota: Quota,
           wall: Callable[[], float] = time.time) -> Outcome:
    """R3's first candidates in the model's order, then the rest. Stage 4 measured one model,
    so when that model is closed for the day the hits keep R3's order (ADR-0014). The tokens
    count against the same per-model quota as the answers."""
    if ranker.name in quota.closed():
        return Outcome(list(hits), fallback="rate_day")
    head, tail = list(hits[:RERANK_CANDIDATES]), list(hits[RERANK_CANDIDATES:])
    try:
        ranking = ranker.rank(question, query, head)
    except ProviderError as e:
        if e.kind == "rate_day":
            quota.close(ranker.name, wall() + (e.retry_after or DAY_FALLBACK))
        return Outcome(list(hits), fallback=e.kind)
    quota.spend(ranker.name, ranking.tokens)
    if not ranking.ids:
        return Outcome(list(hits), ranking.tokens, "empty")
    return Outcome(apply_order(head, ranking.ids) + tail, ranking.tokens)

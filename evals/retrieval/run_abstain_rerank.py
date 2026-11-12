"""Stage 5b: can a relevance grade from the reranker tell that the portfolio has no answer?

Stage 5 (run_abstain.py, ADR-0023) found that no score of the search itself separates the
questions the portfolio answers from the ones it does not: they are all about Sarah, so they
all sit close to her records. Yael Zucker's next step: make the scoring better, and refuse
when the best score is below a cut. Here the reranker's model (R4, ADR-0014) grades each of
R3's first 10 candidates, on whether it holds what the question asks for, not on whether it is
on the same subject:

    3  answers the question
    2  answers part of it
    1  about the same subject, but without what the question asks
    0  unrelated

The signal is the best grade among the 10. It is compared as in stage 5: positives are the D1
questions that expect an answer, negatives `refuse_no_info` and `redirect_off_topic`; the
question as written (Q0), follow-ups left out; AUC on dev and on test; the cut that keeps
every dev positive, then the same cut on test. Set before the first run: the cut that would be
used is "best grade >= 2", and ADR-0023 reopens only if test AUC >= 0.85.

The candidates and their text are what R4 sees on the site (rerank.py: 10, 150 tokens each).
The site does not call this: it only measures. Each grading is saved as it comes, in
evals/datasets/rerank/, so a run that hits the token ceiling resumes the next day (the Groq
quota is 200,000 tokens a day, shared with the site).

Runs in CI (.github/workflows/groq.yml, job abstain), since the home network intercepts TLS to
Groq. Locally, with a key and from another network:
    DATABASE_URL=... EMBEDDING_MODEL_DIR=... GROQ_API_KEY_EVALS=... GROQ_MODEL=... \
        python -m retrieval.run_abstain_rerank
"""

import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import psycopg
from portfolio_agent import migrate
from portfolio_agent.ingest import chunk, load, upsert
from portfolio_agent.retrieval import embedder as e5
from portfolio_agent.retrieval import hybrid, vector
from portfolio_agent.retrieval.lexical import Hit
from portfolio_agent.retrieval.rerank import (
    BAD_REQUEST_TRIES,
    CANDIDATE_TOKENS,
    RERANK_CANDIDATES,
    candidates_block,
)

from retrieval.embedders import env, post
from retrieval.harness import D1Item, load_d1, write_results
from retrieval.rewrite import GROQ_URL
from retrieval.run_abstain import at_cut, auc, cut_keeping_all
from retrieval.run_stage1 import D1_PATH

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "evals" / "datasets" / "rerank" / "d1-abstain-grades.json"
STRATEGY = "C4"
TABLE = "abstain_rerank_chunks"
MAX_TOKENS = int(os.environ.get("ABSTAIN_MAX_TOKENS", "60000"))  # per invocation
FIXED_CUT = 2  # set before the first run: answer only when some candidate answers at least part
GRADES = (0, 1, 2, 3)

SYSTEM = (
    "You grade search results for an assistant that answers questions about Sarah's work. "
    "For each candidate passage, grade whether it contains what the visitor's question asks "
    "for: 3 = it answers the question, 2 = it answers part of it, 1 = it is about the same "
    "subject but does not contain what is asked, 0 = it is unrelated. A passage about the "
    "right project or topic that lacks the specific fact asked for is a 1. Grade every "
    "candidate id you are given, and only those."
)

# (question, candidates) -> (grades by id, tokens, ms spent waiting on 429)
Grader = Callable[[str, Sequence[Hit]], tuple[dict[str, int], int, int]]


def grade_tool(ids: Sequence[str]) -> dict:
    return {"type": "function", "function": {
        "name": "grade_passages",
        "description": "Give every candidate id with its grade.",
        "parameters": {"type": "object", "required": ["grades"], "properties": {
            "grades": {"type": "array", "minItems": 1, "maxItems": len(ids), "items": {
                "type": "object", "required": ["id", "grade"], "properties": {
                    "id": {"type": "string", "enum": list(ids)},
                    "grade": {"type": "integer", "enum": list(GRADES)},
                },
            }},
        }},
    }}


def grade_prompt(question: str, hits: Sequence[Hit]) -> str:
    return (f"Visitor's question: {question}\n\n"
            f"Candidates:\n\n{candidates_block(hits, CANDIDATE_TOKENS)}")


def parse_grades(data: dict, ids: Sequence[str]) -> dict[str, int]:
    """The grades of the given ids. Unknown ids, bad grades and repeats (the first one counts)
    are dropped; an answer with no tool call gives nothing."""
    try:
        calls = data["choices"][0]["message"].get("tool_calls") or []
        raw = json.loads(calls[0]["function"]["arguments"])["grades"] if calls else []
    except (ValueError, KeyError, IndexError, TypeError):
        return {}
    out: dict[str, int] = {}
    for g in raw if isinstance(raw, list) else []:
        if not isinstance(g, dict):
            continue
        cid, grade = g.get("id"), g.get("grade")
        is_grade = isinstance(grade, int) and not isinstance(grade, bool) and grade in GRADES
        if cid in ids and cid not in out and is_grade:
            out[cid] = grade
    return out


def best_grade(grades: dict[str, int]) -> int | None:
    """The signal: the best grade, None when the model graded nothing (a fallback)."""
    return max(grades.values()) if grades else None


def groq_grader(client: httpx.Client) -> Grader:
    headers = {"Authorization": f"Bearer {env('GROQ_API_KEY_EVALS')}"}
    model = env("GROQ_MODEL")

    def grade(question: str, hits: Sequence[Hit]) -> tuple[dict[str, int], int, int]:
        ids = [h.id for h in hits]
        body = {
            "model": model, "tools": [grade_tool(ids)],
            "tool_choice": {"type": "function", "function": {"name": "grade_passages"}},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": grade_prompt(question, hits)}],
        }
        waits: list[float] = []
        for attempt in range(BAD_REQUEST_TRIES):
            try:
                data = post(client, GROQ_URL, waits=waits, headers=headers, json=body).json()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 400 or attempt == BAD_REQUEST_TRIES - 1:
                    raise
        return (parse_grades(data, ids), (data.get("usage") or {}).get("total_tokens", 0),
                round(sum(waits) * 1000))
    return grade


def measure(
    db_url: str, items: Sequence[D1Item], embed_query: Callable[[str], list[float]],
    embed_passages: Callable[[Sequence[str]], list[list[float]]], grader: Grader,
    saved_path: Path = SAVED, model: str = "", max_tokens: int = MAX_TOKENS,
) -> dict:
    """Saved grades are reused while R3 gives the same candidates; missing ones are asked for
    until max_tokens is spent. Returns the rows, and which questions are still missing."""
    if saved_path.exists():
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
    else:
        saved = {"model": model, "date": time.strftime("%Y-%m-%d"), "system": SYSTEM,
                 "candidates": RERANK_CANDIDATES, "candidate_tokens": CANDIDATE_TOKENS,
                 "tokens": 0, "calls": 0, "grades": {}}
    migrate.run(db_url)
    chunks = chunk(load(), STRATEGY)
    rows, missing, spent = [], [], 0
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"drop table if exists {TABLE}")
        conn.execute(f"create temp table {TABLE} (like chunks including all)")
        try:
            upsert(conn, chunks, TABLE)
            vector.add_embedding_column(conn, TABLE, len(embed_query("dimension")))
            vecs = embed_passages([c.content for c in chunks])
            vector.store_embeddings(conn, TABLE, {c.id: v for c, v in zip(chunks, vecs,
                                                                         strict=True)})
            for item in items:
                if item.history:
                    continue
                hits = hybrid.search(conn, item.question, embed_query(item.question),
                                     RERANK_CANDIDATES, TABLE)
                ids = [h.id for h in hits]
                got = saved["grades"].get(item.id)
                if got is None or got["candidates"] != ids:
                    if spent >= max_tokens:
                        missing.append(item.id)
                        continue
                    start = time.perf_counter()
                    grades, used, wait_ms = grader(item.question, hits)
                    spent += used
                    saved["tokens"] += used
                    saved["calls"] += 1
                    got = {"candidates": ids, "grades": grades, "tokens": used,
                           "ms": round((time.perf_counter() - start) * 1000) - wait_ms,
                           "wait_ms": wait_ms}
                    saved["grades"][item.id] = got
                    saved_path.parent.mkdir(parents=True, exist_ok=True)
                    saved_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2)
                                          + "\n", encoding="utf-8")
                gold = {g.split("#")[0] for g in item.gold_chunks}
                rows.append({
                    "id": item.id, "split": item.split, "lang": item.lang,
                    "category": item.category, "answerable": item.expected_behavior == "answer",
                    "grade": best_grade(got["grades"]),
                    "gold_in_candidates": bool(gold & {h.record_id for h in hits}),
                    "top_graded": max(got["grades"], key=got["grades"].get, default=None),
                })
        finally:
            conn.execute(f"drop table {TABLE}")
    return {"rows": rows, "missing": missing, "spent_now": spent,
            "tokens": saved["tokens"], "calls": saved["calls"]}


def summarize(rows: Sequence[dict]) -> dict:
    """A fallback (no grade) counts as 0 here: the site would have nothing to answer from. How
    many there were is reported apart."""
    graded = [{**r, "grade": 0 if r["grade"] is None else r["grade"]} for r in rows]
    out: dict = {"fallbacks": [r["id"] for r in rows if r["grade"] is None]}
    for split in ("dev", "test"):
        part = [r for r in graded if r["split"] == split]
        pos = [r["grade"] for r in part if r["answerable"]]
        neg = [r["grade"] for r in part if not r["answerable"]]
        out[split] = {"positives": len(pos), "negatives": len(neg),
                      "auc": round(auc(pos, neg), 3),
                      "grade_counts": {
                          kind: {g: sum(r["grade"] == g for r in part
                                        if r["answerable"] == (kind == "positives"))
                                 for g in GRADES}
                          for kind in ("positives", "negatives")}}
    dev_pos = [r["grade"] for r in graded if r["split"] == "dev" and r["answerable"]]
    for name, cut in (("fixed_cut", FIXED_CUT), ("cut_from_dev", cut_keeping_all(dev_pos))):
        out[name] = {split: at_cut([r for r in graded if r["split"] == split], "grade", cut)
                     for split in ("dev", "test")}
    return out


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    model = e5.from_env()
    if not db_url or model is None:
        print("DATABASE_URL and EMBEDDING_MODEL_DIR are required (see the module docstring)",
              file=sys.stderr)
        return 2
    with httpx.Client(timeout=120) as client:
        out = measure(db_url, load_d1(D1_PATH), model.embed_query, model.embed_passages,
                      groq_grader(client), model=env("GROQ_MODEL"))
    status = {k: out[k] for k in ("missing", "spent_now", "tokens", "calls")}
    print(json.dumps(status))
    if out["missing"]:
        print(f"{len(out['missing'])} questions still to grade; run again to resume")
        return 0
    summary = summarize(out["rows"])
    print(write_results({"strategy": STRATEGY, "query": "Q0", "grader": env("GROQ_MODEL"),
                         "rows": out["rows"], "summary": summary},
                        f"abstain-{STRATEGY}-R3-e5-small-Q0-grades"))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    for r in sorted(out["rows"], key=lambda r: (r["grade"] is None, r["grade"] or 0)):
        mark = "+" if r["answerable"] else "-"
        print(f"{mark} {r['id']} {r['split']:4} {r['category']:14} grade={r['grade']} "
              f"gold_in_top10={r['gold_in_candidates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

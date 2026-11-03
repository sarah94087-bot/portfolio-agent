"""Spike S4: is a free embeddings model available at query time, how fast is it, and does it
match Hebrew questions to English text (docs/04-retrieval-design.md, axis D)?

    python spikes/s4_embeddings.py

Each Hebrew question should be closer to its English passage than to the other passages.
"""

import math
import time

import httpx
from common import GEMINI_BASE, load_env, require, save

PASSAGES = [
    ("Built a human-gated AI translation pipeline using the Claude API; machine output never "
    "overwrites human edits."),
    ("Improved API latency from 582ms to 40ms through SQL optimization and better data access "
    "patterns."),
    ("Built an image embedding system using CLIP, publishing vectors to Kafka and loading them "
    "into pgvector for similarity search."),
    ("Developed an MCP server that lets AI agents analyze Git history, with a human-in-the-loop "
    "approval flow."),
]
QUESTIONS_HE = [
    "איך היא מנעה מתרגום אוטומטי לדרוס עריכה של אדם?",
    "איך היא שיפרה את מהירות ה-API?",
    "היא עבדה עם חיפוש וקטורי?",
    "יש לה ניסיון בבניית כלים לסוכני AI שעובדים עם git?",
]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def embed(client: httpx.Client, key: str, model: str, texts: list[str]) -> tuple[list, int]:
    started = time.perf_counter()
    r = client.post(
        f"{GEMINI_BASE}/embeddings",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "input": texts},
        timeout=30,
    )
    ms = round((time.perf_counter() - started) * 1000)
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]], ms


def main() -> None:
    load_env()
    env = require("GEMINI_API_KEY_EVALS", "EMBEDDING_MODEL")
    key, model = env["GEMINI_API_KEY_EVALS"], env["EMBEDDING_MODEL"]
    with httpx.Client() as client:
        passages, ms_batch = embed(client, key, model, PASSAGES)
        single_ms = []
        questions = []
        for q in QUESTIONS_HE:  # one call per question, like query time in production
            vec, ms = embed(client, key, model, [q])
            questions.append(vec[0])
            single_ms.append(ms)
    hits = 0
    rows = []
    for i, q in enumerate(questions):
        scores = [round(cosine(q, p), 3) for p in passages]
        best = max(range(len(scores)), key=scores.__getitem__)
        hits += best == i
        rows.append({"question": QUESTIONS_HE[i], "scores": scores, "best": best, "expected": i})
    report = {
        "model": model,
        "dimensions": len(passages[0]),
        "ms_batch_of_4": ms_batch,
        "ms_single_query": single_ms,
        "cross_lingual_top1": f"{hits}/{len(questions)}",
        "rows": rows,
    }
    print(f"model {model}, {report['dimensions']} dimensions")
    print(f"single query latency (ms): {single_ms}")
    print(f"Hebrew question -> right English passage: {report['cross_lingual_top1']}")
    print(f"saved {save('s4', report)}")


if __name__ == "__main__":
    main()

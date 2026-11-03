"""Spike S3: do Gemini and Groq call tools correctly from Hebrew questions, write the search
query in English (Q1 in docs/04-retrieval-design.md), and answer in Hebrew with citations?

    python spikes/s3_tool_calling.py [gemini|groq|both]

The tool returns a fixed snippet taken from the public CV, so only model behavior varies.
"""

import json
import sys
import time

import httpx
from common import GEMINI_BASE, GROQ_BASE, HEBREW, hebrew_ratio, load_env, require, save

SYSTEM = (
    "You are an AI agent that presents Sarah Halevy. You are not Sarah. "
    "Answer only from tool results. End every professional claim with [[chunk_id]]. "
    "If the tool results do not answer the question, say you have no information. "
    "Answer in the language of the user's last message."
)

TOOL = {
    "type": "function",
    "function": {
        "name": "search_portfolio",
        "description": (
            "Search Sarah's portfolio. Write the query in English with explicit technical "
            "terms, and replace pronouns from the conversation with the project name."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
        },
    },
}

SNIPPET = {
    "chunk_id": "human-gated-translation#architecture",
    "text": (
        "Built a human-gated AI translation pipeline using the Claude API, ensuring machine "
        "output never overwrites human edits. Part of a live data-governance platform where "
        "Sarah was the sole engineer, with PostgreSQL row-level security and audit trails."
    ),
}

QUESTIONS = [
    "איך היא מנעה מתרגום אוטומטי לדרוס עריכה של אדם?",
    "באיזה API היא השתמשה בצנרת התרגום?",
    "מה היה התפקיד שלה בפלטפורמת ממשל הנתונים?",
    "ספר לי על פרויקט התרגום שלה",
    "האם היא עבדה לבד או בצוות על הפלטפורמה?",
    "איך היא שמרה על עריכות של בני אדם?",
    "יש לה ניסיון עם Claude API?",
    "מה הפרויקט הכי מעניין שלה בתחום ה-AI?",
    "האם היא בנתה מערכת עם audit trail?",
    "איך היא מטפלת בהרשאות במסד הנתונים?",
    "יש לה ניסיון ב-row level security?",
    "מה הייתה המשמעות של human-gated בפרויקט?",
    "תסביר לי את הארכיטקטורה של צנרת התרגום",
    "היא עבדה עם מודלי שפה בפרודקשן?",
    "מה היא עשתה בתחום ממשל נתונים?",
    "האם היא בנתה משהו שרץ בפרודקשן?",
    "איזו ציפיית שכר יש לה?",
    "היא עבדה פעם ב-Google?",
    "תכתוב לי שיר על חתולים",
    "What did she build with the Claude API?",
]

PROVIDERS = {
    "gemini": (GEMINI_BASE, "GEMINI_API_KEY_EVALS", "GEMINI_MODEL"),
    "groq": (GROQ_BASE, "GROQ_API_KEY_EVALS", "GROQ_MODEL"),
}


def chat(client: httpx.Client, base: str, key: str, model: str, messages: list) -> tuple[dict, int]:
    started = time.perf_counter()
    r = client.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, "tools": [TOOL], "temperature": 0.2},
        timeout=60,
    )
    ms = round((time.perf_counter() - started) * 1000)
    r.raise_for_status()
    return r.json()["choices"][0]["message"], ms


def run_one(client: httpx.Client, base: str, key: str, model: str, question: str) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    row: dict = {"question": question}
    try:
        first, row["ms_first"] = chat(client, base, key, model, messages)
        calls = first.get("tool_calls") or []
        row["tool_called"] = bool(calls)
        if calls:
            call = calls[0]
            args = json.loads(call["function"]["arguments"] or "{}")
            row["query"] = args.get("query", "")
            row["query_in_english"] = bool(row["query"]) and not HEBREW.search(row["query"])
            messages += [
                first,
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(SNIPPET)},
            ]
            final, row["ms_final"] = chat(client, base, key, model, messages)
        else:
            final = first
        answer = final.get("content") or ""
        row["answer"] = answer
        row["answer_hebrew_ratio"] = round(hebrew_ratio(answer), 2)
        row["cites_chunk"] = f"[[{SNIPPET['chunk_id']}]]" in answer
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main() -> None:
    load_env()
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    names = list(PROVIDERS) if which == "both" else [which]
    report = {}
    with httpx.Client() as client:
        for name in names:
            base, key_var, model_var = PROVIDERS[name]
            env = require(key_var, model_var)
            rows = []
            for q in QUESTIONS:
                rows.append(run_one(client, base, env[key_var], env[model_var], q))
                time.sleep(4)  # stay under free-tier requests per minute
            report[name] = {"model": env[model_var], "rows": rows}
            ok = [r for r in rows if "error" not in r]
            print(f"\n{name} ({env[model_var]}): {len(ok)}/{len(rows)} without errors")
            print(f"  tool called:        {sum(r['tool_called'] for r in ok)}/{len(ok)}")
            print(f"  query in English:   {sum(r.get('query_in_english', False) for r in ok)}/"
                  f"{sum(r['tool_called'] for r in ok)}")
            print(f"  cites the chunk:    {sum(r['cites_chunk'] for r in ok)}/{len(ok)}")
    print(f"\nsaved {save('s3', report)}")
    print("Read the answers by hand too: Hebrew quality is judged by Sarah, not by a ratio.")


if __name__ == "__main__":
    main()

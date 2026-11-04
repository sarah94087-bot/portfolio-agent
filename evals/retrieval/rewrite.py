"""Q1 and Q2 for stage 3 (docs/04-retrieval-design.md, section 3, axis C): the search query the
agent writes itself, as the `query` parameter of search_portfolio.

The model gets the visitor's question, a system prompt and the tool, and must call the tool.
- Q1: the tool as in docs/06-agent-design.md, section 3: one `query`, in English.
- Q2: the same tool with `alternative_queries`, two more phrasings, fused with the first.

The agent's real system prompt is written in M4. Until then this uses spike S3's prompt, the
shortest one that holds the agent's rules. The queries are saved once per run, so every later
stage reads the same ones (docs/04, section 3). A file that exists is resumed, not redone.

    ../backend/.venv/Scripts/python -m retrieval.rewrite q1|q2 [run]
"""

import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from retrieval.embedders import env, load_env, post
from retrieval.harness import D1Item, load_d1

ROOT = Path(__file__).resolve().parents[2]
QUERIES_DIR = ROOT / "evals" / "datasets" / "queries"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# A hard ceiling per invocation, under the evals budget (docs/10-ops-and-costs.md, section 3):
# 80% of a model's 200,000 daily tokens before launch, shared with every other eval.
MAX_TOKENS = int(os.environ.get("REWRITE_MAX_TOKENS", "60000"))

SYSTEM = (
    "You are an AI agent that presents Sarah Halevy. You are not Sarah. "
    "Answer only from tool results. End every professional claim with [[chunk_id]]. "
    "If the tool results do not answer the question, say you have no information. "
    "Answer in the language of the user's last message."
)
DESCRIPTION = (
    "Search Sarah's portfolio. Write the query in English with explicit technical terms, "
    "and replace pronouns from the conversation with the project name."
)


def tool(mode: str) -> dict:
    props: dict = {"query": {"type": "string", "maxLength": 200}}
    required = ["query"]
    description = DESCRIPTION
    if mode == "q2":
        props["alternative_queries"] = {
            "type": "array", "items": {"type": "string", "maxLength": 200},
            "minItems": 2, "maxItems": 2,
        }
        required.append("alternative_queries")
        description += " Also give two alternative English phrasings that use different terms."
    return {"type": "function", "function": {
        "name": "search_portfolio", "description": description,
        "parameters": {"type": "object", "properties": props, "required": required},
    }}


def parse(message: dict, mode: str) -> dict:
    """The tool call's arguments as {"query", "alternatives"}; raises if the model did not call."""
    calls = message.get("tool_calls") or []
    if not calls:
        raise ValueError("the model did not call search_portfolio")
    args = json.loads(calls[0]["function"]["arguments"])
    query = str(args["query"]).strip()
    alts = [str(a).strip() for a in args.get("alternative_queries") or []] if mode == "q2" else []
    if not query or (mode == "q2" and len([a for a in alts if a]) < 2):
        raise ValueError(f"incomplete arguments: {args}")
    return {"query": query, "alternatives": alts[:2]}


def path_for(mode: str, run: int, split: str = "dev") -> Path:
    return QUERIES_DIR / f"d1-{split}-{mode}-run{run}.json"


def generate(items: Sequence[D1Item], mode: str, run: int = 1, split: str = "dev") -> Path:
    path = path_for(mode, run, split)
    model = env("GROQ_MODEL")
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["model"] != model:
            raise SystemExit(f"{path.name} was made with {saved['model']}, not {model}")
    else:
        saved = {
            "mode": mode, "run": run, "split": split, "model": model,
            "date": time.strftime("%Y-%m-%d"), "system": SYSTEM, "tool": tool(mode),
            "tokens": 0, "queries": {},
        }
    todo = [i for i in items if i.split == split and i.expected_behavior == "answer"
            and i.id not in saved["queries"]]
    spent = 0
    headers = {"Authorization": f"Bearer {env('GROQ_API_KEY_EVALS')}"}
    with httpx.Client(timeout=60) as client:
        for item in todo:
            if spent >= MAX_TOKENS:
                print(f"stopped at the {MAX_TOKENS} token ceiling; run again to resume")
                break
            body = {
                "model": model, "tools": [tool(mode)],
                "tool_choice": {"type": "function", "function": {"name": "search_portfolio"}},
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": item.question}],
            }
            data = post(client, GROQ_URL, headers=headers, json=body).json()
            used = data.get("usage", {}).get("total_tokens", 0)
            spent += used
            saved["tokens"] += used
            saved["queries"][item.id] = parse(data["choices"][0]["message"], mode)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return path


def load_queries(mode: str, run: int = 1, split: str = "dev") -> dict[str, dict]:
    return json.loads(path_for(mode, run, split).read_text(encoding="utf-8"))["queries"]


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("q1", "q2"):
        print("usage: rewrite q1|q2 [run]", file=sys.stderr)
        return 2
    load_env()
    from retrieval.run_stage1 import D1_PATH

    mode, run = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1
    path = generate(load_d1(D1_PATH), mode, run)
    saved = json.loads(path.read_text(encoding="utf-8"))
    print(f"{path}: {len(saved['queries'])} queries, {saved['tokens']} tokens in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())

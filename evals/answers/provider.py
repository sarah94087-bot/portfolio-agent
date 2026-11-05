"""The Promptfoo provider: runs a case's turns through the agent (agent.py).

The output is an object, so the code checks read fields and the judge reads the answer
together with the sources it cited: `answer` and `sources` of the last turn, and `turns` with
every turn of a conversation (D4, and D1 or D2 cases with history).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Promptfoo runs this file directly

from agent import run  # noqa: E402


def call_api(prompt, options, context):
    vars_ = context.get("vars", {})
    turns = json.loads(vars_["turns"]) if vars_.get("turns") else [prompt]  # cases.py: JSON text
    try:
        results = run(turns)
    except Exception as e:  # the case fails with the reason, the run goes on
        return {"error": f"{type(e).__name__}: {e}"}
    last = results[-1]
    output = {**last, "turns": [{"user": r["user"], "answer": r["answer"]} for r in results]}
    tokens = [r["tokens"] for r in results]
    return {
        "output": output,
        "tokenUsage": {
            "prompt": sum(t["input"] for t in tokens),
            "completion": sum(t["output"] for t in tokens),
            "total": sum(t["input"] + t["output"] for t in tokens),
        },
    }

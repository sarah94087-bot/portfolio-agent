"""The Promptfoo provider: runs a case's turns through the agent (agent.py).

The output is an object, so the code checks read fields and the judge reads the answer
together with the sources it cited: `answer` and `sources` of the last turn, and `turns` with
every turn of a conversation (D4, and D1 or D2 cases with history).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Promptfoo runs this file directly

from agent import run  # noqa: E402


def _progress(case, detail, started):
    """One line per case for the run's log, which is public: ids and counts, never the text.
    Promptfoo prints nothing else until the end, so this shows where a long run spends its time."""
    seconds = time.monotonic() - started
    print(f"[case] {case}: {detail}, {seconds:.0f} s", file=sys.stderr, flush=True)


def call_api(prompt, options, context):
    vars_ = context.get("vars", {})
    turns = json.loads(vars_["turns"]) if vars_.get("turns") else [prompt]  # cases.py: JSON text
    case, started = vars_.get("id", "?"), time.monotonic()
    try:
        results = run(turns)
    except Exception as e:  # the case fails with the reason, the run goes on
        _progress(case, f"failed with {type(e).__name__}", started)
        return {"error": f"{type(e).__name__}: {e}"}
    models = ",".join(dict.fromkeys(str(r["model"]) for r in results))
    total = sum(r["tokens"]["input"] + r["tokens"]["output"] for r in results)
    fallback = any(r["fallback"] for r in results)
    switches = ",".join(s for r in results for s in r.get("switches", [])) or "none"
    errors = ",".join(str(r["error"]) for r in results if r.get("error")) or "none"
    revised = sum(bool(r.get("revised")) for r in results)
    uncited = sum(bool(r.get("uncited")) for r in results)
    _progress(case, f"model {models}, fallback {fallback}, {total} tokens, "
                    f"switches {switches}, error {errors}, revised {revised}, "
                    f"uncited {uncited}", started)
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

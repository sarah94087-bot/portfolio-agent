"""Lists the models each provider key can use, to pick GEMINI_MODEL, GROQ_MODEL and
EMBEDDING_MODEL from what is actually available. Prints model ids only.

    python spikes/list_models.py
"""

import httpx
from common import GEMINI_BASE, GROQ_BASE, load_env, require


def list_ids(base: str, key: str) -> list[str]:
    r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    r.raise_for_status()
    return sorted(m["id"] for m in r.json()["data"])


def main() -> None:
    load_env()
    env = require("GEMINI_API_KEY_EVALS", "GROQ_API_KEY_EVALS")
    for name, base, key in [
        ("gemini", GEMINI_BASE, env["GEMINI_API_KEY_EVALS"]),
        ("groq", GROQ_BASE, env["GROQ_API_KEY_EVALS"]),
    ]:
        try:
            ids = list_ids(base, key)
            print(f"\n{name}: {len(ids)} models")
            for model_id in ids:
                print(f"  {model_id}")
        except httpx.HTTPError as exc:
            print(f"\n{name}: failed ({type(exc).__name__})")


if __name__ == "__main__":
    main()

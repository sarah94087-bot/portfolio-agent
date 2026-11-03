"""Checks that .env has every value M1 needs. Prints names only, never values.

    python spikes/check_env.py
"""

import os

from common import load_env

GROUPS = {
    "S3 tool calling": ["GEMINI_API_KEY_EVALS", "GROQ_API_KEY_EVALS", "GEMINI_MODEL", "GROQ_MODEL"],
    "S4 embeddings": ["GEMINI_API_KEY_EVALS", "EMBEDDING_MODEL"],
    "S6 Langfuse": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"],
    "S2 database": ["DATABASE_URL", "DATABASE_URL_DIRECT"],
    "Production (needed at deploy)": [
        "GEMINI_API_KEY", "GROQ_API_KEY", "RESEND_API_KEY", "CONTACT_EMAIL",
        "VISITOR_HMAC_SECRET", "CANARY_TOKEN",
    ],
}

load_env()
all_ok = True
for group, names in GROUPS.items():
    missing = [n for n in names if not os.environ.get(n)]
    all_ok &= not missing
    detail = f": {', '.join(missing)}" if missing else ""
    print(f"{'MISSING' if missing else 'OK     '}  {group}{detail}")
raise SystemExit(0 if all_ok else 1)

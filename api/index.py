"""Vercel entry point. Vercel turns every .py file under api/ into a function, so the
application code lives in backend/ and this file only exposes the ASGI app.
Whether this layout works on Vercel is what spike S1 checks (docs/11-roadmap.md, M1).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from portfolio_agent.main import app  # noqa: E402

__all__ = ["app"]

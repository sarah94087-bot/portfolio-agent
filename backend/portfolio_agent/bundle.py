"""The Vercel build: python -m portfolio_agent.bundle (pyproject.toml, tool.vercel.scripts).

What the function reads at run time and the repository does not give it: the knowledge base,
which sits outside the backend service, and the embedding model, which is not in the repo. Both
land beside the code. The records are checked here, so a bad or missing knowledge base fails
the build and never reaches a visitor.
"""

import shutil
import sys
from pathlib import Path

from portfolio_agent.ingest import load
from portfolio_agent.kb_check import BUNDLED_PORTFOLIO_DIR, REPO_PORTFOLIO_DIR
from portfolio_agent.retrieval.embedder import BUNDLED_DIR
from portfolio_agent.retrieval.fetch_model import fetch


def _not_records(folder: str, names: list[str]) -> list[str]:
    return [n for n in names if (Path(folder) / n).is_file() and not n.endswith(".md")]


def bundle_knowledge(source: Path = REPO_PORTFOLIO_DIR,
                     target: Path = BUNDLED_PORTFOLIO_DIR) -> int:
    """Copies the records beside the code and returns how many there are."""
    count = len(load(source))
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, ignore=_not_records)
    return count


def main() -> int:
    print(f"bundling {bundle_knowledge()} records in {BUNDLED_PORTFOLIO_DIR}")
    print(f"bundling the model in {BUNDLED_DIR}")
    fetch(BUNDLED_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())

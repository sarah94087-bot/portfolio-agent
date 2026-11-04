"""Publication check: no forbidden term in any file the repo publishes.

    python -m portfolio_agent.publication_check [--require]

docs/02-knowledge-base.md, sections 8 and 9: the list of forbidden terms (client names, product
names under NDA, anything that must stay out) is itself sensitive, so it lives only in the
PUBLICATION_TERMS secret in CI, or in the local .env. Terms are separated by new lines or commas.

The repo is public, so every tracked file is checked, not only portfolio/: a term in docs/ or
evals/ leaks just the same. Matching uses the search normalization (case, Hebrew final letters,
niqqud) and finds a term inside a longer word too, so a Hebrew prefix (ב, ה, ו...) does not hide
it. Errors name the file, the line and the term's number in the list, never the term itself,
because CI logs of a public repo are public.

Without a list the check is skipped, unless --require (used in CI) makes that an error.
"""

import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from portfolio_agent.retrieval.normalize import normalize

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_VAR = "PUBLICATION_TERMS"


def parse_terms(raw: str) -> list[str]:
    parts = (p.strip() for line in raw.splitlines() for p in line.split(","))
    return [p for p in parts if p]


def load_terms() -> list[str]:
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == ENV_VAR:
                    raw = value.strip().strip("'\"")
    return parse_terms(raw or "")


def tracked_files(root: Path | None = None) -> list[Path]:
    root = ROOT if root is None else root
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [root / p for p in out.stdout.decode("utf-8").split("\0") if p]


def find(terms: list[str], files: Iterable[Path], root: Path | None = None) -> list[str]:
    """One error per (file, line, term). Files that are not UTF-8 text are skipped."""
    root = ROOT if root is None else root
    needles = [(n, normalize(t)) for n, t in enumerate(terms, start=1)]
    errors = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            hay = normalize(line)
            errors.extend(f"{rel}:{lineno}: forbidden term #{n}" for n, t in needles if t in hay)
    return errors


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    terms = load_terms()
    if not terms:
        if "--require" in argv:
            print(f"{ENV_VAR} is empty: add the list as a CI secret", file=sys.stderr)
            return 1
        print(f"skipped: {ENV_VAR} is not set")
        return 0
    files = tracked_files()
    errors = find(terms, files)
    for err in errors:
        print(err)
    if errors:
        return 1
    print(f"ok: {len(terms)} terms, {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

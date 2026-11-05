"""What a non-editable install ships: every subpackage and every file the code reads."""

import tomllib
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).parents[1]
PKG = ROOT / "portfolio_agent"
CONFIG = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]


def test_every_subpackage_is_found():
    include = CONFIG["packages"]["find"]["include"]
    for init in PKG.rglob("__init__.py"):
        name = ".".join(init.parent.relative_to(ROOT).parts)
        assert any(fnmatch(name, pattern) for pattern in include), name


def test_every_data_file_is_package_data():
    data = CONFIG["package-data"]
    for path in PKG.rglob("*"):
        if path.is_dir() or path.suffix in {".py", ".pyc"} or "__pycache__" in path.parts:
            continue
        owner = path.parent
        while not (owner / "__init__.py").exists():
            owner = owner.parent
        rel = path.relative_to(owner).as_posix()
        package = ".".join(owner.relative_to(ROOT).parts)
        assert any(fnmatch(rel, g) for g in data.get(package, [])), path

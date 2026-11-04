"""Schema check for the knowledge base: python -m portfolio_agent.kb_check [portfolio_dir]

Implements the checks in docs/02-knowledge-base.md, sections 3, 6 and 9: required fields,
review.approved, how_measured for every metric, the fixed body headings, and skill levels
backed by evidence. Each error says exactly which file and field is wrong.
Record types without a schema here yet fail, so a new type gets its schema before it ships.
"""

import re
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PORTFOLIO_DIR = Path(__file__).resolve().parent.parent.parent / "portfolio"

SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
Text = Annotated[str, Field(min_length=1)]

# docs/02-knowledge-base.md, section 3 ("גוף הרשומה")
SECTIONS = [
    "Problem",
    "Why it was hard",
    "My role",
    "Architecture",
    "Decisions and alternatives",
    "What broke",
    "Results",
    "In hindsight",
]
REQUIRED_SECTIONS = {
    "full": {"Problem", "Why it was hard", "My role", "Architecture",
             "Decisions and alternatives", "Results"},
    "overview": {"Problem", "My role", "Architecture", "Results"},
}
# Section 2: an experience record gives the context, the responsibility, and links to projects.
EXPERIENCE_SECTIONS = ["Context", "Responsibilities", "Projects"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Title(Strict):
    en: Text
    he: Text


class Review(Strict):
    approved: bool
    approved_on: date | None = None
    publication_check: Literal["employer-ok", "own-project", "anonymized"] | None = None

    @model_validator(mode="after")
    def approved_with_date(self):
        if not self.approved:
            raise ValueError("review.approved must be true: an unapproved record is not ingested")
        if self.approved_on is None:
            raise ValueError("review.approved_on is required once approved")
        return self


class Metric(Strict):
    label: Text
    before: str | None = None
    after: str | None = None
    value: str | None = None
    how_measured: str = Field(min_length=1, description="without it, the number does not go in")


class Component(Strict):
    id: Text
    label: Text


class Edge(Strict):
    from_: str = Field(alias="from", min_length=1)
    to: Text
    label: str | None = None


class Architecture(Strict):
    components: list[Component] = Field(min_length=1)
    edges: list[Edge] = []

    @model_validator(mode="after")
    def edges_use_known_components(self):
        ids = {c.id for c in self.components}
        for e in self.edges:
            for end in (e.from_, e.to):
                if end not in ids:
                    raise ValueError(f"edge points at unknown component '{end}'")
        return self


def require_publication_check(v: Review) -> Review:
    if v.publication_check is None:
        raise ValueError("review.publication_check is required")
    return v


class Project(Strict):
    id: str = Field(pattern=SLUG)
    type: Literal["project"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    period: Text
    experience: str | None = Field(default=None, pattern=SLUG)
    role: Text
    tech: list[str] = Field(min_length=1)
    tags: list[str] = []
    metrics: list[Metric] = []
    architecture: Architecture
    code_allowed: bool
    depth: Literal["full", "overview"]
    related: list[str] = []
    answers: list[str] = Field(min_length=1)
    review: Review

    _publication = field_validator("review")(require_publication_check)


class Experience(Strict):
    id: str = Field(pattern=SLUG)
    type: Literal["experience"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    employer: Text
    role: Text
    period: Text
    location: str | None = None
    projects: list[str] = []
    tags: list[str] = []
    answers: list[str] = Field(min_length=1)
    review: Review

    _publication = field_validator("review")(require_publication_check)


class Program(Strict):
    institution: Text
    program: Text
    field: Text
    start: Text
    end: Text
    grade: str | None = None


class Education(Strict):
    id: Literal["education"]
    type: Literal["education"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    programs: list[Program] = Field(min_length=1)
    answers: list[str] = Field(min_length=1)
    review: Review


class Profile(Strict):
    id: Literal["profile"]
    type: Literal["profile"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    name: Title
    headline: Text
    answers: list[str] = Field(min_length=1)
    review: Review


class Roles(Strict):
    primary: list[str] = Field(min_length=1)
    open_to: list[str] = []


class Preferences(Strict):
    id: Literal["preferences"]
    type: Literal["preferences"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    roles: Roles
    work_mode: list[Literal["remote", "hybrid", "office"]] = Field(min_length=1)
    locations: list[str] = []
    availability: Text
    answers: list[str] = Field(min_length=1)
    review: Review


class Faq(Strict):
    id: Literal["faq"]
    type: Literal["faq"]
    title: Title
    aliases: list[str] = Field(min_length=1)
    review: Review


class Skill(Strict):
    name: Text
    level: Literal["used", "studied", "listed"]
    evidence: list[str] = []
    note: str | None = None

    @model_validator(mode="after")
    def evidence_matches_level(self):
        if self.level in ("used", "studied") and not self.evidence:
            raise ValueError(f"'{self.name}' is {self.level} but has no evidence")
        if self.level == "listed" and self.evidence:
            raise ValueError(f"'{self.name}' is listed, so evidence must be empty")
        return self


class Skills(Strict):
    id: Literal["skills"]
    type: Literal["skills"]
    title: Title
    skills: list[Skill] = Field(min_length=1)
    review: Review


SCHEMAS = {
    "project": Project,
    "experience": Experience,
    "education": Education,
    "profile": Profile,
    "preferences": Preferences,
    "faq": Faq,
    "skills": Skills,
}


def split(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError("missing frontmatter between --- lines")
    meta = yaml.safe_load(m.group(1))
    if not isinstance(meta, dict):
        raise ValueError("frontmatter is not a mapping")
    return meta, m.group(2)


def body_sections(body: str) -> list[tuple[str, str]]:
    """(heading, text) for every '## ' heading, in file order. Ingestion chunks the same split."""
    names = re.findall(r"^## (.+?)\s*$", body, re.MULTILINE)
    parts = re.split(r"^## .+$", body, flags=re.MULTILINE)[1:]
    return list(zip(names, parts, strict=True))


def body_errors(body: str, sections: list[str], required: set[str]) -> list[str]:
    errors = []
    parsed = body_sections(body)
    found = [name for name, _ in parsed]
    for name in found:
        if name not in sections:
            errors.append(f"unknown heading '## {name}'")
    if len(found) != len(set(found)):
        errors.append("a heading appears twice")
    known = [n for n in found if n in sections]
    if known != sorted(known, key=sections.index):
        errors.append("headings are out of order")
    for name in sorted(required - set(found), key=sections.index):
        errors.append(f"missing required heading '## {name}'")
    for name, text in parsed:
        if not re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip():
            errors.append(f"heading '## {name}' is empty")
    if "<!-- GAP" in body:
        errors.append("body still has a GAP marker")
    return errors


def check_file(path: Path) -> tuple[BaseModel | None, list[str]]:
    try:
        meta, body = split(path.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError) as e:
        return None, [str(e)]
    schema = SCHEMAS.get(meta.get("type"))
    if schema is None:
        return None, [f"no schema yet for type '{meta.get('type')}'"]
    try:
        record = schema.model_validate(meta)
    except ValidationError as e:
        return None, [
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in e.errors()
        ]
    errors = []
    if record.id != path.stem:
        errors.append(f"id '{record.id}' does not match the file name '{path.stem}'")
    if isinstance(record, Project):
        errors += body_errors(body, SECTIONS, REQUIRED_SECTIONS[record.depth])
    elif isinstance(record, Experience):
        errors += body_errors(body, EXPERIENCE_SECTIONS, set(EXPERIENCE_SECTIONS))
    elif isinstance(record, Profile | Preferences):
        errors += body_errors(body, ["Context"], {"Context"})
    elif isinstance(record, Faq):
        # Every heading is one question, so headings are free text (section 3 does not apply).
        questions = re.findall(r"^## (.+?)\s*$", body, re.MULTILINE)
        errors += body_errors(body, questions, set()) if questions else ["no questions"]
    return record, errors


def check(portfolio_dir: Path) -> dict[str, list[str]]:
    """Returns {relative path: errors} for every file with at least one error."""
    results: dict[str, list[str]] = {}
    records: dict[str, BaseModel] = {}
    paths: dict[str, str] = {}
    for path in sorted(portfolio_dir.rglob("*.md")):
        rel = path.relative_to(portfolio_dir).as_posix()
        record, errors = check_file(path)
        if record is not None:
            if record.id in records:
                errors.append(f"duplicate id '{record.id}'")
            records[record.id] = record
            paths[record.id] = rel
        if errors:
            results[rel] = errors
    # Skill evidence must point at records that exist (section 6).
    skills = records.get("skills")
    if isinstance(skills, Skills):
        missing = [
            f"'{s.name}' cites '{ev}', which has no record"
            for s in skills.skills for ev in s.evidence if ev not in records
        ]
        if missing:
            results.setdefault("skills.md", []).extend(missing)
    # A project and its experience record must point at each other.
    for rid, record in records.items():
        errors = []
        if isinstance(record, Project) and record.experience:
            exp = records.get(record.experience)
            if not isinstance(exp, Experience):
                errors.append(f"experience '{record.experience}' has no record")
            elif rid not in exp.projects:
                errors.append(f"'{record.experience}' does not list this project")
        if isinstance(record, Experience):
            for pid in record.projects:
                project = records.get(pid)
                if not isinstance(project, Project):
                    errors.append(f"project '{pid}' has no record")
                elif project.experience != rid:
                    errors.append(f"project '{pid}' does not point back at '{rid}'")
        if errors:
            results.setdefault(paths[rid], []).extend(errors)
    return results


def main() -> int:
    portfolio_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PORTFOLIO_DIR
    results = check(portfolio_dir)
    for rel, errors in results.items():
        for err in errors:
            print(f"{rel}: {err}")
    if results:
        return 1
    print(f"ok: {sum(1 for _ in portfolio_dir.rglob('*.md'))} records")
    return 0


if __name__ == "__main__":
    sys.exit(main())

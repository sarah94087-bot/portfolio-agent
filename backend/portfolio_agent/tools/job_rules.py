"""What the code decides in a job match, with no model involved (docs/07-advanced-capabilities.md,
section 2): the caps on a rating by the kind of proof behind it, and the overall score.

The model proposes a strength and citations. Here a citation outside what was retrieved for that
requirement is dropped, and the strength is cut to what the remaining proof allows, so a posting
that talks the model into "strong" still needs a real passage from a project or a role.

A `used` skill is a line in the skills record that points at projects. It is not itself a passage
from one, so alone it allows `partial`, as studied and listed skills do; the same goes for
education, the profile and the FAQ. Only the project or role passage can carry `strong`.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

Strength = Literal["strong", "partial", "none"]
Kind = Literal["must", "nice"]
Overall = Literal["high", "partial", "low"]
Tier = Literal["work", "used", "studied", "listed", "other"]

POINTS: dict[str, float] = {"strong": 1.0, "partial": 0.5, "none": 0.0}
WEIGHT: dict[str, int] = {"must": 2, "nice": 1}
HIGH = 0.75
PARTIAL = 0.45
MAX_EVIDENCE = 3  # per requirement (stage 2)
MAX_RATIONALE_WORDS = 25


@dataclass(frozen=True)
class Proof:
    """What a retrieved chunk is worth as proof."""

    tier: Tier
    years: tuple[int, ...] = ()  # calendar years of the record's period, for a years requirement


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    kind: Kind
    category: str = "other"
    years: int | None = None
    query: str = ""  # English search terms; never shown


@dataclass(frozen=True)
class Rating:
    strength: Strength
    evidence: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Rated:
    requirement: Requirement
    strength: Strength
    evidence: tuple[str, ...]
    rationale: str
    cv_only: bool = False
    years_required: int | None = None  # set when the portfolio does not cover the years asked
    years_covered: int | None = None
    capped_from: Strength | None = None  # what the model said, when the code cut it
    dropped: tuple[str, ...] = ()  # citations outside what was retrieved


_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?|שנים|שנות|שנה)", re.I)
_TWO_YEARS = re.compile("שנתיים")


def required_years(requirement: Requirement) -> int | None:
    """The extractor's number, or one in the text: the cap must not depend on the model noticing."""
    if requirement.years:
        return requirement.years
    if m := _YEARS.search(requirement.text):
        return int(m.group(1))
    return 2 if _TWO_YEARS.search(requirement.text) else None


def years_covered(proofs: Iterable[Proof]) -> int:
    """How long the cited work spans, in calendar years: 2025 and 2026 are 2."""
    years = [y for p in proofs for y in p.years]
    return max(years) - min(years) + 1 if years else 0


def clip_words(text: str, limit: int = MAX_RATIONALE_WORDS) -> str:
    words = text.split()
    return " ".join(words) if len(words) <= limit else " ".join(words[:limit]) + "…"


def enforce(requirement: Requirement, rating: Rating, candidates: Mapping[str, Proof],
            no_evidence: str) -> Rated:
    """Stage 4. `candidates` is what stage 2 retrieved for this requirement, and nothing else."""
    unique = list(dict.fromkeys(rating.evidence))
    valid = [c for c in unique if c in candidates][:MAX_EVIDENCE]
    dropped = tuple(c for c in unique if c not in candidates)
    if rating.strength == "none" or not valid:
        return Rated(requirement, "none", (), no_evidence,
                     capped_from=None if rating.strength == "none" else rating.strength,
                     dropped=dropped)

    proofs = [candidates[c] for c in valid]
    strength = rating.strength
    if strength == "strong" and all(p.tier != "work" for p in proofs):
        strength = "partial"

    asked = required_years(requirement)
    covered = years_covered(proofs)
    missing_years = asked is not None and asked > covered
    if missing_years and strength == "strong":
        strength = "partial"

    return Rated(
        requirement, strength, tuple(valid), clip_words(rating.rationale),
        cv_only=all(p.tier == "listed" for p in proofs),
        years_required=asked if missing_years else None,
        years_covered=covered if missing_years else None,
        capped_from=rating.strength if strength != rating.strength else None,
        dropped=dropped,
    )


def score(items: Iterable[tuple[str, str]]) -> float:
    """(kind, strength) pairs: strong 1, partial 0.5, none 0, a must weighs twice a nice."""
    pairs = list(items)
    total = sum(WEIGHT[kind] for kind, _ in pairs)
    return sum(WEIGHT[kind] * POINTS[s] for kind, s in pairs) / total if total else 0.0


def overall(value: float) -> Overall:
    return "high" if value >= HIGH else "partial" if value >= PARTIAL else "low"


def gaps(rated: Sequence[Rated]) -> list[Rated]:
    """Every requirement without proof, the musts first whatever the score."""
    return sorted((r for r in rated if r.strength == "none"),
                  key=lambda r: r.requirement.kind != "must")

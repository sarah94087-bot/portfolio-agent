"""Statistics for small eval sets: Wilson intervals and a paired bootstrap.

Implements docs/03-evaluation-methodology.md, section 5: every rate is reported as a count
with a 95% Wilson interval, and a method counts as better than another only when the paired
bootstrap interval of the difference excludes zero. The decision rule in
docs/04-retrieval-design.md, section 5 reads `Difference.significant`.
Standard library only, and seeded, so every number is reproducible from the repo (US-9.6).
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist, fmean


def wilson(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a rate. Unlike p ± z·se, it stays inside [0, 1] at 0/n and n/n."""
    if n <= 0:
        raise ValueError("n must be positive: a rate over zero items has no interval")
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be between 0 and n, got {successes}/{n}")
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = successes / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z / (1 + z * z / n) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    # At 0/n and n/n the formula lands on the bound only up to rounding.
    low = 0.0 if successes == 0 else center - half
    high = 1.0 if successes == n else center + half
    return low, high


def format_rate(successes: int, n: int) -> str:
    """'57/60 (95%) [86%, 98%]': the count next to the percentage, with its interval."""
    low, high = wilson(successes, n)
    return f"{successes}/{n} ({successes / n:.0%}) [{low:.0%}, {high:.0%}]"


@dataclass(frozen=True)
class Difference:
    """Mean of b - a over paired items, with a percentile bootstrap interval."""

    mean: float
    low: float
    high: float
    n: int

    @property
    def significant(self) -> bool:
        return not self.low <= 0 <= self.high


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Difference:
    """Compares two methods question by question: a[i] and b[i] are scores on the same item.

    Resamples items, not scores, so the pairing survives. A positive mean means b is better.
    """
    if len(a) != len(b):
        raise ValueError(f"paired scores need the same items, got {len(a)} and {len(b)}")
    if not a:
        raise ValueError("no items to compare")
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    low, high = bootstrap_mean(diffs, resamples, confidence, seed)
    return Difference(mean=fmean(diffs), low=low, high=high, n=len(diffs))


def bootstrap_mean(
    values: Sequence[float],
    resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval for a mean, such as Recall@5 averaged over questions."""
    if not values:
        raise ValueError("no values")
    rng = random.Random(seed)
    means = sorted(fmean(rng.choices(values, k=len(values))) for _ in range(resamples))
    tail = (1 - confidence) / 2
    return means[math.floor(tail * resamples)], means[math.ceil((1 - tail) * resamples) - 1]


def cohen_kappa(a: Sequence, b: Sequence) -> float | None:
    """Agreement between two raters beyond chance (docs/03, section 4: the judge is accepted at
    kappa >= 0.7). None when chance agreement is already 1, as when both raters gave one label
    to everything: kappa is undefined there, and the raw agreement says what there is to say."""
    if len(a) != len(b) or not a:
        raise ValueError("kappa needs two label lists of the same, nonzero length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    labels = set(a) | set(b)
    expected = sum((list(a).count(k) / n) * (list(b).count(k) / n) for k in labels)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def kappa_interval(a: Sequence, b: Sequence, rounds: int = 2000, seed: int = 0,
                   confidence: float = 0.95) -> tuple[float, float] | None:
    """Percentile bootstrap over the labeled items, resampled in pairs. Resamples where kappa is
    undefined are left out; None if most of them are."""
    rng = random.Random(seed)
    pairs = list(zip(a, b, strict=True))
    values = []
    for _ in range(rounds):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        k = cohen_kappa([x for x, _ in sample], [y for _, y in sample])
        if k is not None:
            values.append(k)
    if len(values) < rounds / 2:
        return None
    values.sort()
    tail = (1 - confidence) / 2
    return values[int(tail * len(values))], values[min(len(values) - 1,
                                                       int((1 - tail) * len(values)))]

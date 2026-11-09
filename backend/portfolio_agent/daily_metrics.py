"""The daily computation behind /stats: python -m portfolio_agent.daily_metrics

Runs in retention.yml before the deletions, so a 30-day window is still whole. Each run writes
both windows (7 and 30 whole UTC days, ending yesterday) from the saved answers. Run twice in a
day, it gives the same rows.

What is measured (docs/08-transparency.md, section 4):
- Response times come from the answers the model wrote in a chat turn. An answer from the cache
  and a job match would distort them: one takes no model time, the other runs a pipeline.
- A backup model answered if a model failed during the turn, or the first one was already closed.
- "Unanswered" has no flag of its own. It is approximated by what can be checked at no cost: the
  agent searched the portfolio, and the answer cites nothing. A greeting never searches, so it
  does not count. A job match and a blocked answer are not questions the portfolio failed.
- A rating marked as a challenge attempt is a report about the agent, not a level of satisfaction.

The repository is public and so are its Actions logs: nothing about the numbers is printed.
"""

import math
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import psycopg

WINDOWS = (7, 30)
MODEL_SHARE = "model_share:"  # + the name of the model

Measure = tuple[float | None, int]  # the value, and how many observations are behind it


@dataclass(frozen=True)
class Answer:
    created_at: datetime
    model: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    searched: bool = False
    rating: str | None = None


def percentile(values: list[float], fraction: float) -> float | None:
    """Linear interpolation between the closest ranks, as Postgres's percentile_cont."""
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * fraction
    low = math.floor(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _rate(answers: list[Answer], counted: Callable[[Answer], Any]) -> Measure:
    if not answers:
        return None, 0
    return sum(1 for a in answers if counted(a)) / len(answers), len(answers)


def _percentiles(name: str, values: list[float]) -> dict[str, Measure]:
    return {f"{name}_p50": (percentile(values, 0.5), len(values)),
            f"{name}_p95": (percentile(values, 0.95), len(values))}


def _stats(answer: Answer) -> dict[str, Any]:
    return answer.meta.get("stats") or {}


def _on_backup(answer: Answer) -> bool:
    return bool(answer.meta.get("switches") or _stats(answer).get("backup"))


def aggregate(answers: Iterable[Answer]) -> dict[str, Measure]:
    every = list(answers)
    written = [a for a in every if not a.meta.get("cached")]
    cited = [a for a in written if not a.meta.get("direct")]
    searched = [a for a in every
                if a.searched and not a.meta.get("card") and not a.meta.get("blocked")]
    measures = {
        "fallback_rate": _rate(written, _on_backup),
        "cache_rate": _rate(every, lambda a: a.meta.get("cached")),
        "citation_removed_rate": _rate(cited, lambda a: a.meta.get("dropped")),
        "unanswered_rate": _rate(searched, lambda a: not a.meta.get("cited")),
        "satisfaction_rate": _rate([a for a in every if a.rating], lambda a: a.rating == "up"),
    }
    timed = [s for s in map(_stats, every) if s.get("total_ms") is not None]
    measures |= _percentiles("total_ms", [s["total_ms"] for s in timed])
    for label, cold in (("warm", False), ("cold", True)):
        first = [s["ttft_ms"] for s in timed if s.get("ttft_ms") is not None
                 and bool(s.get("cold")) is cold]
        measures |= _percentiles(f"ttft_ms_{label}", first)
    models = Counter(a.model for a in written if a.model)
    total = sum(models.values())
    measures |= {f"{MODEL_SHARE}{m}": (n / total, total) for m, n in models.items()}
    return measures


def read_answers(conn: psycopg.Connection, start: datetime, end: datetime) -> list[Answer]:
    rows = conn.execute(
        "select m.created_at, m.model, m.meta,"
        " exists (select 1 from steps s where s.message_id = m.id"
        "         and s.name = 'search_portfolio'),"
        " case when f.challenge then null else f.rating end"
        " from messages m left join feedback f on f.message_id = m.id"
        " where m.role = 'assistant' and m.created_at >= %s and m.created_at < %s",
        (start, end),
    ).fetchall()
    return [Answer(*row) for row in rows]


def compute(conn: psycopg.Connection, now: datetime) -> date:
    """Replaces the rows of the last whole day, and returns that day. A model no longer in use
    must not keep a row, so the day's rows are deleted first."""
    end = datetime.combine(now.date(), time.min, tzinfo=UTC)
    day = (end - timedelta(days=1)).date()
    answers = read_answers(conn, end - timedelta(days=max(WINDOWS)), end)
    rows = [
        (day, metric, days, value, size)
        for days in WINDOWS
        for metric, (value, size) in aggregate(
            a for a in answers if a.created_at >= end - timedelta(days=days)).items()
    ]
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("delete from daily_metrics where day = %s", (day,))
        cur.executemany(
            "insert into daily_metrics (day, metric, window_days, value, sample_size)"
            " values (%s, %s, %s, %s, %s)", rows)
    return day


def main() -> int:
    url = os.environ.get("DATABASE_URL_DIRECT") or os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL_DIRECT or DATABASE_URL is required", file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
        compute(conn, datetime.now(UTC))
    print("daily metrics written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

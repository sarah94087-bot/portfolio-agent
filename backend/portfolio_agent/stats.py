"""GET /api/stats: the public numbers behind /stats (US-9.3; docs/08-transparency.md, section 4).

This is the privacy gate. daily_metrics keeps exact values and sample sizes, and only what passes
here reaches a visitor:
- a measure with fewer than 30 observations in its window is null;
- a rate is rounded to the nearest 5%, a time to the nearest 100 ms;
- a sample size never leaves, nor does any count of conversations or visitors.

Reads only daily_metrics, and the CDN holds the response for 5 minutes, so a page view does not
wake the database and spends no model tokens.
"""

import logging
import math
from collections.abc import Iterable
from datetime import date
from typing import Any

import psycopg
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from portfolio_agent import chat
from portfolio_agent.daily_metrics import MODEL_SHARE, WINDOWS

log = logging.getLogger(__name__)
router = APIRouter()

MIN_SAMPLE = 30
RATE_STEP = 5  # percent
TIME_STEP = 100  # milliseconds
RATES = ("fallback_rate", "cache_rate", "unanswered_rate", "citation_removed_rate",
         "satisfaction_rate")
TIMES = ("total_ms_p50", "total_ms_p95", "ttft_ms_warm_p50", "ttft_ms_warm_p95",
         "ttft_ms_cold_p50", "ttft_ms_cold_p95")
CACHE = "public, max-age=0, s-maxage=300"

Row = tuple[int, str, float | None, int]  # window_days, metric, value, sample_size


def _nearest(value: float, step: int) -> int:
    """Half goes up, unlike round(), which would send 12.5% and 17.5% in different directions."""
    return math.floor(value / step + 0.5) * step


def percent(rate: float) -> int:
    return _nearest(rate * 100, RATE_STEP)


def milliseconds(value: float) -> int:
    return _nearest(value, TIME_STEP)


def public_view(day: date | None, rows: Iterable[Row]) -> dict[str, Any]:
    """Unknown metrics are left out, so a new one is public only once it is named here."""
    shown = [(w, m, v) for w, m, v, n in rows if v is not None and n >= MIN_SAMPLE]
    windows: dict[str, dict[str, Any]] = {}
    for days in WINDOWS:
        found = {m: v for w, m, v in shown if w == days}
        models = [{"model": m.removeprefix(MODEL_SHARE), "share": percent(v)}
                  for m, v in found.items() if m.startswith(MODEL_SHARE)]
        windows[str(days)] = {
            **{m: percent(found[m]) if m in found else None for m in RATES},
            **{m: milliseconds(found[m]) if m in found else None for m in TIMES},
            "models": sorted((m for m in models if m["share"] > 0),
                             key=lambda m: (-m["share"], m["model"])),
        }
    return {"updated": day.isoformat() if day else None, "windows": windows}


def latest(conn: psycopg.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "select day, window_days, metric, value, sample_size from daily_metrics"
        " where day = (select max(day) from daily_metrics)").fetchall()
    return public_view(rows[0][0] if rows else None, [r[1:] for r in rows])


@router.get("/api/stats")
def stats() -> Response:
    url = chat.DEPS.database_url()
    if not url:
        return Response(status_code=503, headers={"Cache-Control": "no-store"})
    try:
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
            body = latest(conn)
    except psycopg.Error as e:
        log.error("stats failed: %s", type(e).__name__)
        return Response(status_code=503, headers={"Cache-Control": "no-store"})
    return JSONResponse(body, headers={"Cache-Control": CACHE})

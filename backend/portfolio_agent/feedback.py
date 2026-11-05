"""POST /api/feedback: 👍 or 👎 on one answer, with an optional comment (US-2.7;
docs/05-architecture.md, section 6).

- Only the visitor who got the answer may rate it: the signed cookie must match the answer's
  conversation. Anything else is a 404, the same as an answer that does not exist, so the
  endpoint cannot tell anyone which message ids are real.
- One rating per answer, and the last one counts: 👎 is saved at once and its comment may come
  in a second request. 👍 clears a comment and the challenge mark.
- The comment is masked like the traces (US-12.3), and cut to 300 characters after masking.
- A visitor may send `feedback_day` of these a day (quotas.Limits); after that, a 429.

Settings come from chat.DEPS, so the tests point both endpoints at the same database.
"""

from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from portfolio_agent import chat, tracing
from portfolio_agent.db import feedback as db
from portfolio_agent.guards import visitor
from portfolio_agent.guards.quotas import bump

router = APIRouter()

MAX_COMMENT = 300


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)
    challenge: bool = False


def _clean(req: FeedbackRequest) -> tuple[str | None, bool]:
    if req.rating == "up":
        return None, False
    comment = (req.comment or "").strip()
    return (tracing.mask(comment)[:MAX_COMMENT] or None), req.challenge


@router.post("/api/feedback", status_code=204)
def feedback(req: FeedbackRequest, request: Request) -> Response:
    visitor_id = visitor.read_cookie(request.cookies.get(visitor.COOKIE))
    if visitor_id is None:  # no cookie, no answers of one's own to rate
        return Response(status_code=404)
    deps = chat.DEPS
    url = deps.database_url()
    if not url:
        return Response(status_code=503)
    comment, challenge = _clean(req)
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        if bump(conn, "feedback", visitor_id, deps.now().date()) > deps.limits().feedback_day:
            return Response(status_code=429)
        saved = db.save(conn, message_id=req.message_id, visitor_id=visitor_id,
                        rating=req.rating, comment=comment, challenge=challenge)
    return Response(status_code=204 if saved else 404)

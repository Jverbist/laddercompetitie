import hmac
from datetime import timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db import SessionLocal
from app.models import Challenge, User

router = APIRouter()


@router.get("/feed/{token}.xml")
def challenge_feed(token: str, request: Request):
    expected = settings.rss_feed_token
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=404)
    challenger, challenged = aliased(User), aliased(User)
    with SessionLocal() as db:
        rows = db.execute(
            select(Challenge, challenger.name, challenged.name)
            .join(challenger, Challenge.challenger_id == challenger.id)
            .join(challenged, Challenge.challenged_id == challenged.id)
            .order_by(Challenge.id.desc())
            .limit(30)
        ).all()
    base = f"{request.url.scheme}://{request.url.netloc}"
    items = []
    for challenge, a, b in rows:
        created = challenge.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        title = escape(f"{a} (#{challenge.challenger_rank_at_creation}) daagt {b} (#{challenge.challenged_rank_at_creation}) uit")
        items.append(
            f"<item><title>{title}</title><link>{base}/dashboard</link>"
            f'<guid isPermaLink="false">challenge-{challenge.id}</guid>'
            f"<pubDate>{format_datetime(created)}</pubDate></item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>Laddercompetitie uitdagingen</title><link>{base}/dashboard</link>"
        "<description>Nieuwe uitdagingen</description>" + "".join(items) + "</channel></rss>"
    )
    return Response(xml, media_type="application/rss+xml")

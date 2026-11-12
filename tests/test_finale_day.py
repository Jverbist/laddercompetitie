from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import hash_password
from app.models import Game, User
from app.services.competition import challenge_duration, create_challenge


def setup_finale(db, players=9):
    users = [User(name=f"P{i}", email=f"p{i}@example.com", rank=i, password_hash=hash_password("x" * 12)) for i in range(1, players + 1)]
    db.add_all([*users, Game(name="G1")])
    db.commit()
    return users, None


def test_finale_challenge_duration_and_cutoff(db):
    users, _ = setup_finale(db)
    inside = settings.finale_qualification_start + timedelta(minutes=5)
    assert challenge_duration(inside) == timedelta(minutes=15)
    assert challenge_duration(inside - timedelta(days=30)) == timedelta(days=2)
    challenge = create_challenge(db, challenger_id=users[1].id, challenged_id=users[0].id, now=inside)
    assert challenge.deadline_at == inside + timedelta(minutes=15)
    with pytest.raises(HTTPException):
        create_challenge(db, challenger_id=users[3].id, challenged_id=users[2].id, now=settings.finale_qualification_end)


def test_finale_announcement_window():
    assert not settings.finale_announcement_active(settings.finale_announce_start - timedelta(seconds=1))
    assert settings.finale_announcement_active(settings.finale_announce_start)
    assert not settings.finale_announcement_active(settings.finale_bracket_start)


def test_finale_day_only_top_ten_can_play(db):
    users, _ = setup_finale(db, players=12)
    inside = settings.finale_qualification_start + timedelta(minutes=5)
    with pytest.raises(HTTPException):
        create_challenge(db, challenger_id=users[10].id, challenged_id=users[8].id, now=inside)
    with pytest.raises(HTTPException):
        create_challenge(db, challenger_id=users[10].id, challenged_id=users[9].id, now=inside)
    create_challenge(db, challenger_id=users[9].id, challenged_id=users[8].id, now=inside)

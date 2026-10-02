from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import ChallengeStatus, Game, User
from app.core.security import hash_password
from app.services.competition import (
    confirm_result,
    create_challenge,
    expire_overdue_challenges,
    is_available,
    submit_result,
)

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


def add_players(db):
    players = [
        User(name="Amber", email="amber@example.com", rank=1, password_hash=hash_password("correct-horse-battery")),
        User(name="John", email="john@example.com", rank=3, password_hash=hash_password("correct-horse-battery")),
        User(name="Noor", email="noor@example.com", rank=8, password_hash=hash_password("correct-horse-battery")),
    ]
    game = Game(name="Pool")
    db.add_all([*players, game])
    db.commit()
    return players, game


def test_challenger_win_swaps_only_two_ranks(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(
        db, challenger_id=john.id, challenged_id=amber.id, game_id=game.id, now=NOW
    )
    submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=john.id)
    confirm_result(db, challenge_id=challenge.id, confirmer_id=amber.id, now=NOW)
    db.commit()

    assert (john.rank, amber.rank) == (1, 3)
    assert challenge.status is ChallengeStatus.COMPLETED


def test_challenger_loss_keeps_ranking(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(
        db, challenger_id=john.id, challenged_id=amber.id, game_id=game.id, now=NOW
    )
    submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=amber.id)
    confirm_result(db, challenge_id=challenge.id, confirmer_id=john.id, now=NOW)
    db.commit()

    assert (amber.rank, john.rank) == (1, 3)


def test_active_challenge_makes_both_players_unavailable(db):
    (amber, john, _), game = add_players(db)
    create_challenge(db, challenger_id=john.id, challenged_id=amber.id, game_id=game.id, now=NOW)

    assert not is_available(db, amber)
    assert not is_available(db, john)


def test_only_five_places_above_may_be_challenged(db):
    (amber, _, noor), game = add_players(db)

    with pytest.raises(HTTPException, match="one to five"):
        create_challenge(db, challenger_id=noor.id, challenged_id=amber.id, game_id=game.id, now=NOW)


def test_expired_challenge_is_forfeit_and_swaps_ranks(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(
        db, challenger_id=john.id, challenged_id=amber.id, game_id=game.id, now=NOW
    )
    expired = expire_overdue_challenges(db, now=NOW + timedelta(days=2))
    db.commit()

    assert expired == [challenge]
    assert challenge.status is ChallengeStatus.FORFEIT
    assert (john.rank, amber.rank) == (1, 3)

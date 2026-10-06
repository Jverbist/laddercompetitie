from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import ChallengeStatus, Game, User
from app.core.security import hash_password
from app.services.competition import (
    choose_game,
    confirm_result,
    cooldown_opponent_ids,
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
        db, challenger_id=john.id, challenged_id=amber.id, now=NOW
    )
    choose_game(db, challenge_id=challenge.id, chooser_id=amber.id, game_id=game.id)
    submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=john.id)
    confirm_result(db, challenge_id=challenge.id, confirmer_id=amber.id, now=NOW)
    db.commit()

    assert (john.rank, amber.rank) == (1, 3)
    assert challenge.status is ChallengeStatus.COMPLETED


def test_challenger_loss_keeps_ranking(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(
        db, challenger_id=john.id, challenged_id=amber.id, now=NOW
    )
    choose_game(db, challenge_id=challenge.id, chooser_id=amber.id, game_id=game.id)
    submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=amber.id)
    confirm_result(db, challenge_id=challenge.id, confirmer_id=john.id, now=NOW)
    db.commit()

    assert (amber.rank, john.rank) == (1, 3)


def test_active_challenge_makes_both_players_unavailable(db):
    (amber, john, _), game = add_players(db)
    create_challenge(db, challenger_id=john.id, challenged_id=amber.id, now=NOW)

    assert not is_available(db, amber)
    assert not is_available(db, john)


def test_only_five_places_above_may_be_challenged(db):
    (amber, _, noor), game = add_players(db)

    with pytest.raises(HTTPException, match="one to five"):
        create_challenge(db, challenger_id=noor.id, challenged_id=amber.id, now=NOW)


def test_expired_challenge_is_forfeit_and_swaps_ranks(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(
        db, challenger_id=john.id, challenged_id=amber.id, now=NOW
    )
    expired = expire_overdue_challenges(db, now=NOW + timedelta(days=2))
    db.commit()

    assert expired == [challenge]
    assert challenge.status is ChallengeStatus.FORFEIT
    assert (john.rank, amber.rank) == (1, 3)


def test_only_challenged_player_may_choose_game_and_result_needs_game(db):
    (amber, john, _), game = add_players(db)
    challenge = create_challenge(db, challenger_id=john.id, challenged_id=amber.id, now=NOW)
    with pytest.raises(HTTPException) as no_game:
        submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=john.id)
    with pytest.raises(HTTPException) as wrong_user:
        choose_game(db, challenge_id=challenge.id, chooser_id=john.id, game_id=game.id)
    choose_game(db, challenge_id=challenge.id, chooser_id=amber.id, game_id=game.id)

    assert no_game.value.status_code == 409
    assert wrong_user.value.status_code == 403
    assert challenge.game_id == game.id


def test_rematch_is_blocked_for_two_turns(db):
    (amber, john, noor), game = add_players(db)
    challenge = create_challenge(db, challenger_id=john.id, challenged_id=amber.id, now=NOW)
    choose_game(db, challenge_id=challenge.id, chooser_id=amber.id, game_id=game.id)
    submit_result(db, challenge_id=challenge.id, submitter_id=john.id, winner_id=amber.id)
    confirm_result(db, challenge_id=challenge.id, confirmer_id=john.id, now=NOW)

    with pytest.raises(HTTPException) as exc:
        create_challenge(db, challenger_id=john.id, challenged_id=amber.id, now=NOW)
    assert exc.value.status_code == 409
    assert amber.id in cooldown_opponent_ids(db, john.id)

    yasmine = User(name="Yasmine", email="yasmine@example.com", rank=7, password_hash=hash_password("correct-horse-battery"))
    db.add(yasmine)
    db.commit()
    for index, challenger in enumerate((noor, yasmine)):
        other = create_challenge(db, challenger_id=challenger.id, challenged_id=john.id, now=NOW)
        choose_game(db, challenge_id=other.id, chooser_id=john.id, game_id=game.id)
        submit_result(db, challenge_id=other.id, submitter_id=challenger.id, winner_id=john.id)
        confirm_result(db, challenge_id=other.id, confirmer_id=challenger.id, now=NOW + timedelta(hours=index + 1))

    assert amber.id not in cooldown_opponent_ids(db, john.id)


def test_registered_user_starts_at_bottom_of_ladder(db):
    from app.services.competition import register_user

    add_players(db)
    newcomer = register_user(db, name="Sam", email="Sam@Example.com", password="correct-horse-battery")

    assert newcomer.rank == 9
    assert newcomer.email == "sam@example.com"
    with pytest.raises(HTTPException) as exc:
        register_user(db, name="Sam", email="sam@example.com", password="correct-horse-battery")
    assert exc.value.status_code == 409

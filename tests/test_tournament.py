from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import hash_password
from app.models import Game, User
from app.services.competition import challenge_duration, create_challenge
from app.services.tournament import (
    admin_set_winner,
    choose_tournament_game,
    confirm_tournament_result,
    start_finale,
    submit_tournament_result,
    try_auto_start,
)


def setup_finale(db, players=9):
    users = [User(name=f"P{i}", email=f"p{i}@example.com", rank=i, password_hash=hash_password("x" * 12)) for i in range(1, players + 1)]
    games = [Game(name=f"G{i}") for i in range(1, 8)]
    db.add_all([*users, *games])
    db.commit()
    return users, games


def test_bracket_pairs_and_game_rules(db):
    users, games = setup_finale(db)
    start = settings.finale_bracket_start
    tournament = start_finale(db, now=start)
    r1 = [m for m in tournament.matches if m.round == 1]
    assert [(m.seed_a, m.seed_b) for m in r1] == [(1, 8), (4, 5), (2, 7), (3, 6)]

    top, other = r1[0], r1[1]
    with pytest.raises(HTTPException):
        choose_tournament_game(db, match_id=top.id, user_id=users[7].id, game_id=games[0].id)
    choose_tournament_game(db, match_id=top.id, user_id=users[0].id, game_id=games[0].id)
    with pytest.raises(HTTPException):
        choose_tournament_game(db, match_id=other.id, user_id=users[3].id, game_id=games[0].id)

    submit_tournament_result(db, match_id=top.id, user_id=users[0].id, winner_id=users[0].id)
    with pytest.raises(HTTPException):
        confirm_tournament_result(db, match_id=top.id, user_id=users[0].id, now=start)
    confirm_tournament_result(db, match_id=top.id, user_id=users[7].id, now=start)

    for match in r1[1:]:
        admin_set_winner(db, match_id=match.id, winner_id=match.player_a_id, now=start)
    semi = [m for m in tournament.matches if m.round == 2]
    assert {semi[0].player_a_id, semi[0].player_b_id} == {users[0].id, users[3].id}
    assert semi[0].status == "active"

    with pytest.raises(HTTPException):
        choose_tournament_game(db, match_id=semi[0].id, user_id=users[0].id, game_id=games[0].id)
    choose_tournament_game(db, match_id=semi[0].id, user_id=users[0].id, game_id=games[1].id)


def test_final_sets_champion_and_start_is_once(db):
    users, _ = setup_finale(db, players=8)
    now = settings.finale_bracket_start
    tournament = start_finale(db, now=now)
    with pytest.raises(HTTPException):
        start_finale(db, now=now)
    for round_number in (1, 2, 3):
        for match in [m for m in tournament.matches if m.round == round_number]:
            admin_set_winner(db, match_id=match.id, winner_id=match.player_a_id, now=now)
    assert tournament.champion_id == users[0].id


def test_auto_start_window_and_too_few_players(db):
    setup_finale(db, players=8)
    assert not try_auto_start(db, settings.finale_bracket_start - timedelta(minutes=1))
    assert try_auto_start(db, settings.finale_bracket_start)
    assert not try_auto_start(db, settings.finale_bracket_start)


def test_finale_challenge_duration_and_cutoff(db):
    users, _ = setup_finale(db)
    inside = settings.finale_qualification_start + timedelta(minutes=5)
    assert challenge_duration(inside) == timedelta(minutes=15)
    assert challenge_duration(inside - timedelta(days=30)) == timedelta(days=2)
    challenge = create_challenge(db, challenger_id=users[1].id, challenged_id=users[0].id, now=inside)
    assert challenge.deadline_at == inside + timedelta(minutes=15)
    with pytest.raises(HTTPException):
        create_challenge(db, challenger_id=users[3].id, challenged_id=users[2].id, now=settings.finale_qualification_end)

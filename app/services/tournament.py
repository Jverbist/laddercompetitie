"""Finale: everyone plays for the top 8, then a knockout bracket (1v8, 4v5, 2v7, 3v6)."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Challenge, ChallengeStatus, Game, Tournament, TournamentMatch, User
from app.services.competition import OPEN_CHALLENGE_STATUSES, expire_overdue_challenges

TOURNAMENT_ID = 1
BRACKET_SIZE = 8
ROUND_NAMES = {1: "Kwartfinale", 2: "Halve finale", 3: "Finale"}
# Seeds per round-1 slot; slots 0+1 feed semi 0, slots 2+3 feed semi 1.
FIRST_ROUND_PAIRS = ((1, 8), (4, 5), (2, 7), (3, 6))
AUTO_START_GRACE = timedelta(hours=6)


def get_tournament(db: Session) -> Tournament | None:
    return db.get(Tournament, TOURNAMENT_ID)


def auto_start_due(db: Session, now: datetime) -> bool:
    start = settings.finale_bracket_start
    return start <= now < start + AUTO_START_GRACE and get_tournament(db) is None


def start_finale(db: Session, *, now: datetime) -> Tournament:
    if get_tournament(db) is not None:
        raise HTTPException(status_code=409, detail="De finale is al gestart.")
    expire_overdue_challenges(db, now=now)
    for challenge in db.scalars(select(Challenge).where(Challenge.status.in_(OPEN_CHALLENGE_STATUSES))):
        challenge.status = ChallengeStatus.CANCELLED
        challenge.completed_at = now
    top = list(
        db.scalars(
            select(User).where(User.is_active, User.is_blocked.is_(False), User.rank > 0).order_by(User.rank).limit(BRACKET_SIZE)
        )
    )
    if len(top) < BRACKET_SIZE:
        raise HTTPException(status_code=409, detail=f"Er zijn minstens {BRACKET_SIZE} spelers nodig voor de finale.")

    tournament = Tournament(id=TOURNAMENT_ID, started_at=now)
    db.add(tournament)
    db.flush()
    for slot, (high, low) in enumerate(FIRST_ROUND_PAIRS):
        a, b = top[high - 1], top[low - 1]
        db.add(TournamentMatch(
            tournament_id=tournament.id, round=1, slot=slot,
            player_a_id=a.id, player_b_id=b.id, seed_a=high, seed_b=low, status="active",
        ))
    for round_number, slots in ((2, 2), (3, 1)):
        for slot in range(slots):
            db.add(TournamentMatch(tournament_id=tournament.id, round=round_number, slot=slot))
    db.flush()
    return tournament


def try_auto_start(db: Session, now: datetime) -> bool:
    """Start the finale at the scheduled time. Safe to call from several workers."""
    if not auto_start_due(db, now):
        return False
    try:
        with db.begin_nested():
            start_finale(db, now=now)
    except IntegrityError:
        return False
    except HTTPException:
        return False
    db.commit()
    return True


def _match(db: Session, match_id: int) -> TournamentMatch:
    match = db.scalar(select(TournamentMatch).where(TournamentMatch.id == match_id).with_for_update())
    if match is None:
        raise HTTPException(status_code=404, detail="Wedstrijd niet gevonden.")
    return match


def _earlier_picks(db: Session, match: TournamentMatch, user_id: int) -> set[int]:
    earlier = db.scalars(
        select(TournamentMatch).where(
            TournamentMatch.tournament_id == match.tournament_id,
            TournamentMatch.round < match.round,
            TournamentMatch.game_id.is_not(None),
        )
    )
    return {m.game_id for m in earlier if m.chooser_id == user_id}


def _round_games(db: Session, match: TournamentMatch) -> set[int]:
    taken = db.scalars(
        select(TournamentMatch.game_id).where(
            TournamentMatch.tournament_id == match.tournament_id,
            TournamentMatch.round == match.round,
            TournamentMatch.id != match.id,
            TournamentMatch.game_id.is_not(None),
        )
    )
    return set(taken)


def available_games(db: Session, match: TournamentMatch) -> list[Game]:
    blocked = _round_games(db, match)
    if match.chooser_id is not None:
        blocked |= _earlier_picks(db, match, match.chooser_id)
    games = db.scalars(select(Game).where(Game.is_active).order_by(Game.name))
    return [game for game in games if game.id not in blocked]


def choose_tournament_game(db: Session, *, match_id: int, user_id: int, game_id: int, is_admin: bool = False) -> TournamentMatch:
    match = _match(db, match_id)
    if match.status != "active" or match.game_id is not None:
        raise HTTPException(status_code=409, detail="Voor deze wedstrijd kan geen spel meer gekozen worden.")
    if not is_admin and user_id != match.chooser_id:
        raise HTTPException(status_code=403, detail="Enkel de hoogst geplaatste speler kiest het spel.")
    if game_id not in {game.id for game in available_games(db, match)}:
        raise HTTPException(
            status_code=409,
            detail="Dit spel is niet beschikbaar: het wordt al gespeeld in deze ronde of de kiezer koos het in een vorige ronde.",
        )
    match.game_id = game_id
    db.flush()
    return match


def submit_tournament_result(db: Session, *, match_id: int, user_id: int, winner_id: int) -> TournamentMatch:
    match = _match(db, match_id)
    players = (match.player_a_id, match.player_b_id)
    if match.status != "active":
        raise HTTPException(status_code=409, detail="Voor deze wedstrijd kan geen resultaat ingevoerd worden.")
    if user_id not in players:
        raise HTTPException(status_code=403, detail="Enkel de spelers van deze wedstrijd kunnen het resultaat invoeren.")
    if match.game_id is None:
        raise HTTPException(status_code=409, detail="Er is nog geen spel gekozen.")
    if winner_id not in players:
        raise HTTPException(status_code=422, detail="De winnaar moet een speler van deze wedstrijd zijn.")
    match.proposed_winner_id = winner_id
    match.status = "result_pending"
    db.flush()
    return match


def confirm_tournament_result(db: Session, *, match_id: int, user_id: int, now: datetime) -> TournamentMatch:
    match = _match(db, match_id)
    if match.status != "result_pending":
        raise HTTPException(status_code=409, detail="Er is geen resultaat om te bevestigen.")
    if user_id not in (match.player_a_id, match.player_b_id):
        raise HTTPException(status_code=403, detail="Enkel de spelers van deze wedstrijd kunnen bevestigen.")
    if user_id == match.proposed_winner_id:
        raise HTTPException(status_code=403, detail="De andere speler moet dit resultaat bevestigen.")
    _finish_match(db, match, match.proposed_winner_id, now)
    return match


def admin_set_winner(db: Session, *, match_id: int, winner_id: int, now: datetime) -> TournamentMatch:
    match = _match(db, match_id)
    if match.status not in ("active", "result_pending"):
        raise HTTPException(status_code=409, detail="Deze wedstrijd is niet actief.")
    if winner_id not in (match.player_a_id, match.player_b_id):
        raise HTTPException(status_code=422, detail="De winnaar moet een speler van deze wedstrijd zijn.")
    _finish_match(db, match, winner_id, now)
    return match


def _finish_match(db: Session, match: TournamentMatch, winner_id: int, now: datetime) -> None:
    match.winner_id = winner_id
    match.proposed_winner_id = winner_id
    match.status = "completed"
    winner_seed = match.seed_a if winner_id == match.player_a_id else match.seed_b
    tournament = match.tournament
    if match.round == 3:
        tournament.champion_id = winner_id
        tournament.finished_at = now
        db.flush()
        return
    target = db.scalar(select(TournamentMatch).where(
        TournamentMatch.tournament_id == match.tournament_id,
        TournamentMatch.round == match.round + 1,
        TournamentMatch.slot == match.slot // 2,
    ))
    if match.slot % 2 == 0:
        target.player_a_id, target.seed_a = winner_id, winner_seed
    else:
        target.player_b_id, target.seed_b = winner_id, winner_seed
    if target.player_a_id and target.player_b_id:
        target.status = "active"
    db.flush()

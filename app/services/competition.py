from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.models import Challenge, ChallengeStatus, Game, User

CHALLENGE_DURATION = timedelta(days=2)
OPEN_CHALLENGE_STATUSES = (ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING)
FINISHED_CHALLENGE_STATUSES = (ChallengeStatus.COMPLETED, ChallengeStatus.FORFEIT)
REMATCH_COOLDOWN_TURNS = 2


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity} not found.")


def _open_challenge_for_user(user_id: int) -> Select[tuple[Challenge]]:
    return select(Challenge).where(
        Challenge.status.in_(OPEN_CHALLENGE_STATUSES),
        or_(Challenge.challenger_id == user_id, Challenge.challenged_id == user_id),
    )


def is_available(db: Session, user: User) -> bool:
    return user.is_active and not user.is_blocked and db.scalar(_open_challenge_for_user(user.id)) is None


def cooldown_opponent_ids(db: Session, user_id: int) -> set[int]:
    """Opponents from the user's last finished challenges who may not be challenged yet."""
    recent = db.scalars(
        select(Challenge)
        .where(
            Challenge.status.in_(FINISHED_CHALLENGE_STATUSES),
            or_(Challenge.challenger_id == user_id, Challenge.challenged_id == user_id),
        )
        .order_by(Challenge.completed_at.desc(), Challenge.id.desc())
        .limit(REMATCH_COOLDOWN_TURNS)
    )
    return {
        item.challenged_id if item.challenger_id == user_id else item.challenger_id for item in recent
    }


def create_challenge(db: Session, *, challenger_id: int, challenged_id: int, now: datetime) -> Challenge:
    if challenger_id == challenged_id:
        raise HTTPException(status_code=422, detail="You cannot challenge yourself.")

    challenger = db.scalar(select(User).where(User.id == challenger_id).with_for_update())
    challenged = db.scalar(select(User).where(User.id == challenged_id).with_for_update())
    if challenger is None or challenged is None:
        raise _not_found("Participant")
    if not is_available(db, challenger):
        raise HTTPException(status_code=409, detail="You are not available for a new challenge.")
    if not is_available(db, challenged):
        raise HTTPException(status_code=409, detail="This participant is already unavailable.")

    rank_distance = challenger.rank - challenged.rank
    if not 1 <= rank_distance <= 5:
        raise HTTPException(
            status_code=422,
            detail="You may only challenge a participant ranked one to five places above you.",
        )

    if challenged.id in cooldown_opponent_ids(db, challenger.id):
        raise HTTPException(
            status_code=409,
            detail=f"You must play {REMATCH_COOLDOWN_TURNS} other matches before challenging this participant again.",
        )

    challenge = Challenge(
        challenger_id=challenger.id,
        challenged_id=challenged.id,
        challenger_rank_at_creation=challenger.rank,
        challenged_rank_at_creation=challenged.rank,
        deadline_at=now + CHALLENGE_DURATION,
    )
    db.add(challenge)
    db.flush()
    return challenge


def choose_game(db: Session, *, challenge_id: int, chooser_id: int, game_id: int) -> Challenge:
    challenge = db.scalar(select(Challenge).where(Challenge.id == challenge_id).with_for_update())
    if challenge is None:
        raise _not_found("Challenge")
    if challenge.challenged_id != chooser_id:
        raise HTTPException(status_code=403, detail="Only the challenged participant can choose the game.")
    if challenge.status is not ChallengeStatus.ACTIVE or challenge.game_id is not None:
        raise HTTPException(status_code=409, detail="The game can no longer be chosen for this challenge.")
    game = db.scalar(select(Game).where(Game.id == game_id))
    if game is None or not game.is_active:
        raise HTTPException(status_code=422, detail="This game is not available.")
    challenge.game_id = game.id
    db.flush()
    return challenge


def submit_result(db: Session, *, challenge_id: int, submitter_id: int, winner_id: int) -> Challenge:
    challenge = db.scalar(select(Challenge).where(Challenge.id == challenge_id).with_for_update())
    if challenge is None:
        raise _not_found("Challenge")
    if challenge.status is not ChallengeStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="This challenge can no longer receive a result.")
    if submitter_id not in (challenge.challenger_id, challenge.challenged_id):
        raise HTTPException(status_code=403, detail="Only participants in this challenge can submit a result.")
    if challenge.game_id is None:
        raise HTTPException(status_code=409, detail="The challenged participant must choose a game first.")
    if winner_id not in (challenge.challenger_id, challenge.challenged_id):
        raise HTTPException(status_code=422, detail="The winner must be a participant in this challenge.")

    challenge.proposed_winner_id = winner_id
    challenge.status = ChallengeStatus.RESULT_PENDING
    db.flush()
    return challenge


def confirm_result(
    db: Session, *, challenge_id: int, confirmer_id: int, now: datetime
) -> Challenge:
    challenge = db.scalar(select(Challenge).where(Challenge.id == challenge_id).with_for_update())
    if challenge is None:
        raise _not_found("Challenge")
    if challenge.status is not ChallengeStatus.RESULT_PENDING:
        raise HTTPException(status_code=409, detail="There is no pending result to confirm.")
    if confirmer_id not in (challenge.challenger_id, challenge.challenged_id):
        raise HTTPException(status_code=403, detail="Only participants in this challenge can confirm a result.")
    if challenge.proposed_winner_id == confirmer_id:
        raise HTTPException(status_code=403, detail="The other participant must confirm this result.")

    _complete_challenge(db, challenge, challenge.proposed_winner_id, ChallengeStatus.COMPLETED, now)
    return challenge


def expire_overdue_challenges(db: Session, *, now: datetime) -> list[Challenge]:
    overdue = list(
        db.scalars(
            select(Challenge)
            .where(Challenge.status.in_(OPEN_CHALLENGE_STATUSES), Challenge.deadline_at <= now)
            .with_for_update()
        )
    )
    for challenge in overdue:
        _complete_challenge(db, challenge, challenge.challenger_id, ChallengeStatus.FORFEIT, now)
    return overdue


def _complete_challenge(
    db: Session,
    challenge: Challenge,
    winner_id: int | None,
    final_status: ChallengeStatus,
    now: datetime,
) -> None:
    if winner_id is None:
        raise ValueError("A completed challenge requires a winner.")

    challenge.confirmed_winner_id = winner_id
    challenge.status = final_status
    challenge.completed_at = now

    if winner_id == challenge.challenger_id:
        challenger = db.scalar(select(User).where(User.id == challenge.challenger_id).with_for_update())
        challenged = db.scalar(select(User).where(User.id == challenge.challenged_id).with_for_update())
        if challenger is None or challenged is None:
            raise RuntimeError("Challenge refers to a missing participant.")
        challenger_rank = challenger.rank
        challenged_rank = challenged.rank
        # Rank is unique, so make the first position temporarily free before swapping.
        challenger.rank = -challenger.id
        db.flush()
        challenged.rank = challenger_rank
        db.flush()
        challenger.rank = challenged_rank
    db.flush()

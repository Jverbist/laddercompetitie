from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Challenge, ChallengeStatus, User


@dataclass
class PlayerStats:
    user: User
    wins: int = 0
    losses: int = 0
    current_streak: int = 0
    best_streak: int = 0
    climbed: int = 0


@dataclass
class Scoreboard:
    podium: list[User] = field(default_factory=list)
    most_wins: list[PlayerStats] = field(default_factory=list)
    streaks: list[PlayerStats] = field(default_factory=list)
    climbers: list[PlayerStats] = field(default_factory=list)
    recent: list[Challenge] = field(default_factory=list)
    played: int = 0


def build_scoreboard(db: Session, *, limit: int = 5) -> Scoreboard:
    users = list(db.scalars(select(User).where(User.is_active).order_by(User.rank)))
    stats = {user.id: PlayerStats(user=user) for user in users}
    finished = list(
        db.scalars(
            select(Challenge)
            .where(
                Challenge.status.in_((ChallengeStatus.COMPLETED, ChallengeStatus.FORFEIT)),
                Challenge.confirmed_winner_id.is_not(None),
            )
            .order_by(Challenge.completed_at, Challenge.id)
        )
    )

    for challenge in finished:
        winner_id = challenge.confirmed_winner_id
        if winner_id == challenge.challenger_id and winner_id in stats:
            stats[winner_id].climbed += max(
                0, challenge.challenger_rank_at_creation - challenge.challenged_rank_at_creation
            )
        # Forfeits move ranks but are not real games, so they don't count for wins or streaks.
        if challenge.status is not ChallengeStatus.COMPLETED:
            continue
        loser_id = challenge.challenged_id if winner_id == challenge.challenger_id else challenge.challenger_id
        if winner_id in stats:
            winner = stats[winner_id]
            winner.wins += 1
            winner.current_streak += 1
            winner.best_streak = max(winner.best_streak, winner.current_streak)
        if loser_id in stats:
            stats[loser_id].losses += 1
            stats[loser_id].current_streak = 0

    players = list(stats.values())
    played = [c for c in finished if c.status is ChallengeStatus.COMPLETED]
    return Scoreboard(
        podium=users[:3],
        most_wins=sorted((p for p in players if p.wins), key=lambda p: (-p.wins, p.user.rank))[:limit],
        streaks=sorted(
            (p for p in players if p.best_streak),
            key=lambda p: (-p.current_streak, -p.best_streak, p.user.rank),
        )[:limit],
        climbers=sorted((p for p in players if p.climbed), key=lambda p: (-p.climbed, p.user.rank))[:limit],
        recent=list(reversed(played))[:8],
        played=len(played),
    )

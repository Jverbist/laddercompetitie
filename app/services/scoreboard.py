from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Challenge, ChallengeStatus, CheaterClick, User


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
    players: int = 0
    open_challenges: int = 0
    best_streak: int = 0
    games: list[dict] = field(default_factory=list)
    daily: list[dict] = field(default_factory=list)
    cheaters: list[CheaterClick] = field(default_factory=list)


GAME_COLORS = ("#ff9933", "#44d39d", "#4cc3ff", "#b388ff", "#ff6b8a", "#ffd166", "#7bdff2")


def _game_segments(played: list[Challenge]) -> list[dict]:
    counts = Counter(c.game.name if c.game else "Onbekend" for c in played)
    total = sum(counts.values())
    segments, offset = [], 0.0
    for index, (name, count) in enumerate(counts.most_common()):
        pct = count / total * 100
        segments.append({"name": name, "count": count, "pct": round(pct), "dash": round(pct, 2), "offset": round(25 - offset, 2), "color": GAME_COLORS[index % len(GAME_COLORS)]})
        offset += pct
    return segments


def _daily_activity(played: list[Challenge], days: int = 14) -> list[dict]:
    dated = [c.completed_at.date() for c in played if c.completed_at]
    if not dated:
        return []
    last = max(dated)
    counts = Counter(dated)
    series = [last - timedelta(days=days - 1 - i) for i in range(days)]
    peak = max(counts[d] for d in series) or 1
    return [{"label": f"{d.day}/{d.month}", "count": counts[d], "height": round(counts[d] / peak * 100)} for d in series]


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
        players=len(users),
        open_challenges=db.scalar(select(func.count()).select_from(Challenge).where(Challenge.status.in_((ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING)))) or 0,
        best_streak=max((p.current_streak for p in players), default=0),
        games=_game_segments(played),
        daily=_daily_activity(played),
        cheaters=list(db.scalars(select(CheaterClick).order_by(CheaterClick.first_clicked_at))),
    )

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
    forfeits: int = 0
    loss_streak: int = 0
    worst_loss_streak: int = 0


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
    titles: list[dict] = field(default_factory=list)


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


def _award_titles(users: list[User], players: list[PlayerStats]) -> list[dict]:
    """Fun titles; every title has one holder and ties go to the better ranked player."""
    titles: list[dict] = []

    def award(icon: str, title: str, joke: str, candidates, key, detail) -> None:
        pool = [p for p in candidates if key(p) > 0]
        if not pool:
            return
        holder = max(pool, key=lambda p: (key(p), -p.user.rank))
        titles.append({"icon": icon, "title": title, "joke": joke, "name": holder.user.name, "detail": detail(holder)})

    if users:
        titles.append({"icon": "👑", "title": "De Kroonprins", "joke": "Staat bovenaan en weet het.", "name": users[0].name, "detail": "rang 1"})
    if len(users) > 1:
        titles.append({"icon": "🥈", "title": "Eeuwige tweede", "joke": "Dichterbij dan ooit, maar net niet.", "name": users[1].name, "detail": "rang 2"})
    award("🔥", "Onverslaanbaar", "Niemand kan hem of haar nog stoppen.", players, lambda p: p.current_streak if p.current_streak >= 2 else 0, lambda p: f"{p.current_streak} wins op rij")
    award("🏳️", "Forfeit-koning", "Als opgeven een sport was.", players, lambda p: p.forfeits, lambda p: f"{p.forfeits}x opgegeven of niet komen opdagen")
    award("🤕", "Pechvogel", "De ladder zit even tegen.", players, lambda p: p.loss_streak if p.loss_streak >= 2 else 0, lambda p: f"{p.loss_streak} verliespartijen op rij")
    award("🧗", "Klimaap", "Altijd omhoog, nooit tevreden.", players, lambda p: p.climbed, lambda p: f"{p.climbed} plaatsen gestegen")
    award("🎮", "Gamer van het kantoor", "Heeft duidelijk geen deadlines.", players, lambda p: p.wins + p.losses if p.wins + p.losses >= 2 else 0, lambda p: f"{p.wins + p.losses} partijen gespeeld")
    return titles


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
            forfeiter_id = challenge.challenged_id if winner_id == challenge.challenger_id else challenge.challenger_id
            if forfeiter_id in stats:
                stats[forfeiter_id].forfeits += 1
            continue
        loser_id = challenge.challenged_id if winner_id == challenge.challenger_id else challenge.challenger_id
        if winner_id in stats:
            winner = stats[winner_id]
            winner.wins += 1
            winner.current_streak += 1
            winner.best_streak = max(winner.best_streak, winner.current_streak)
            winner.loss_streak = 0
        if loser_id in stats:
            loser = stats[loser_id]
            loser.losses += 1
            loser.current_streak = 0
            loser.loss_streak += 1
            loser.worst_loss_streak = max(loser.worst_loss_streak, loser.loss_streak)

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
        titles=_award_titles(users, players),
        cheaters=list(db.scalars(select(CheaterClick).order_by(CheaterClick.first_clicked_at))),
    )

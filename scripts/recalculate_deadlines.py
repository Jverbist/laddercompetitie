"""Recalculate deadlines of open challenges with the weekend pause (Friday 18:00 - Monday 08:00).

Safe to run more than once: the deadline is always derived from the challenge creation time.
"""

from datetime import UTC

from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models import Challenge, ChallengeStatus
from app.services.competition import CHALLENGE_DURATION
from app.services.worktime import add_working_time


def main() -> None:
    tz = settings.qualification_deadline.tzinfo
    with SessionLocal.begin() as db:
        open_challenges = db.scalars(
            select(Challenge).where(Challenge.status.in_((ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING)))
        )
        for challenge in open_challenges:
            created = challenge.created_at.replace(tzinfo=UTC)  # server default stores UTC
            challenge.deadline_at = add_working_time(created, CHALLENGE_DURATION).astimezone(tz)
            print(f"Uitdaging {challenge.id}: nieuwe deadline {challenge.deadline_at:%d/%m/%Y %H:%M}")


if __name__ == "__main__":
    main()

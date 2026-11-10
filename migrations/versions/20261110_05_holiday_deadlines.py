"""Extend open challenge deadlines for the 11 November holiday."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import context, op

from app.core.config import settings
from app.services.worktime import add_working_time

revision = "20261110_05"
down_revision = "20261105_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("The holiday deadline migration requires an online database connection.")
    challenges = sa.table(
        "challenges",
        sa.column("id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("deadline_at", sa.DateTime(timezone=True)),
    )
    tz = ZoneInfo("Europe/Brussels")
    holiday_start = datetime(2026, 11, 11, tzinfo=tz).astimezone(UTC)
    holiday_end = datetime(2026, 11, 12, tzinfo=tz).astimezone(UTC)
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(challenges).where(challenges.c.status.in_(("ACTIVE", "RESULT_PENDING")))
    )
    for row in rows:
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        deadline = row.deadline_at if row.deadline_at.tzinfo else row.deadline_at.replace(
            tzinfo=settings.qualification_deadline.tzinfo
        )
        overlap = min(deadline.astimezone(UTC), holiday_end) - max(created.astimezone(UTC), holiday_start)
        if overlap > timedelta(0):
            extended = add_working_time(deadline, overlap)
            connection.execute(
                challenges.update().where(challenges.c.id == row.id).values(deadline_at=extended)
            )


def downgrade() -> None:
    # Do not shorten deadlines that may have been manually extended since the upgrade.
    pass

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import Base
from app.models import Challenge, ChallengeStatus, User
from app.services.worktime import add_working_time, is_paused, paused_until, working_seconds_between

BRUSSELS = ZoneInfo("Europe/Brussels")


def test_holiday_pauses_clock_for_whole_local_day():
    tuesday = datetime(2026, 11, 10, 10, tzinfo=BRUSSELS)
    wednesday = datetime(2026, 11, 11, 0, tzinfo=BRUSSELS)
    thursday = datetime(2026, 11, 12, 0, tzinfo=BRUSSELS)
    assert not is_paused(wednesday - timedelta(seconds=1))
    assert is_paused(wednesday)
    assert not is_paused(thursday)
    assert paused_until(wednesday) == thursday
    assert add_working_time(tuesday, timedelta(hours=48)) == datetime(2026, 11, 13, 10, tzinfo=BRUSSELS)
    assert add_working_time(wednesday + timedelta(hours=12), timedelta(hours=2)) == thursday + timedelta(hours=2)
    assert working_seconds_between(tuesday, thursday + timedelta(hours=1)) == 15 * 3600


def test_migration_extends_only_open_deadlines_once_and_preserves_extension(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'holiday.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([
            User(id=1, name="A", email="a@example.com", rank=1, password_hash="x"),
            User(id=2, name="B", email="b@example.com", rank=2, password_hash="x"),
        ])
        db.add_all([
            Challenge(id=1, challenger_id=2, challenged_id=1, challenger_rank_at_creation=2,
                      challenged_rank_at_creation=1, status=ChallengeStatus.ACTIVE,
                      created_at=datetime(2026, 11, 10, 9, tzinfo=UTC),
                      deadline_at=datetime(2026, 11, 12, 14)),
            Challenge(id=2, challenger_id=2, challenged_id=1, challenger_rank_at_creation=2,
                      challenged_rank_at_creation=1, status=ChallengeStatus.COMPLETED,
                      created_at=datetime(2026, 11, 10, 8, tzinfo=UTC),
                      deadline_at=datetime(2026, 11, 12, 14)),
        ])
        db.commit()
    monkeypatch.setattr(settings, "database_url", str(engine.url))
    config = Config("alembic.ini")
    config.attributes["connection"] = engine
    command.stamp(config, "20261105_04")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with Session(engine) as db:
        assert db.get(Challenge, 1).deadline_at == datetime(2026, 11, 13, 14)
        assert db.get(Challenge, 2).deadline_at == datetime(2026, 11, 12, 14)
    engine.dispose()

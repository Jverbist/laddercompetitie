import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRole(str, enum.Enum):
    PARTICIPANT = "participant"
    ADMIN = "admin"


class ChallengeStatus(str, enum.Enum):
    ACTIVE = "active"
    RESULT_PENDING = "result_pending"
    COMPLETED = "completed"
    FORFEIT = "forfeit"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.PARTICIPANT)
    rank: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    password_hash: Mapped[str] = mapped_column(String(255))
    must_reset_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    challenges_started: Mapped[list["Challenge"]] = relationship(
        foreign_keys="Challenge.challenger_id", back_populates="challenger"
    )
    challenges_received: Mapped[list["Challenge"]] = relationship(
        foreign_keys="Challenge.challenged_id", back_populates="challenged"
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (UniqueConstraint("challenger_id", "challenged_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    challenged_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    challenger_rank_at_creation: Mapped[int] = mapped_column(Integer)
    challenged_rank_at_creation: Mapped[int] = mapped_column(Integer)
    status: Mapped[ChallengeStatus] = mapped_column(Enum(ChallengeStatus), default=ChallengeStatus.ACTIVE)
    proposed_winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    challenger: Mapped[User] = relationship(foreign_keys=[challenger_id], back_populates="challenges_started")
    challenged: Mapped[User] = relationship(foreign_keys=[challenged_id], back_populates="challenges_received")
    game: Mapped[Game] = relationship()

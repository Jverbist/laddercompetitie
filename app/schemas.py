from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import ChallengeStatus, UserRole


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    rank: int = Field(gt=0)
    password: str = Field(min_length=12, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: UserRole
    rank: int
    is_active: bool
    is_blocked: bool
    must_reset_password: bool


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AdminPasswordReset(BaseModel):
    temporary_password: str = Field(min_length=12, max_length=128)


class UserAccessUpdate(BaseModel):
    is_active: bool | None = None
    is_blocked: bool | None = None


class GameCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class GameRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool


class ChallengeCreate(BaseModel):
    challenged_id: int = Field(gt=0)


class GameChoice(BaseModel):
    game_id: int = Field(gt=0)


class ResultSubmit(BaseModel):
    winner_id: int = Field(gt=0)


class ChallengeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    challenger_id: int
    challenged_id: int
    game_id: int | None
    challenger_rank_at_creation: int
    challenged_rank_at_creation: int
    status: ChallengeStatus
    proposed_winner_id: int | None
    confirmed_winner_id: int | None
    deadline_at: datetime
    created_at: datetime
    completed_at: datetime | None

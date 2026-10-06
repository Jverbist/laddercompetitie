from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, AuthenticatedUser, CurrentUser, DbSession
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import Challenge, ChallengeStatus, Game, User, UserRole
from app.schemas import (
    ChallengeCreate,
    ChallengeRead,
    AdminPasswordReset,
    GameChoice,
    GameCreate,
    GameRead,
    ResultSubmit,
    PasswordChange,
    UserAccessUpdate,
    UserCreate,
    UserRead,
)
from app.services.competition import (
    choose_game,
    confirm_result,
    cooldown_opponent_ids,
    create_challenge,
    expire_overdue_challenges,
    is_available,
    submit_result,
)

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/change-password")
def change_password(payload: PasswordChange, db: DbSession, user: AuthenticatedUser) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=422, detail="The current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    user.must_reset_password = False
    db.commit()
    return {"detail": "Password changed."}


@router.get("/ranking", response_model=list[UserRead])
def ranking(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active).order_by(User.rank)))


@router.get("/ranking/top-10", response_model=list[UserRead])
def top_ten(db: DbSession) -> list[User]:
    return list(db.scalars(select(User).where(User.is_active, User.rank <= 10).order_by(User.rank)))


@router.get("/me", response_model=UserRead)
def my_profile(user: CurrentUser) -> User:
    return user


@router.get("/eligible-opponents", response_model=list[UserRead])
def eligible_opponents(db: DbSession, user: CurrentUser) -> list[User]:
    candidates = db.scalars(
        select(User)
        .where(
            User.is_active,
            User.id != user.id,
            User.rank < user.rank,
            User.rank >= user.rank - 5,
        )
        .order_by(User.rank)
    )
    blocked = cooldown_opponent_ids(db, user.id)
    return [c for c in candidates if c.id not in blocked and is_available(db, c)]


@router.get("/games", response_model=list[GameRead])
def games(db: DbSession) -> list[Game]:
    return list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name)))


@router.post("/challenges", response_model=ChallengeRead, status_code=status.HTTP_201_CREATED)
def start_challenge(payload: ChallengeCreate, db: DbSession, user: CurrentUser) -> Challenge:
    challenge = create_challenge(
        db,
        challenger_id=user.id,
        challenged_id=payload.challenged_id,
        now=datetime.now(settings.qualification_deadline.tzinfo),
    )
    db.commit()
    db.refresh(challenge)
    return challenge


@router.post("/challenges/{challenge_id}/game", response_model=ChallengeRead)
def pick_game(challenge_id: int, payload: GameChoice, db: DbSession, user: CurrentUser) -> Challenge:
    challenge = choose_game(db, challenge_id=challenge_id, chooser_id=user.id, game_id=payload.game_id)
    db.commit()
    db.refresh(challenge)
    return challenge


@router.get("/challenges/active", response_model=list[ChallengeRead])
def active_challenges(db: DbSession, user: CurrentUser) -> list[Challenge]:
    return list(
        db.scalars(
            select(Challenge)
            .where(
                Challenge.status.in_((ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING)),
                (Challenge.challenger_id == user.id) | (Challenge.challenged_id == user.id),
            )
            .order_by(Challenge.deadline_at)
        )
    )


@router.post("/challenges/{challenge_id}/result", response_model=ChallengeRead)
def register_result(challenge_id: int, payload: ResultSubmit, db: DbSession, user: CurrentUser) -> Challenge:
    challenge = submit_result(db, challenge_id=challenge_id, submitter_id=user.id, winner_id=payload.winner_id)
    db.commit()
    db.refresh(challenge)
    return challenge


@router.post("/challenges/{challenge_id}/confirm", response_model=ChallengeRead)
def approve_result(challenge_id: int, db: DbSession, user: CurrentUser) -> Challenge:
    challenge = confirm_result(
        db,
        challenge_id=challenge_id,
        confirmer_id=user.id,
        now=datetime.now(settings.qualification_deadline.tzinfo),
    )
    db.commit()
    db.refresh(challenge)
    return challenge


@router.post("/admin/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def add_user(payload: UserCreate, db: DbSession, _: AdminUser) -> User:
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(status_code=409, detail="A user with this e-mail already exists.")
    if db.scalar(select(User).where(User.rank == payload.rank)):
        raise HTTPException(status_code=409, detail="This rank is already occupied.")
    user = User(
        name=payload.name,
        email=payload.email.lower(),
        rank=payload.rank,
        role=UserRole.ADMIN if payload.email.lower() in settings.admin_email_set else UserRole.PARTICIPANT,
        password_hash=hash_password(payload.password),
        must_reset_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/admin/users", response_model=list[UserRead])
def list_users(db: DbSession, _: AdminUser) -> list[User]:
    return list(db.scalars(select(User).order_by(User.rank)))


@router.patch("/admin/users/{user_id}/access", response_model=UserRead)
def update_user_access(
    user_id: int, payload: UserAccessUpdate, db: DbSession, _: AdminUser
) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_blocked is not None:
        user.is_blocked = payload.is_blocked
    db.commit()
    db.refresh(user)
    return user


@router.post("/admin/users/{user_id}/reset-password", response_model=UserRead)
def reset_user_password(
    user_id: int, payload: AdminPasswordReset, db: DbSession, _: AdminUser
) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.password_hash = hash_password(payload.temporary_password)
    user.must_reset_password = True
    db.commit()
    db.refresh(user)
    return user


@router.post("/admin/games", response_model=GameRead, status_code=status.HTTP_201_CREATED)
def add_game(payload: GameCreate, db: DbSession, _: AdminUser) -> Game:
    game = Game(name=payload.name, description=payload.description)
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


@router.get("/admin/challenges", response_model=list[ChallengeRead])
def list_challenges(db: DbSession, _: AdminUser) -> list[Challenge]:
    return list(db.scalars(select(Challenge).order_by(Challenge.created_at.desc())))


@router.post("/admin/challenges/{challenge_id}/cancel", response_model=ChallengeRead)
def cancel_challenge(challenge_id: int, db: DbSession, _: AdminUser) -> Challenge:
    challenge = db.scalar(select(Challenge).where(Challenge.id == challenge_id))
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found.")
    if challenge.status not in (ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING):
        raise HTTPException(status_code=409, detail="Only an open challenge can be cancelled.")
    challenge.status = ChallengeStatus.CANCELLED
    challenge.completed_at = datetime.now(settings.qualification_deadline.tzinfo)
    db.commit()
    db.refresh(challenge)
    return challenge


@router.post("/admin/process-deadlines", response_model=list[ChallengeRead])
def process_deadlines(db: DbSession, _: AdminUser) -> list[Challenge]:
    challenges = expire_overdue_challenges(
        db, now=datetime.now(settings.qualification_deadline.tzinfo)
    )
    db.commit()
    return challenges

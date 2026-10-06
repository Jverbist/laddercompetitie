from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import authenticated_user
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db import SessionLocal
from app.models import Challenge, ChallengeStatus, Game, User, UserRole
from app.services.competition import (
    choose_game,
    confirm_result,
    cooldown_opponent_ids,
    create_challenge,
    is_available,
    register_user,
    reset_competition,
    submit_result,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _now() -> datetime:
    return datetime.now(settings.qualification_deadline.tzinfo)


def _time_left(deadline: datetime) -> str:
    if deadline.tzinfo is None:
        # SQLite drops the timezone; values were stored in the configured timezone.
        deadline = deadline.replace(tzinfo=settings.qualification_deadline.tzinfo)
    seconds = max(0, int((deadline - _now()).total_seconds()))
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    return f"{days}d {hours}u {seconds // 60}m"


_MONTHS = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december")


def _date_label(value: datetime) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]}"


def _dashboard_data(db, user: User, error: str | None = None) -> dict:
    ranking = list(db.scalars(select(User).where(User.is_active).order_by(User.rank)))
    active = list(db.scalars(select(Challenge).where(
        Challenge.status.in_((ChallengeStatus.ACTIVE, ChallengeStatus.RESULT_PENDING)),
        or_(Challenge.challenger_id == user.id, Challenge.challenged_id == user.id),
    ).order_by(Challenge.deadline_at)))
    history = list(db.scalars(select(Challenge).where(
        or_(Challenge.challenger_id == user.id, Challenge.challenged_id == user.id)
    ).order_by(Challenge.created_at.desc()).limit(5)))
    complete = [item for item in history if item.status in (ChallengeStatus.COMPLETED, ChallengeStatus.FORFEIT)]
    blocked = cooldown_opponent_ids(db, user.id)
    opponents = [candidate for candidate in ranking if user.rank - 5 <= candidate.rank < user.rank and candidate.id not in blocked and is_available(db, candidate)]
    return {
        "user": user, "ranking": ranking, "top_ten": ranking[:10],
        "games": list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name))),
        "active_challenges": active, "history": history, "eligible_opponents": opponents,
        "wins": sum(item.confirmed_winner_id == user.id for item in complete),
        "played": len(complete), "qualification_time": _time_left(settings.qualification_deadline), "end_label": _date_label(settings.qualification_deadline),
        "time_left": {item.id: _time_left(item.deadline_at) for item in active}, "error": error,
    }


def _signed_in(request: Request, db) -> User | RedirectResponse:
    user = authenticated_user(request, db)
    return _redirect("/change-password") if user.must_reset_password else user


@router.get("/")
def home(request: Request):
    return _redirect("/dashboard" if request.session.get("user_id") else "/login")


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "registration_enabled": settings.registration_enabled})


@router.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(request, "login.html", {"error": "Ongeldig e-mailadres of wachtwoord.", "registration_enabled": settings.registration_enabled}, status_code=401)
        request.session["user_id"] = user.id
        return _redirect("/change-password" if user.must_reset_password else "/dashboard")


def _register_page(request: Request, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(request, "register.html", {"error": error}, status_code=status_code)


@router.get("/register")
def register_page(request: Request):
    if not settings.registration_enabled:
        raise HTTPException(status_code=404)
    return _register_page(request)


@router.post("/register")
def register(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    password: str = Form(),
    confirm_password: str = Form(),
):
    if not settings.registration_enabled:
        raise HTTPException(status_code=404)
    email = email.strip().lower()
    domains = settings.registration_domain_set
    if not name.strip() or len(name) > 100 or "@" not in email or len(email) > 255:
        return _register_page(request, "Vul een geldige naam en een geldig e-mailadres in.", 422)
    if domains and email.rsplit("@", 1)[1] not in domains:
        return _register_page(request, "Registratie is enkel mogelijk met een toegelaten e-maildomein.", 422)
    if password != confirm_password or not 12 <= len(password) <= 128:
        return _register_page(request, "Gebruik een wachtwoord van 12 tot 128 tekens en bevestig het correct.", 422)
    try:
        with SessionLocal.begin() as db:
            user = register_user(db, name=name, email=email, password=password, admin_emails=settings.admin_email_set)
            user_id = user.id
    except HTTPException as exception:
        return _register_page(request, exception.detail, exception.status_code)
    except IntegrityError:
        return _register_page(request, "Registratie mislukt, probeer opnieuw.", 409)
    request.session["user_id"] = user_id
    return _redirect("/dashboard")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return _redirect("/login")


@router.get("/change-password")
def password_page(request: Request):
    with SessionLocal() as db:
        return templates.TemplateResponse(request, "change_password.html", {"user": authenticated_user(request, db), "error": None})


@router.post("/change-password")
def change_password_page(request: Request, current_password: str = Form(), new_password: str = Form(), confirm_password: str = Form()):
    with SessionLocal.begin() as db:
        user = authenticated_user(request, db)
        if new_password != confirm_password or len(new_password) < 12 or not verify_password(current_password, user.password_hash):
            return templates.TemplateResponse(request, "change_password.html", {"user": user, "error": "Gebruik een correct huidig wachtwoord en minstens 12 tekens."}, status_code=422)
        user.password_hash, user.must_reset_password = hash_password(new_password), False
    return _redirect("/dashboard")


@router.get("/dashboard")
def dashboard(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        return user if isinstance(user, RedirectResponse) else templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user))


@router.post("/dashboard/challenges")
def start_challenge_page(request: Request, challenged_id: int = Form()):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            create_challenge(db, challenger_id=user.id, challenged_id=challenged_id, now=_now())
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user, exception.detail), status_code=exception.status_code)
    return _redirect("/dashboard?success=Uitdaging+verstuurd")


@router.post("/dashboard/challenges/{challenge_id}/game")
def choose_game_page(request: Request, challenge_id: int, game_id: int = Form()):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            choose_game(db, challenge_id=challenge_id, chooser_id=user.id, game_id=game_id)
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user, exception.detail), status_code=exception.status_code)
    return _redirect("/dashboard?success=Spel+gekozen")


@router.post("/dashboard/challenges/{challenge_id}/result")
def submit_result_page(request: Request, challenge_id: int, winner_id: int = Form()):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            submit_result(db, challenge_id=challenge_id, submitter_id=user.id, winner_id=winner_id)
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user, exception.detail), status_code=exception.status_code)
    return _redirect("/dashboard?success=Resultaat+wacht+op+bevestiging")


@router.post("/dashboard/challenges/{challenge_id}/confirm")
def confirm_result_page(request: Request, challenge_id: int):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            confirm_result(db, challenge_id=challenge_id, confirmer_id=user.id, now=_now())
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user, exception.detail), status_code=exception.status_code)
    return _redirect("/dashboard?success=Resultaat+bevestigd")


@router.get("/regels")
def rules_page(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        games = list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name)))
        return templates.TemplateResponse(request, "rules.html", {"user": user, "games": games, "deadline": settings.qualification_deadline, "end_label": _date_label(settings.qualification_deadline)})


@router.get("/admin")
def admin_console(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        return templates.TemplateResponse(request, "admin.html", {"user": user, "users": list(db.scalars(select(User).order_by(User.rank))), "games": list(db.scalars(select(Game).order_by(Game.name))), "challenges": list(db.scalars(select(Challenge).order_by(Challenge.created_at.desc(), Challenge.id.desc()))), "winners": {u.id: u.name for u in db.scalars(select(User))}, "message": request.query_params.get("success"), "error": request.query_params.get("error")})


@router.post("/admin/reset")
def reset_competition_page(request: Request, confirmation: str = Form()):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        if confirmation.strip() != "RESET":
            return _redirect("/admin?error=Typ+RESET+om+te+bevestigen")
        removed, players = reset_competition(db)
        db.commit()
    return _redirect(f"/admin?success=Competitie+gereset:+{players}+spelers+willekeurig+geplaatst,+{removed}+uitdagingen+verwijderd")

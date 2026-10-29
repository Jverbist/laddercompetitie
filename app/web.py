import secrets
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import qrcode
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import authenticated_user
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db import SessionLocal
from app.models import Challenge, ChallengeStatus, CheaterClick, Game, User, UserRole
from app.services.competition import (
    choose_game,
    confirm_result,
    cooldown_opponent_ids,
    create_challenge,
    admin_resolve_challenge,
    expire_overdue_challenges,
    forfeit_challenge,
    is_available,
    register_user,
    remove_participant,
    reset_competition,
    submit_result,
)
from app.services.worktime import is_paused, working_seconds_between
from app.services.scoreboard import build_scoreboard
from app.services.notifications import send_challenge_notification

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _now() -> datetime:
    return datetime.now(settings.qualification_deadline.tzinfo)


def _ensure_competition_running() -> None:
    now = _now()
    if now < settings.competition_start:
        raise HTTPException(status_code=409, detail=f"De competitie start op {_date_label(settings.competition_start)}.")
    if now > settings.qualification_deadline:
        raise HTTPException(status_code=409, detail="De competitie is afgelopen.")


def _time_left(deadline: datetime, *, working: bool = False) -> str:
    if deadline.tzinfo is None:
        # SQLite drops the timezone; values were stored in the configured timezone.
        deadline = deadline.replace(tzinfo=settings.qualification_deadline.tzinfo)
    now = _now()
    seconds = working_seconds_between(now, deadline) if working else max(0, int((deadline - now).total_seconds()))
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    label = f"{days}d {hours}u {seconds // 60}m"
    return f"{label} (gepauzeerd tot maandag 08:00)" if working and is_paused(now) else label


_MONTHS = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december")


def _date_label(value: datetime) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]}"


def _dashboard_data(db, user: User, error: str | None = None) -> dict:
    if expire_overdue_challenges(db, now=_now()):
        db.commit()
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
    games = list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name)))
    played_per_game = dict(db.execute(
        select(Challenge.game_id, func.count()).where(
            Challenge.status.in_((ChallengeStatus.COMPLETED, ChallengeStatus.FORFEIT)), Challenge.game_id.is_not(None)
        ).group_by(Challenge.game_id)
    ).all())
    return {
        "game_overview": [(game, played_per_game.get(game.id, 0)) for game in games],
        "user": user, "ranking": ranking, "top_ten": ranking[:10],
        "games": list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name))),
        "active_challenges": active, "history": history, "eligible_opponents": opponents,
        "wins": sum(item.confirmed_winner_id == user.id for item in complete),
        "played": len(complete), "qualification_time": _time_left(settings.qualification_deadline), "end_label": _date_label(settings.qualification_deadline),
        "time_left": {item.id: _time_left(item.deadline_at, working=True) for item in active}, "error": error,
    }


def _signed_in(request: Request, db) -> User | RedirectResponse:
    user = authenticated_user(request, db)
    return _redirect("/change-password") if user.must_reset_password else user


@router.get("/")
def home(request: Request):
    return _redirect("/dashboard" if request.session.get("user_id") else "/login")


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None, "registration_enabled": settings.registration_open(_now())})


@router.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            return templates.TemplateResponse(request, "login.html", {"error": "Ongeldig e-mailadres of wachtwoord.", "registration_enabled": settings.registration_open(_now())}, status_code=401)
        request.session["user_id"] = user.id
        return _redirect("/change-password" if user.must_reset_password else "/dashboard")


def _register_page(request: Request, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(request, "register.html", {"error": error}, status_code=status_code)


@router.get("/register")
def register_page(request: Request):
    if not settings.registration_open(_now()):
        raise HTTPException(status_code=404)
    return _register_page(request)


@router.get("/register/qr.png")
def registration_qr() -> Response:
    image = qrcode.make("https://ctf.exn.be/register")
    output = BytesIO()
    image.save(output, format="PNG")
    return Response(output.getvalue(), media_type="image/png")


@router.post("/register")
def register(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    password: str = Form(),
    confirm_password: str = Form(),
):
    if not settings.registration_open(_now()):
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
def start_challenge_page(request: Request, background_tasks: BackgroundTasks, challenged_id: int = Form()):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            _ensure_competition_running()
            challenge = create_challenge(db, challenger_id=user.id, challenged_id=challenged_id, now=_now())
            notification = {
                "challenge_id": challenge.id,
                "challenger_name": user.name,
                "challenger_email": user.email,
                "challenger_rank": challenge.challenger_rank_at_creation,
                "challenged_name": challenge.challenged.name,
                "challenged_email": challenge.challenged.email,
                "challenged_rank": challenge.challenged_rank_at_creation,
                "deadline_at": challenge.deadline_at,
            }
            db.commit()
            if settings.teams_webhook_url:
                background_tasks.add_task(
                    send_challenge_notification,
                    webhook_url=settings.teams_webhook_url,
                    **notification,
                )
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


@router.post("/dashboard/challenges/{challenge_id}/forfeit")
def forfeit_challenge_page(request: Request, challenge_id: int):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        try:
            forfeit_challenge(db, challenge_id=challenge_id, user_id=user.id, now=_now())
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return templates.TemplateResponse(request, "dashboard.html", _dashboard_data(db, user, exception.detail), status_code=exception.status_code)
    return _redirect("/dashboard?success=Je+hebt+opgegeven")


@router.get("/regels")
def rules_page(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        games = list(db.scalars(select(Game).where(Game.is_active).order_by(Game.name)))
        return templates.TemplateResponse(request, "rules.html", {"user": user, "games": games, "deadline": settings.qualification_deadline, "end_label": _date_label(settings.qualification_deadline)})


@router.get("/scoreboard")
def scoreboard_page(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        return templates.TemplateResponse(request, "scoreboard.html", {"user": user, "board": build_scoreboard(db)})


@router.get("/bijdrage")
def cheater_page(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        record = db.get(CheaterClick, user.id)
        if record is None:
            db.add(CheaterClick(user_id=user.id, clicks=1))
        else:
            record.clicks += 1
        db.commit()
        return templates.TemplateResponse(request, "cheater.html", {"user": user})


@router.get("/uitleg")
def guide_page(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        return templates.TemplateResponse(request, "guide.html", {"user": user, "start_label": _date_label(settings.competition_start), "end_label": _date_label(settings.qualification_deadline)})


@router.get("/admin")
def admin_console(request: Request):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        return templates.TemplateResponse(request, "admin.html", _admin_data(db, user, request))


def _admin_data(db, user: User, request: Request, **extra) -> dict:
    return {"user": user, "users": list(db.scalars(select(User).order_by(User.is_active.desc(), User.rank))), "games": list(db.scalars(select(Game).order_by(Game.name))), "challenges": list(db.scalars(select(Challenge).order_by(Challenge.created_at.desc(), Challenge.id.desc()))), "winners": {u.id: u.name for u in db.scalars(select(User))}, "message": request.query_params.get("success"), "error": request.query_params.get("error"), "temp_password": None, **extra}


@router.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(request: Request, user_id: int):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        target = db.get(User, user_id)
        if target is None:
            return _redirect("/admin?error=Gebruiker+niet+gevonden")
        temp_password = secrets.token_urlsafe(9)
        target.password_hash, target.must_reset_password = hash_password(temp_password), True
        db.commit()
        response = templates.TemplateResponse(request, "admin.html", _admin_data(db, user, request, temp_password=temp_password, temp_name=target.name))
        response.headers["Cache-Control"] = "no-store"
        return response


@router.post("/admin/challenges/{challenge_id}")
def admin_challenge_action(request: Request, challenge_id: int, action: str = Form(), winner_id: int | None = Form(None)):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        try:
            admin_resolve_challenge(db, challenge_id=challenge_id, action=action, winner_id=winner_id, now=_now())
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return _redirect(f"/admin?error={quote(str(exception.detail))}")
    return _redirect("/admin?success=Uitdaging+aangepast")


@router.post("/admin/users/{user_id}/remove")
def admin_remove_user(request: Request, user_id: int):
    with SessionLocal() as db:
        user = _signed_in(request, db)
        if isinstance(user, RedirectResponse):
            return user
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator permission required.")
        if user.id == user_id:
            return _redirect("/admin?error=Je+kunt+jezelf+niet+verwijderen")
        try:
            removed = remove_participant(db, user_id=user_id, now=_now())
            db.commit()
        except HTTPException as exception:
            db.rollback()
            return _redirect(f"/admin?error={quote(str(exception.detail))}")
    return _redirect("/admin?success=" + quote(f"{removed.name} is verwijderd uit de competitie"))


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

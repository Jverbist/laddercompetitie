"""Create the standard games and initial administrator accounts."""

import argparse

from sqlalchemy import func, select

from app.core.config import settings
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.models import Game, User, UserRole

STANDARD_GAMES = ("Pool", "1 leg darts", "Bowling", "Mikado", "4 op een rij", "Wie is het")


def main(*, reset_admin_passwords: bool = False) -> None:
    if not settings.admin_bootstrap_password or settings.admin_bootstrap_password.startswith("replace-"):
        raise ValueError("Set ADMIN_BOOTSTRAP_PASSWORD in .env before creating administrator accounts.")
    Base.metadata.create_all(engine)
    with SessionLocal.begin() as db:
        for name in STANDARD_GAMES:
            if db.scalar(select(Game).where(Game.name == name)) is None:
                db.add(Game(name=name))
        for email in sorted(settings.admin_email_set):
            admin = db.scalar(select(User).where(User.email == email))
            if admin is None:
                next_rank = (db.scalar(select(func.max(User.rank))) or 0) + 1
                db.add(
                    User(
                        name=email.split("@", maxsplit=1)[0].title(),
                        email=email,
                        role=UserRole.ADMIN,
                        rank=next_rank,
                        password_hash=hash_password(settings.admin_bootstrap_password),
                        must_reset_password=True,
                    )
                )
                db.flush()
            elif reset_admin_passwords or not admin.password_hash:
                admin.password_hash = hash_password(settings.admin_bootstrap_password)
                admin.must_reset_password = True
    print("Seed data created." if not reset_admin_passwords else "Seed data created and administrator passwords reset.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset-admin-passwords",
        action="store_true",
        help="Replace every configured administrator password with ADMIN_BOOTSTRAP_PASSWORD.",
    )
    arguments = parser.parse_args()
    main(reset_admin_passwords=arguments.reset_admin_passwords)

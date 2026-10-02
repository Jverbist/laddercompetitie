"""Apply the small schema upgrade needed by the local development database."""

from sqlalchemy import inspect, text

from app.db import engine


def main() -> None:
    if not engine.url.drivername.startswith("sqlite"):
        raise RuntimeError("Use Alembic migrations for non-SQLite databases.")

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        if "password_hash" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "must_reset_password" not in columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN must_reset_password BOOLEAN NOT NULL DEFAULT 1")
            )
    print("Local database migration completed.")


if __name__ == "__main__":
    main()

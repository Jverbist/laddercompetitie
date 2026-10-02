"""Create the initial ladder competition schema."""

from alembic import op

from app.db import Base
import app.models  # noqa: F401

revision = "20261002_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

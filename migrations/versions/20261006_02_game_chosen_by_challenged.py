"""Let the challenged participant choose the game after the challenge is created."""

from alembic import op

revision = "20261006_02"
down_revision = "20261002_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("challenges") as batch:
        batch.alter_column("game_id", nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("challenges") as batch:
        batch.alter_column("game_id", nullable=False)

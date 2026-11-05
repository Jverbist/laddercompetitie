"""Add finale tournament tables."""

import sqlalchemy as sa
from alembic import op

revision = "20261105_04"
down_revision = "20261029_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = sa.inspect(op.get_bind()).get_table_names()
    if "tournaments" not in existing:
        op.create_table(
            "tournaments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("champion_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "tournament_matches" not in existing:
        op.create_table(
            "tournament_matches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False, index=True),
            sa.Column("round", sa.Integer(), nullable=False),
            sa.Column("slot", sa.Integer(), nullable=False),
            sa.Column("player_a_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("player_b_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("seed_a", sa.Integer(), nullable=True),
            sa.Column("seed_b", sa.Integer(), nullable=True),
            sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("proposed_winner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("winner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.UniqueConstraint("tournament_id", "round", "slot"),
            sa.UniqueConstraint("tournament_id", "round", "game_id"),
        )


def downgrade() -> None:
    op.drop_table("tournament_matches")
    op.drop_table("tournaments")

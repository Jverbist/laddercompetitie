"""Record who clicked the donation link."""

import sqlalchemy as sa
from alembic import op

revision = "20261029_03"
down_revision = "20261006_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "cheater_clicks" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "cheater_clicks",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_clicked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cheater_clicks")

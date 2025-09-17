"""add_availability_status_to_users

Revision ID: 8b9d5d3a4af1
Revises: fdeec55cbdb7
Create Date: 2025-09-17 18:54:07.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8b9d5d3a4af1"
down_revision = "fdeec55cbdb7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "availability_status",
            sa.String(),
            nullable=False,
            server_default="not_available",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "availability_mode",
            sa.String(),
            nullable=False,
            server_default="auto",
        ),
    )

    # Reset existing rows to offline/auto mode by default
    op.execute("UPDATE users SET availability_status = 'not_available' WHERE availability_status IS NULL")
    op.execute("UPDATE users SET availability_mode = 'auto' WHERE availability_mode IS NULL")


def downgrade() -> None:
    op.drop_column("users", "availability_mode")
    op.drop_column("users", "availability_status")

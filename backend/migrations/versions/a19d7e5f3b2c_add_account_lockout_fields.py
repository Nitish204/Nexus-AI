"""add account lockout fields to user

Revision ID: a19d7e5f3b2c
Revises: c028bc0e10c7
Create Date: 2026-09-22 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 — see 3f086b6e3c11 for why this import is required


# revision identifiers, used by Alembic.
revision: str = 'a19d7e5f3b2c'
down_revision: Union[str, None] = 'c028bc0e10c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Real production bug this migration fixes: app/api/auth.py's
    # /login handler has unconditionally read/written
    # user.failed_login_count and user.locked_until since account
    # lockout was written, but the User table never actually had these
    # columns — every login attempt raised AttributeError. server_default
    # values (not just Python-level Field defaults) are required here
    # for the same reason as totp_enabled in 3f086b6e3c11: Postgres
    # rejects a NOT NULL column with no default against a table that
    # already has rows, which `user` does.
    op.add_column('user', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('user', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'locked_until')
    op.drop_column('user', 'failed_login_count')

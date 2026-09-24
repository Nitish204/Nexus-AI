"""add token_usage table for LLM cost tracking

Revision ID: c028bc0e10c7
Revises: 3f086b6e3c11
Create Date: 2026-09-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel  # noqa: F401 — see 3f086b6e3c11 for why this import is required


# revision identifiers, used by Alembic.
revision: str = 'c028bc0e10c7'
down_revision: Union[str, None] = '3f086b6e3c11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tokenusage',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('project_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('task_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # create_type=False: the Postgres ENUM type "agentrole" already
        # exists (created by eb174659ba7f for task.assigned_role) — letting
        # it auto-create again fails with "type agentrole already exists".
        #
        # IMPORTANT: create_type is a postgresql-dialect-specific kwarg.
        # It only has any effect on sqlalchemy.dialects.postgresql.ENUM.
        # Passing it to the generic sa.Enum(...) (as an earlier version of
        # this migration did) is silently accepted and silently ignored —
        # sa.Enum has no create_type attribute at all, so Alembic still
        # emitted CREATE TYPE and broke every deploy with
        # "DuplicateObjectError: type agentrole already exists". This is
        # the actual fix, not a cosmetic one.
        sa.Column('role', postgresql.ENUM('PRODUCT_MANAGER', 'BACKEND_ENGINEER', 'FRONTEND_ENGINEER', 'QA_ENGINEER', 'DEVOPS_ENGINEER', name='agentrole', create_type=False), nullable=False),
        sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default=sa.text('0')),
        sa.Column('is_estimated', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['project.id']),
        sa.ForeignKeyConstraint(['task_id'], ['task.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tokenusage_project_id'), 'tokenusage', ['project_id'], unique=False)
    op.create_index(op.f('ix_tokenusage_task_id'), 'tokenusage', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tokenusage_task_id'), table_name='tokenusage')
    op.drop_index(op.f('ix_tokenusage_project_id'), table_name='tokenusage')
    op.drop_table('tokenusage')

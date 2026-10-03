"""Remember the last accepted TOTP step, so a code is never accepted twice.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_last_step', sa.Integer(),
                                      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('totp_last_step')

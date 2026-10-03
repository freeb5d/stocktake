"""An API key belongs to a person and reaches any of their portfolios.

Until now a key belonged to exactly one portfolio, in `api_key.portfolio_id`.
It moves to a link table, and every existing key keeps reaching the one
portfolio it reached before. decisions.md #128.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('api_key_portfolio',
    sa.Column('api_key_id', sa.Integer(), nullable=False),
    sa.Column('portfolio_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['api_key_id'], ['api_key.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['portfolio_id'], ['portfolio.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('api_key_id', 'portfolio_id')
    )
    with op.batch_alter_table('api_key_portfolio', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_key_portfolio_portfolio_id'),
                              ['portfolio_id'], unique=False)

    op.execute("INSERT INTO api_key_portfolio (api_key_id, portfolio_id) "
               "SELECT id, portfolio_id FROM api_key")

    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_key_portfolio_id'))
        batch_op.drop_column('portfolio_id')


def downgrade() -> None:
    # A key that reaches several portfolios keeps the first of them; one that
    # reaches none cannot be expressed in the old shape and is deleted.
    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.add_column(sa.Column('portfolio_id', sa.Integer(), nullable=True))
    op.execute("UPDATE api_key SET portfolio_id = (SELECT MIN(portfolio_id) "
               "FROM api_key_portfolio WHERE api_key_id = api_key.id)")
    op.execute("DELETE FROM api_key WHERE portfolio_id IS NULL")
    with op.batch_alter_table('api_key', schema=None) as batch_op:
        batch_op.alter_column('portfolio_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_api_key_portfolio_id', 'portfolio',
                                    ['portfolio_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(batch_op.f('ix_api_key_portfolio_id'),
                              ['portfolio_id'], unique=False)

    with op.batch_alter_table('api_key_portfolio', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_key_portfolio_portfolio_id'))
    op.drop_table('api_key_portfolio')

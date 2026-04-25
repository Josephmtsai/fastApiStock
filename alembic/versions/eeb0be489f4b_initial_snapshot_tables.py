"""initial snapshot tables

Revision ID: eeb0be489f4b
Revises:
Create Date: 2026-04-25 18:14:09.349349

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'eeb0be489f4b'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'portfolio_report_summary',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('report_type', sa.String(length=10), nullable=False),
        sa.Column('report_period', sa.String(length=10), nullable=False),
        sa.Column('pnl_tw_total', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('pnl_us_total', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('pnl_tw_delta', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('pnl_us_delta', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('buy_amount_twd', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('signals_count', sa.Integer(), nullable=False),
        sa.Column('symbols_count', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'report_type', 'report_period', name='uq_report_summary_period'
        ),
    )
    op.create_table(
        'portfolio_symbol_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('report_type', sa.String(length=10), nullable=False),
        sa.Column('report_period', sa.String(length=10), nullable=False),
        sa.Column('market', sa.String(length=4), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('shares', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('avg_cost', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('current_price', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('market_value', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('unrealized_pnl', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('pnl_pct', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('pnl_delta', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'report_type',
            'report_period',
            'market',
            'symbol',
            name='uq_symbol_snapshot_period',
        ),
    )
    op.create_index(
        'idx_period_report',
        'portfolio_symbol_snapshots',
        ['report_type', 'report_period'],
        unique=False,
    )
    op.create_index(
        'idx_symbol_time',
        'portfolio_symbol_snapshots',
        ['market', 'symbol', 'report_period'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_symbol_time', table_name='portfolio_symbol_snapshots')
    op.drop_index('idx_period_report', table_name='portfolio_symbol_snapshots')
    op.drop_table('portfolio_symbol_snapshots')
    op.drop_table('portfolio_report_summary')

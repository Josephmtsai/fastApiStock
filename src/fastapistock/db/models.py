"""SQLAlchemy 2.0 ORM models for spec-006 report history tables.

Tables:
    * ``portfolio_symbol_snapshots``: per-symbol per-period snapshot rows.
    * ``portfolio_report_summary``: one aggregated row per (report_type, period).

Both tables use ``UPSERT`` semantics (see repositories in Phase 2); the
UNIQUE constraints below back that behaviour.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class PortfolioSymbolSnapshot(Base):
    """Per-symbol snapshot of a portfolio position at a specific report period."""

    __tablename__ = 'portfolio_symbol_snapshots'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(10), nullable=False)
    report_period: Mapped[str] = mapped_column(String(10), nullable=False)
    market: Mapped[str] = mapped_column(String(4), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pnl_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            'report_type',
            'report_period',
            'market',
            'symbol',
            name='uq_symbol_snapshot_period',
        ),
        Index(
            'idx_symbol_time',
            'market',
            'symbol',
            'report_period',
        ),
        Index(
            'idx_period_report',
            'report_type',
            'report_period',
        ),
    )


class PortfolioReportSummary(Base):
    """Aggregated per-period summary across both TW and US portfolios."""

    __tablename__ = 'portfolio_report_summary'

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(String(10), nullable=False)
    report_period: Mapped[str] = mapped_column(String(10), nullable=False)
    pnl_tw_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pnl_us_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pnl_tw_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    pnl_us_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    buy_amount_twd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    signals_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            'report_type',
            'report_period',
            name='uq_report_summary_period',
        ),
    )

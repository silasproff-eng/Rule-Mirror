from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def uuid_value() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    public_handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    public_profile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    file_hash: Mapped[str] = mapped_column(String(64))
    mapping: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30))
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    trade_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (UniqueConstraint("user_id", "source", "account_reference", "symbol"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(80))
    account_reference: Mapped[str] = mapped_column(String(128), default="default")
    symbol: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(String(240))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    asset_type: Mapped[str] = mapped_column(String(40), default="stock")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    asset_type: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    commission: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    account_reference: Mapped[str] = mapped_column(String(128), default="default")
    external_execution_id: Mapped[str | None] = mapped_column(String(160))
    row_number: Mapped[int] = mapped_column(Integer)
    row_hash: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))


class ImportBatchExecution(Base):
    __tablename__ = "import_batch_executions"
    __table_args__ = (UniqueConstraint("import_batch_id", "row_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="RESTRICT"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    row_hash: Mapped[str] = mapped_column(String(64))
    was_inserted: Mapped[bool] = mapped_column(Boolean)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (UniqueConstraint("user_id", "identity_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    asset_type: Mapped[str] = mapped_column(String(20))
    account_reference: Mapped[str] = mapped_column(String(128), default="default")
    identity_key: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(8))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    current_revision_id: Mapped[str | None] = mapped_column(ForeignKey("trade_revisions.id", use_alter=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TradeRevision(Base):
    __tablename__ = "trade_revisions"
    __table_args__ = (UniqueConstraint("trade_id", "revision_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"))
    revision_hash: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(8))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TradeRevisionAllocation(Base):
    __tablename__ = "trade_revision_allocations"
    __table_args__ = (UniqueConstraint("trade_revision_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    trade_revision_id: Mapped[str] = mapped_column(ForeignKey("trade_revisions.id", ondelete="CASCADE"))
    execution_id: Mapped[str] = mapped_column(ForeignKey("executions.id", ondelete="CASCADE"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    role: Mapped[str] = mapped_column(String(12))
    sequence: Mapped[int] = mapped_column(Integer)


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"))
    trade_revision_id: Mapped[str] = mapped_column(ForeignKey("trade_revisions.id", ondelete="RESTRICT"))
    strategy_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_versions.id"))
    retry_of_run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(40))
    engine_version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TradeAnalysis(Base):
    __tablename__ = "trade_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), unique=True)
    trade_id: Mapped[str] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"))
    score: Mapped[int | None] = mapped_column(Integer)
    data_sufficiency: Mapped[str] = mapped_column(String(30))
    feedback: Mapped[list] = mapped_column(JSON)
    derived_context: Mapped[dict] = mapped_column(JSON)


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"
    __table_args__ = (UniqueConstraint("trade_analysis_id", "rule_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    trade_analysis_id: Mapped[str] = mapped_column(ForeignKey("trade_analyses.id", ondelete="CASCADE"))
    rule_key: Mapped[str] = mapped_column(String(80))
    result: Mapped[str] = mapped_column(String(24))
    measurement: Mapped[str | None] = mapped_column(String(100))
    threshold: Mapped[str | None] = mapped_column(String(100))
    weight: Mapped[int] = mapped_column(Integer)


class MarketCacheEntry(Base):
    __tablename__ = "market_cache_entries"
    __table_args__ = (UniqueConstraint("provider", "instrument", "asset_type", "session_date", "timeframe", "schema_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_value)
    provider: Mapped[str] = mapped_column(String(40))
    instrument: Mapped[str] = mapped_column(String(32))
    asset_type: Mapped[str] = mapped_column(String(20))
    session_date: Mapped[str] = mapped_column(String(10))
    timeframe: Mapped[str] = mapped_column(String(10))
    schema_version: Mapped[int] = mapped_column(Integer)
    normalized_payload: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    storage_policy: Mapped[str] = mapped_column(String(80))

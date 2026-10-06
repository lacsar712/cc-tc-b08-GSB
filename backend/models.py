import os
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
# 本地用 SQLite 冒烟时允许跨线程连接；PostgreSQL 不需要这些参数。
_CONNECT_ARGS = {"check_same_thread": False, "timeout": 15} if DSN.startswith("sqlite") else {}
engine = create_engine(DSN, pool_pre_ping=True, connect_args=_CONNECT_ARGS)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=False, default="掌子面")
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThinningState(Base):
    """抽稀台单例配置，id 固定为 1。开关与取样窗参数都落库，重启不丢。"""

    __tablename__ = "thinning_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    jump_threshold_mm: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThinningRejection(Base):
    """被抽稀台拦住的交单履历：整份退回的每一笔都留痕，关闸后仍可翻。"""

    __tablename__ = "thinning_rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String, nullable=False)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    rule: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    window_median: Mapped[float | None] = mapped_column(Float, nullable=True)
    jump_threshold_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def ensure_schema():
    """建表并对老库补齐后加的列（幂等）。"""
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("convergence_logs")}
    if "section" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE convergence_logs ADD COLUMN section VARCHAR NOT NULL DEFAULT '掌子面'")
            )


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "section": row.section,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def state_dict(state: ThinningState, window_median=None, window_samples=0) -> dict:
    return {
        "enabled": state.enabled,
        "window_seconds": state.window_seconds,
        "jump_threshold_mm": state.jump_threshold_mm,
        "updated_by": state.updated_by,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        "window_median": window_median,
        "window_samples": window_samples,
    }


def rejection_dict(row: ThinningRejection) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "chainage": row.chainage,
        "section": row.section,
        "delta_mm": row.delta_mm,
        "rule": row.rule,
        "detail": row.detail,
        "window_median": row.window_median,
        "jump_threshold_mm": row.jump_threshold_mm,
        "window_seconds": row.window_seconds,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

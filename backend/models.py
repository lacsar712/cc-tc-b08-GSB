import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
if DSN.startswith("sqlite"):
    engine = create_engine(
        DSN,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
else:
    engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# 测读部位：拱顶读数 / 边墙锤击读数，同一抽稀台都要拦
PART_CROWN = "拱顶"
PART_SIDE = "边墙"
PARTS = (PART_CROWN, PART_SIDE)


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    part: Mapped[str] = mapped_column(String, nullable=False, default=PART_CROWN, server_default=PART_CROWN)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThinConfig(Base):
    """抽稀台开关与取样窗，单行单例（id 恒为 1）。"""

    __tablename__ = "thin_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    threshold_mm: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ThinReject(Base):
    """被抽稀台整份退回的飞点履历；停用开关不影响旧履历留存与翻阅。"""

    __tablename__ = "thin_rejects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    part: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    median_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_mm: Mapped[float] = mapped_column(Float, nullable=False)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "part": row.part,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def config_dict(row: ThinConfig) -> dict:
    return {
        "enabled": row.enabled,
        "window_size": row.window_size,
        "threshold_mm": row.threshold_mm,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def reject_dict(row: ThinReject) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "part": row.part,
        "delta_mm": row.delta_mm,
        "median_mm": row.median_mm,
        "deviation_mm": row.deviation_mm,
        "threshold_mm": row.threshold_mm,
        "window_size": row.window_size,
        "sample_count": row.sample_count,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def ensure_schema():
    Base.metadata.create_all(engine)
    # 老库补列（create_all 不会给既有表加列）
    cols = {c["name"] for c in inspect(engine).get_columns("convergence_logs")}
    if "part" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE convergence_logs ADD COLUMN part VARCHAR NOT NULL DEFAULT :p"),
                {"p": PART_CROWN},
            )

from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class ProductModelOrm(Base):
    __tablename__ = "product_models"

    model: Mapped[str] = mapped_column(String(64), primary_key=True)
    resistance_mean: Mapped[float] = mapped_column(Float, default=0)
    resistance_sd: Mapped[float] = mapped_column(Float, default=0)
    power_w: Mapped[float] = mapped_column(Float, default=0)


class BatchRecordOrm(Base):
    __tablename__ = "batch_records"

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    count: Mapped[int] = mapped_column(Integer, default=0)
    defect_ratio: Mapped[float] = mapped_column(Float, default=0)
    batch_factor: Mapped[float] = mapped_column(Float, default=1)
    remaining: Mapped[int] = mapped_column(Integer, default=0)
    tested: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    aborted: Mapped[int] = mapped_column(Integer, default=0)
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    machine_ids: Mapped[list] = mapped_column(JSONB, default=list)
    started_at: Mapped[int] = mapped_column(BigInteger, default=0)
    ended_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="done")
    rc_mean: Mapped[float] = mapped_column(Float, default=0)
    rc_sd: Mapped[float] = mapped_column(Float, default=0)
    top_fail: Mapped[str] = mapped_column(String(64), default="")
    eta_s: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProductionOrm(Base):
    __tablename__ = "production_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[str] = mapped_column(String(128), default="")
    queue_remaining: Mapped[int] = mapped_column(Integer, default=0)
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)


class PlanDispatchOrm(Base):
    __tablename__ = "plan_dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(16), index=True)
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    batch_id: Mapped[str] = mapped_column(String(128), default="")
    actor: Mapped[str] = mapped_column(String(64), default="")
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[int] = mapped_column(BigInteger, index=True)


class RunDetailOrm(Base):
    __tablename__ = "run_details"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)

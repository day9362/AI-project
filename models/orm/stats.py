from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class RunOrm(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(16), index=True)
    slot_index: Mapped[int] = mapped_column(Integer)
    serial_number: Mapped[str] = mapped_column(String(128), default="")
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fail_items: Mapped[list] = mapped_column(JSONB, default=list)
    keep_result: Mapped[bool] = mapped_column(Boolean, default=True)
    rc: Mapped[float | None] = mapped_column(Float, nullable=True)
    dt01: Mapped[float | None] = mapped_column(Float, nullable=True)
    batch_id: Mapped[str] = mapped_column(String(128), default="")
    ended_at: Mapped[int] = mapped_column(BigInteger, index=True)


class PlanOrm(Base):
    __tablename__ = "plans"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    duration_s: Mapped[int] = mapped_column(Integer, default=180)
    power_w: Mapped[float] = mapped_column(Float, default=0)
    start_temp_c: Mapped[float] = mapped_column(Float, default=45)
    ambient_low_c: Mapped[float] = mapped_column(Float, default=23)
    ambient_high_c: Mapped[float] = mapped_column(Float, default=27)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)


class BatchStatOrm(Base):
    __tablename__ = "batch_stats"

    batch_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    count: Mapped[int] = mapped_column(Integer, default=0)
    tested: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(16), default="done")
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    plan_version: Mapped[int] = mapped_column(Integer, default=0)


class Agg5mOrm(Base):
    __tablename__ = "agg_5m"

    bucket: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    aborted: Mapped[int] = mapped_column(Integer, default=0)
    rc_mean: Mapped[float] = mapped_column(Float, default=0)
    dt01_mean: Mapped[float] = mapped_column(Float, default=0)

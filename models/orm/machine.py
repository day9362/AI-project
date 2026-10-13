from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class MachineOrm(Base):
    __tablename__ = "machines"

    machine_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    serial: Mapped[str] = mapped_column(String(64), default="")
    fixture: Mapped[str] = mapped_column(String(64), default="")
    holder: Mapped[str] = mapped_column(String(64), default="")
    thermal_boards: Mapped[str] = mapped_column(String(256), default="")
    plc: Mapped[str] = mapped_column(String(16), default="INOVANCE")
    firmware: Mapped[str] = mapped_column(String(64), default="")
    slot_count: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default="OFFLINE")
    comm_status: Mapped[str] = mapped_column(String(32), default="DISCONNECTED")
    comm_note: Mapped[str] = mapped_column(String(128), default="")
    speed: Mapped[float] = mapped_column(Float, default=1)
    room_temp_c: Mapped[float] = mapped_column(Float, default=25)
    alarm: Mapped[str] = mapped_column(String(256), default="")
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capability: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_sync_at: Mapped[int] = mapped_column(BigInteger, default=0)


class SlotOrm(Base):
    __tablename__ = "slots"

    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id", ondelete="CASCADE"), primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase: Mapped[str] = mapped_column(String(32), default="IDLE")
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tests_done: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(256), default="")
    power_w: Mapped[float] = mapped_column(Float, default=0)
    vacuum_kpa: Mapped[float] = mapped_column(Float, default=0)
    t0: Mapped[float] = mapped_column(Float, default=0)
    t1: Mapped[float] = mapped_column(Float, default=0)
    ta: Mapped[float] = mapped_column(Float, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RunSampleOrm(Base):
    __tablename__ = "run_samples"
    __table_args__ = (UniqueConstraint("run_id", "t_s", name="uq_run_sample"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    t_s: Mapped[float] = mapped_column(Float)
    t0: Mapped[float] = mapped_column(Float)
    t1: Mapped[float] = mapped_column(Float)
    ta: Mapped[float] = mapped_column(Float)
    power_w: Mapped[float] = mapped_column(Float)


class CompensationWriteOrm(Base):
    """补偿写入记录。只记本平台发出的修改。"""

    __tablename__ = "compensation_writes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(16), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="")
    mode: Mapped[str] = mapped_column(String(8), default="set")
    before: Mapped[list] = mapped_column(JSONB, default=list)
    after: Mapped[list] = mapped_column(JSONB, default=list)
    audit_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[int] = mapped_column(BigInteger, index=True)


class ChannelBiasOrm(Base):
    __tablename__ = "channel_biases"
    __table_args__ = (UniqueConstraint("machine_id", "channel", name="uq_channel_bias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machines.machine_id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    measured_at: Mapped[int] = mapped_column(BigInteger, default=0)

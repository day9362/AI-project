from sqlalchemy import BigInteger, Boolean, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class AlarmOrm(Base):
    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    time: Mapped[int] = mapped_column(BigInteger, index=True)
    level: Mapped[str] = mapped_column(String(16))
    machine_id: Mapped[str] = mapped_column(String(16), index=True)
    slot_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(512))
    acked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    acked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class AlarmAttributionOrm(Base):
    __tablename__ = "alarm_attributions"

    alarm_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    category: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    summary: Mapped[str] = mapped_column(String(1024), default="")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    suggestion: Mapped[str] = mapped_column(String(512), default="")
    model: Mapped[str] = mapped_column(String(64), default="rule")
    created_at: Mapped[int] = mapped_column(BigInteger, default=0)

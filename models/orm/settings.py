from sqlalchemy import BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class PlatformSettingsOrm(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=0)

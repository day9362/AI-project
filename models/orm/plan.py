from sqlalchemy import BigInteger, Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.orm.base import Base


class PlanRevisionOrm(Base):
    """完整方案。version = 0 是只存在本地的草稿。"""

    __tablename__ = "plan_revisions"

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    body: Mapped[dict] = mapped_column(JSONB)
    author: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    updated_at: Mapped[int] = mapped_column(BigInteger, default=0)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)

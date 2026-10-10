import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms
from models.orm.audit import AuditLogOrm, IdempotencyOrm

IDEMPOTENCY_MS = 10 * 60 * 1000


class AuditRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def write(self, actor: str, action: str, request: dict | None = None) -> str:
        audit_id = "aud_" + uuid.uuid4().hex[:12]
        self.session.add(AuditLogOrm(
            id=audit_id,
            actor=actor,
            action=action,
            created_at=now_ms(),
            request=request or {},
        ))
        return audit_id

    async def get_idempotent(self, user_id: str, key: str) -> dict | None:
        row = await self.session.scalar(
            select(IdempotencyOrm).where(
                IdempotencyOrm.user_id == user_id,
                IdempotencyOrm.key == key,
                IdempotencyOrm.created_at >= now_ms() - IDEMPOTENCY_MS,
            )
        )
        return dict(row.body) if row else None

    async def save_idempotent(self, user_id: str, key: str, body: dict) -> None:
        self.session.add(IdempotencyOrm(user_id=user_id, key=key, body=body, created_at=now_ms()))

    async def purge_idempotent(self) -> int:
        result = await self.session.execute(
            delete(IdempotencyOrm).where(IdempotencyOrm.created_at < now_ms() - IDEMPOTENCY_MS)
        )
        return int(result.rowcount or 0)

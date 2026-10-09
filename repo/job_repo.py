from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.orm.audit import IdempotencyOrm, JobRunOrm


class JobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def start(self, name: str, kind: str, started_at: int) -> int:
        row = JobRunOrm(name=name, kind=kind, status="running", started_at=started_at, detail="")
        self.session.add(row)
        await self.session.flush()
        return row.id

    async def finish(self, job_id: int, status: str, finished_at: int, detail: str) -> None:
        row = await self.session.get(JobRunOrm, job_id)
        if row is None:
            return
        row.status = status
        row.finished_at = finished_at
        row.detail = detail[:1024]

    async def get_idempotent(self, user_id: str, key: str, not_before: int) -> dict | None:
        row = await self.session.scalar(
            select(IdempotencyOrm).where(
                IdempotencyOrm.user_id == user_id,
                IdempotencyOrm.key == key,
                IdempotencyOrm.created_at >= not_before,
            )
        )
        return dict(row.body) if row else None

    async def save_idempotent(self, user_id: str, key: str, body: dict, created_at: int) -> None:
        self.session.add(IdempotencyOrm(user_id=user_id, key=key, body=body, created_at=created_at))

    async def purge_idempotent(self, older_than: int) -> int:
        result = await self.session.execute(delete(IdempotencyOrm).where(IdempotencyOrm.created_at < older_than))
        return int(result.rowcount or 0)

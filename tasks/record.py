import logging

from core.clock import now_ms
from core.db import SessionLocal
from models.orm.audit import JobRunOrm

log = logging.getLogger(__name__)


async def record_job(name: str, kind: str, status: str, started_at: int, detail: str) -> None:
    try:
        async with SessionLocal() as session:
            session.add(JobRunOrm(
                name=name,
                kind=kind,
                status=status,
                started_at=started_at,
                finished_at=now_ms(),
                detail=detail[:1024],
            ))
            await session.commit()
    except Exception:
        log.exception("记录任务失败 %s", name)

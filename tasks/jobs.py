import logging

from core.clock import now_ms
from core.db import SessionLocal
from repo.audit_repo import AuditRepo
from tasks.record import record_job

log = logging.getLogger(__name__)


async def cleanup_idempotency(kind: str = "scheduled") -> None:
    """清理超过 10 分钟的幂等键。定时任务和触发任务都走这里。"""
    started = now_ms()
    try:
        async with SessionLocal() as session:
            removed = await AuditRepo(session).purge_idempotent()
            await session.commit()
        await record_job("cleanup.idempotency", kind, "ok", started, f"removed={removed}")
    except Exception as exc:
        log.exception("cleanup.idempotency failed")
        await record_job("cleanup.idempotency", kind, "failed", started, str(exc))
        raise

import asyncio
import logging

from core.clock import now_ms
from core.db import SessionLocal
from repo.alarm_repo import AlarmRepo
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.overview.alarm_service import AlarmService
from tasks.jobs import cleanup_idempotency
from tasks.record import record_job

log = logging.getLogger(__name__)


class TriggerBus:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    def emit(self, name: str, payload: dict | None = None) -> None:
        self.queue.put_nowait((name, payload or {}))

    async def _loop(self) -> None:
        while True:
            name, payload = await self.queue.get()
            started = now_ms()
            try:
                await self._dispatch(name, payload)
                if name != "cleanup.idempotency":
                    await record_job(name, "triggered", "ok", started, str(payload.get("alarm_id", "")))
            except Exception as exc:
                log.exception("触发任务失败 %s", name)
                if name != "cleanup.idempotency":
                    await record_job(name, "triggered", "failed", started, str(exc))

    async def _dispatch(self, name: str, payload: dict) -> None:
        if name == "cleanup.idempotency":
            await cleanup_idempotency(kind="triggered")
            return
        if name == "alarm.attribution":
            async with SessionLocal() as session:
                service = AlarmService(
                    AlarmRepo(session), MachineRepo(session), StatsRepo(session), AuditRepo(session),
                )
                await service.run_attribution(payload["alarm_id"])
                await session.commit()
            return
        raise RuntimeError(f"未知触发任务 {name}")


trigger_bus = TriggerBus()

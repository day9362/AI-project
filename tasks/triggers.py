import asyncio
import logging

from core.clock import now_ms
from core.db import SessionLocal
from repo.alarm_repo import AlarmRepo
from repo.job_repo import JobRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.overview.alarm_service import AlarmService
from tasks.record import record_job

log = logging.getLogger(__name__)


class TriggerBus:
    """进程内触发任务。新告警和手动重新归因都从这里执行。"""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def emit(self, name: str, payload: dict) -> None:
        self.queue.put_nowait((name, payload, None))

    async def emit_wait(self, name: str, payload: dict):
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self.queue.put((name, payload, future))
        return await future

    async def _loop(self) -> None:
        while True:
            name, payload, future = await self.queue.get()
            started = now_ms()
            try:
                result = await self._dispatch(name, payload)
                await record_job(name, "triggered", "ok", started, str(payload.get("alarm_id", "")))
                if future and not future.done():
                    future.set_result(result)
            except Exception as exc:
                log.exception("triggered task %s failed", name)
                await record_job(name, "triggered", "failed", started, str(exc))
                if future and not future.done():
                    future.set_exception(exc)

    async def _dispatch(self, name: str, payload: dict):
        if name != "alarm.attribution":
            raise RuntimeError(f"未知触发任务 {name}")
        async with SessionLocal() as session:
            service = AlarmService(AlarmRepo(session), MachineRepo(session), StatsRepo(session), JobRepo(session))
            result = await service.run_attribution(payload["alarm_id"])
            await session.commit()
            return result


trigger_bus = TriggerBus()

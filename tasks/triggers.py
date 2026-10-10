import asyncio
import logging

from tasks.jobs import cleanup_idempotency

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

    def emit(self, name: str) -> None:
        self.queue.put_nowait(name)

    async def _loop(self) -> None:
        while True:
            name = await self.queue.get()
            try:
                await self._dispatch(name)
            except Exception:
                log.exception("触发任务失败 %s", name)

    async def _dispatch(self, name: str) -> None:
        if name != "cleanup.idempotency":
            raise RuntimeError(f"未知触发任务 {name}")
        await cleanup_idempotency(kind="triggered")


trigger_bus = TriggerBus()

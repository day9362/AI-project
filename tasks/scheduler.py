from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tasks.jobs import cleanup_idempotency

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        cleanup_idempotency,
        "interval",
        minutes=10,
        id="cleanup.idempotency",
        next_run_time=datetime.now(),
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

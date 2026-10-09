from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from tasks.jobs import cleanup_idempotency, rollup_agg, scan_alarms, sync_fleet, sync_runs, sync_slots

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(sync_fleet, "interval", seconds=settings.fleet_interval_s, id="sync.fleet", max_instances=1, coalesce=True)
    scheduler.add_job(sync_slots, "interval", seconds=settings.slots_interval_s, id="sync.slots", max_instances=1, coalesce=True)
    scheduler.add_job(sync_runs, "interval", seconds=settings.runs_interval_s, id="sync.runs", max_instances=1, coalesce=True)
    scheduler.add_job(rollup_agg, "interval", seconds=settings.agg_interval_s, id="rollup.agg", max_instances=1, coalesce=True)
    scheduler.add_job(scan_alarms, "interval", seconds=settings.alarm_interval_s, id="scan.alarms", max_instances=1, coalesce=True)
    scheduler.add_job(cleanup_idempotency, "interval", minutes=10, id="cleanup.idempotency", max_instances=1, coalesce=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

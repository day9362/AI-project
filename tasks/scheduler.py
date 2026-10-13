from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from tasks.jobs import cleanup_idempotency, rollup_agg, scan_alarms, sync_catalog, sync_fleet, sync_runs, sync_slots

scheduler = AsyncIOScheduler()


def start_scheduler(jobs: list[dict] | None = None) -> None:
    if scheduler.running:
        return
    now = datetime.now()
    chosen = _seconds(jobs)
    scheduler.add_job(sync_fleet, "interval", seconds=chosen["fleet"], id="sync.fleet", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(sync_slots, "interval", seconds=chosen["slots"], id="sync.slots", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(sync_runs, "interval", seconds=chosen["runs"], id="sync.runs", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(sync_catalog, "interval", seconds=chosen["catalog"], id="sync.catalog", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(rollup_agg, "interval", seconds=chosen["agg"], id="rollup.agg", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(scan_alarms, "interval", seconds=settings.alarm_interval_s, id="scan.alarms", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.add_job(cleanup_idempotency, "interval", minutes=10, id="cleanup.idempotency", next_run_time=now, max_instances=1, coalesce=True)
    scheduler.start()
    if jobs:
        apply_job_intervals(jobs)


def apply_job_intervals(jobs: list[dict]) -> None:
    if not scheduler.running:
        return
    chosen = _seconds(jobs)
    by_key = {job["key"]: job for job in jobs}
    _retune("sync.fleet", by_key.get("fleet", {}).get("enabled", True), chosen["fleet"])
    _retune("sync.slots", by_key.get("slots", {}).get("enabled", True), chosen["slots"])
    _retune("sync.runs", by_key.get("runs", {}).get("enabled", True), chosen["runs"])
    _retune("rollup.agg", by_key.get("agg", {}).get("enabled", True), chosen["agg"])
    catalog_on = any(by_key.get(key, {}).get("enabled") for key in ("plans", "batches"))
    _retune("sync.catalog", catalog_on, chosen["catalog"])


def _seconds(jobs: list[dict] | None) -> dict[str, int]:
    found = {job["key"]: job for job in jobs or []}

    def pick(key: str, fallback: int) -> int:
        row = found.get(key)
        if row and row.get("enabled"):
            return int(row["interval_s"])
        return fallback

    catalog_values = [int(found[key]["interval_s"]) for key in ("plans", "batches") if found.get(key, {}).get("enabled")]
    return {
        "fleet": pick("fleet", settings.fleet_interval_s),
        "slots": pick("slots", settings.slots_interval_s),
        "runs": pick("runs", settings.runs_interval_s),
        "agg": pick("agg", settings.agg_interval_s),
        "catalog": min(catalog_values) if catalog_values else settings.catalog_interval_s,
    }


def _retune(job_id: str, enabled: bool, seconds: int) -> None:
    job = scheduler.get_job(job_id)
    if job is None:
        return
    if not enabled:
        if job.next_run_time is not None:
            scheduler.pause_job(job_id)
        return
    scheduler.reschedule_job(job_id, trigger="interval", seconds=max(1, seconds))
    current = scheduler.get_job(job_id)
    if current is not None and current.next_run_time is None:
        scheduler.resume_job(job_id)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

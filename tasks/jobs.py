import logging
import time
from dataclasses import asdict

from core.clock import now_ms
from core.config import settings
from core.db import SessionLocal
from repo.alarm_repo import AlarmRepo
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.cluster_sync import ClusterSync
from service.overview.alarm_service import AlarmService
from service.overview.machine_service import MachineService
from service.overview.stats_service import StatsService
from service.realtime import hub
from tasks.record import record_job

log = logging.getLogger(__name__)


class _Backoff:
    def __init__(self) -> None:
        self.until = 0.0
        self.delay = 5.0

    def ready(self) -> bool:
        return time.time() >= self.until

    def ok(self) -> None:
        self.delay = 5.0
        self.until = 0.0

    def fail(self) -> None:
        self.delay = min(self.delay * 2, 300)
        self.until = time.time() + self.delay


_fleet_backoff = _Backoff()
_slots_backoff = _Backoff()
_runs_backoff = _Backoff()


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


async def sync_fleet() -> None:
    await _sync("sync.fleet", _fleet_backoff, lambda sync: sync.sync_fleet(), publish_slots=False)


async def sync_slots() -> None:
    await _sync("sync.slots", _slots_backoff, lambda sync: sync.sync_slots(), publish_slots=True)


async def sync_runs() -> None:
    if not settings.cluster_sync_enabled or not _runs_backoff.ready():
        return
    started = now_ms()
    try:
        async with SessionLocal() as session:
            count = await ClusterSync(MachineRepo(session), StatsRepo(session)).sync_runs()
            await session.commit()
        _runs_backoff.ok()
        if count:
            await record_job("sync.runs", "scheduled", "ok", started, f"upsert={count}")
            await rollup_agg()
    except Exception as exc:
        _runs_backoff.fail()
        log.warning("sync.runs failed, retry in %.0fs: %r", _runs_backoff.delay, exc)
        await record_job("sync.runs", "scheduled", "failed", started, str(exc))


async def rollup_agg() -> None:
    started = now_ms()
    try:
        async with SessionLocal() as session:
            rows = await StatsService(StatsRepo(session), MachineRepo(session), AlarmRepo(session)).rebuild_recent(16)
            await session.commit()
        if rows:
            await hub.publish("agg_5m", asdict(rows[-1]))
        await record_job("rollup.agg", "scheduled", "ok", started, f"buckets={len(rows)}")
    except Exception as exc:
        log.exception("rollup.agg failed")
        await record_job("rollup.agg", "scheduled", "failed", started, str(exc))


async def scan_alarms() -> None:
    started = now_ms()
    try:
        async with SessionLocal() as session:
            created = await AlarmService(
                AlarmRepo(session), MachineRepo(session), StatsRepo(session), AuditRepo(session),
            ).scan()
            await session.commit()
        for alarm in created:
            await hub.publish("alarms", asdict(alarm))
        if created:
            from tasks.triggers import trigger_bus

            for alarm in created:
                trigger_bus.emit("alarm.attribution", {"alarm_id": alarm.id})
            await record_job("scan.alarms", "scheduled", "ok", started, f"created={len(created)}")
    except Exception as exc:
        log.exception("scan.alarms failed")
        await record_job("scan.alarms", "scheduled", "failed", started, str(exc))


async def _sync(name: str, backoff: _Backoff, call, publish_slots: bool) -> None:
    if not settings.cluster_sync_enabled or not backoff.ready():
        return
    started = now_ms()
    try:
        async with SessionLocal() as session:
            changed = await call(ClusterSync(MachineRepo(session), StatsRepo(session)))
            await session.commit()
        backoff.ok()
        if changed:
            await record_job(name, "scheduled", "ok", started, ",".join(changed))
            await _publish(changed, publish_slots)
    except Exception as exc:
        backoff.fail()
        log.warning("%s failed, retry in %.0fs: %r", name, backoff.delay, exc)
        await record_job(name, "scheduled", "failed", started, str(exc))


async def _publish(machine_ids: list[str], slots: bool) -> None:
    wanted = set(machine_ids)
    async with SessionLocal() as session:
        service = MachineService(MachineRepo(session), StatsRepo(session))
        summaries = [item.model_dump() for item in await service.summaries() if item.machine_id in wanted]
        slot_payloads = []
        if slots:
            for machine_id in machine_ids:
                machine = await service.get_machine(machine_id)
                slot_payloads.append({"machine_id": machine_id, "slots": [slot.model_dump() for slot in machine.slots]})
    if summaries:
        await hub.publish("fleet", summaries)
    for payload in slot_payloads:
        await hub.publish("slots", payload)

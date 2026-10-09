import logging
from typing import Any

import httpx

from core.clock import now_ms
from core.config import settings
from models.entity.overview import MachineEntity, RunEntity, SlotEntity
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo

log = logging.getLogger(__name__)


class ClusterClient:
    def __init__(self) -> None:
        self.base = settings.cluster_base_url.rstrip("/")

    async def get(self, path: str) -> Any:
        headers = {}
        if settings.cluster_token:
            headers["Authorization"] = f"Bearer {settings.cluster_token}"
        async with httpx.AsyncClient(base_url=self.base, timeout=settings.cluster_timeout_s) as client:
            response = await client.get(path, headers=headers)
            response.raise_for_status()
            return response.json()


def _items(payload: Any, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def machine_from_cluster(raw: dict, synced_at: int) -> MachineEntity | None:
    machine_id = raw.get("machine_id")
    if not machine_id:
        return None
    slots = []
    for slot in raw.get("slots") or []:
        parsed = slot_from_cluster(slot)
        if parsed:
            slots.append(parsed)
    return MachineEntity(
        machine_id=str(machine_id),
        serial=str(raw.get("serial") or ""),
        fixture=str(raw.get("fixture") or ""),
        holder=str(raw.get("holder") or ""),
        thermal_boards=str(raw.get("thermal_boards") or ""),
        plc=str(raw.get("plc") or "INOVANCE"),
        firmware=str(raw.get("firmware") or ""),
        slot_count=int(raw.get("slot_count") or len(slots) or 10),
        status=str(raw.get("status") or "OFFLINE"),
        comm_status=str(raw.get("comm_status") or "ONLINE"),
        comm_note=str(raw.get("comm_note") or ""),
        speed=float(raw.get("speed") or 1),
        room_temp_c=float(raw.get("room_temp_c") or 0),
        alarm=str(raw.get("alarm") or ""),
        plan_id=raw.get("plan_id"),
        plan_version=raw.get("plan_version"),
        capability=raw.get("capability") or {},
        slots=slots,
        last_sync_at=synced_at,
    )


def slot_from_cluster(raw: dict) -> SlotEntity | None:
    if "index" not in raw:
        return None
    temps = raw.get("temps") or {}
    return SlotEntity(
        index=int(raw["index"]),
        phase=str(raw.get("phase") or "IDLE"),
        serial_number=raw.get("serial_number"),
        tests_done=int(raw.get("tests_done") or 0),
        last_error=str(raw.get("last_error") or ""),
        power_w=float(raw.get("power_w") or 0),
        vacuum_kpa=float(raw.get("vacuum_kpa") or 0),
        t0=float(raw.get("t0") if raw.get("t0") is not None else temps.get("T0") or 0),
        t1=float(raw.get("t1") if raw.get("t1") is not None else temps.get("T1") or 0),
        ta=float(raw.get("ta") if raw.get("ta") is not None else temps.get("Ta") or 0),
        progress=float(raw.get("progress") or 0),
        run_id=raw.get("run_id"),
    )


def run_from_cluster(raw: dict) -> RunEntity | None:
    run_id = raw.get("run_id")
    if not run_id:
        return None
    deltas = (raw.get("result") or {}).get("deltas") or {}
    rc = raw.get("rc", deltas.get("Rc"))
    dt01 = raw.get("dt01", deltas.get("Temp_T0-T1"))
    return RunEntity(
        run_id=str(run_id),
        machine_id=str(raw.get("machine_id") or ""),
        slot_index=int(raw.get("slot_index") or 0),
        serial_number=str(raw.get("serial_number") or ""),
        plan_id=str(raw.get("plan_id") or ""),
        plan_version=int(raw.get("plan_version") or 0),
        status=str(raw.get("status") or "COMPLETED"),
        passed=raw.get("passed"),
        fail_items=list(raw.get("fail_items") or []),
        keep_result=bool(raw.get("keep_result", True)),
        rc=None if rc is None else float(rc),
        dt01=None if dt01 is None else float(dt01),
        batch_id=str(raw.get("batch_id") or ""),
        ended_at=int(raw.get("ended_at") or now_ms()),
    )


class ClusterSync:
    def __init__(self, machines: MachineRepo, stats: StatsRepo, client: ClusterClient | None = None):
        self.machines = machines
        self.stats = stats
        self.client = client or ClusterClient()

    async def sync_fleet(self) -> list[str]:
        payload = await self.client.get("/fleet")
        changed: list[str] = []
        synced = now_ms()
        current = {row.machine_id: row for row in await self.machines.list_all()}
        for raw in _items(payload, "machines", "items"):
            entity = machine_from_cluster(raw, synced)
            if entity is None:
                continue
            old = current.get(entity.machine_id)
            if old is None or _machine_changed(old, entity):
                changed.append(entity.machine_id)
            if not entity.slots and old is not None:
                entity.slots = old.slots
            await self.machines.save_machine(entity)
            if entity.slots:
                await self.machines.replace_slots(entity.machine_id, entity.slots)
        return changed

    async def sync_slots(self) -> list[str]:
        changed: list[str] = []
        for machine in await self.machines.list_all():
            if machine.comm_status == "DISCONNECTED":
                continue
            payload = await self.client.get(f"/machines/{machine.machine_id}/slots")
            slots = [slot for row in _items(payload, "slots", "items") if (slot := slot_from_cluster(row))]
            if not slots:
                continue
            if _slots_changed(machine.slots, slots):
                changed.append(machine.machine_id)
            await self.machines.replace_slots(machine.machine_id, slots)
        return changed

    async def sync_runs(self) -> int:
        since = await self.stats.latest_ended_at()
        payload = await self.client.get(f"/runs?since={since}")
        count = 0
        for raw in _items(payload, "runs", "items"):
            run = run_from_cluster(raw)
            if run is None:
                continue
            await self.stats.upsert_run(run)
            count += 1
        return count


def _machine_changed(old: MachineEntity, new: MachineEntity) -> bool:
    return (old.status, old.comm_status, old.alarm, old.plan_id, old.plan_version) != (
        new.status, new.comm_status, new.alarm, new.plan_id, new.plan_version,
    )


def _slots_changed(old: list[SlotEntity], new: list[SlotEntity]) -> bool:
    left = [(s.index, s.phase, s.progress, s.run_id, s.last_error) for s in old]
    right = [(s.index, s.phase, s.progress, s.run_id, s.last_error) for s in new]
    return left != right

import logging
from typing import Any

import httpx

from core.clock import now_ms
from service.platform_state import endpoint
from models.entity.overview import MachineEntity, RunEntity, SlotEntity
from repo.machine_repo import MachineRepo
from repo.production_repo import ProductionRepo
from repo.stats_repo import StatsRepo

log = logging.getLogger(__name__)


class ClusterClient:
    def __init__(self) -> None:
        self.base = endpoint()[0]

    async def get(self, path: str, timeout: float | None = None) -> Any:
        return await self._send("GET", path, timeout=timeout)

    async def post(self, path: str, body: dict | None = None) -> Any:
        return await self._send("POST", path, body)

    async def put(self, path: str, body: dict) -> Any:
        return await self._send("PUT", path, body)

    async def delete(self, path: str) -> Any:
        return await self._send("DELETE", path)

    async def _send(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> Any:
        base, token, default_timeout = endpoint()
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(base_url=base, timeout=timeout or default_timeout) as client:
            response = await client.request(method, path, headers=headers, json=body)
            response.raise_for_status()
            if not response.content:
                return {}
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


def _channel_map(raw: dict) -> dict:
    temps = raw.get("temps")
    if isinstance(temps, dict):
        return temps
    if isinstance(temps, list):
        return {
            str(item.get("channel")): item.get("value")
            for item in temps
            if isinstance(item, dict) and item.get("channel")
        }
    return {}


def _reading(raw: dict, temps: dict, name: str) -> float:
    direct = raw.get(name.lower())
    if direct is not None and not isinstance(direct, (dict, list)):
        return float(direct)
    value = temps.get(name)
    return float(value or 0)


def slot_from_cluster(raw: dict) -> SlotEntity | None:
    if "index" not in raw:
        return None
    temps = _channel_map(raw)
    return SlotEntity(
        index=int(raw["index"]),
        phase=str(raw.get("phase") or "IDLE"),
        serial_number=raw.get("serial_number"),
        tests_done=int(raw.get("tests_done") or 0),
        last_error=str(raw.get("last_error") or ""),
        power_w=float(raw.get("power_w") or 0),
        vacuum_kpa=float(raw.get("vacuum_kpa") or 0),
        t0=_reading(raw, temps, "T0"),
        t1=_reading(raw, temps, "T1"),
        ta=_reading(raw, temps, "Ta"),
        progress=float(raw.get("progress") or 0),
        run_id=raw.get("run_id"),
    )


def run_from_cluster(raw: dict) -> RunEntity | None:
    run_id = raw.get("run_id")
    if not run_id:
        return None
    result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    deltas = result.get("deltas") if isinstance(result.get("deltas"), dict) else {}
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
        ended_at=int(raw["ended_at"]) if raw.get("ended_at") else 0,
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
        listed = [str(raw["machine_id"]) for raw in _items(payload, "machines", "items") if raw.get("machine_id")]
        current = {row.machine_id: row for row in await self.machines.list_all()}
        failures = 0
        saved = 0
        for raw in _items(payload, "machines", "items"):
            try:
                machine_id = raw.get("machine_id")
                if machine_id and not raw.get("serial"):
                    detail = await self.client.get(f"/machines/{machine_id}")
                    if not isinstance(detail, dict):
                        continue
                    raw = detail
                entity = machine_from_cluster(raw, synced)
            except Exception:
                failures += 1
                log.warning("机台详情同步失败", exc_info=True)
                continue
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
            saved += 1
        if failures and saved == 0:
            raise RuntimeError(f"{failures} 台机台详情同步失败")
        if listed and saved:
            removed = await self.machines.delete_except(set(listed))
            changed.extend(removed)
        return changed

    async def sync_slots(self) -> list[str]:
        changed: list[str] = []
        failures = 0
        saved = 0
        for machine in await self.machines.list_all():
            if machine.comm_status == "DISCONNECTED":
                continue
            try:
                payload = await self.client.get(f"/machines/{machine.machine_id}/slots")
            except Exception:
                failures += 1
                log.warning("槽位同步失败 %s", machine.machine_id, exc_info=True)
                continue
            slots = [slot for row in _items(payload, "slots", "items") if (slot := slot_from_cluster(row))]
            if not slots:
                continue
            if _slots_changed(machine.slots, slots):
                changed.append(machine.machine_id)
            await self.machines.replace_slots(machine.machine_id, slots)
            saved += 1
        if failures and saved == 0:
            raise RuntimeError(f"{failures} 台槽位同步失败")
        return changed

    async def sync_runs(self) -> int:
        payload = await self.client.get("/runs")
        known = [row.batch_id for row in await ProductionRepo(self.stats.session).batches()]
        keep: set[str] = set()
        for raw in _items(payload, "runs", "items"):
            run = run_from_cluster(raw)
            if run is None:
                continue
            if not run.batch_id:
                run.batch_id = batch_of_serial(run.serial_number, known)
            await self.stats.upsert_run(run)
            result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
            await ProductionRepo(self.stats.session).save_result(run.run_id, result)
            keep.add(run.run_id)
        await self.stats.delete_runs_except(keep)
        return len(keep)


def batch_of_serial(serial: str, batch_ids: list[str]) -> str:
    serial = serial.strip()
    if not serial:
        return ""
    matches = [batch_id for batch_id in batch_ids if batch_id and (serial == batch_id or serial.startswith(batch_id + "-"))]
    if not matches:
        return ""
    return max(matches, key=len)


def _machine_changed(old: MachineEntity, new: MachineEntity) -> bool:
    return (old.status, old.comm_status, old.alarm, old.plan_id, old.plan_version) != (
        new.status, new.comm_status, new.alarm, new.plan_id, new.plan_version,
    )


def _slots_changed(old: list[SlotEntity], new: list[SlotEntity]) -> bool:
    left = [(s.index, s.phase, s.progress, s.run_id, s.last_error) for s in old]
    right = [(s.index, s.phase, s.progress, s.run_id, s.last_error) for s in new]
    return left != right

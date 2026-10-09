from dataclasses import asdict

from core.errors import ApiError
from models.dto.overview import CurveOut, MachineOut, MachineSummaryOut
from models.entity.overview import CurveEntity, CurvePoint, MachineEntity, YieldRecent
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo


class MachineService:
    def __init__(self, machines: MachineRepo, stats: StatsRepo):
        self.machines = machines
        self.stats = stats

    async def list_machines(self) -> list[MachineOut]:
        rows = await self._with_yield(await self.machines.list_all())
        return [MachineOut.model_validate(asdict(row)) for row in rows]

    async def get_machine(self, machine_id: str) -> MachineOut:
        row = await self.machines.get(machine_id)
        if row is None:
            raise ApiError(404, "NOT_FOUND", f"机台 {machine_id} 不存在")
        await self._with_yield([row])
        return MachineOut.model_validate(asdict(row))

    async def summaries(self) -> list[MachineSummaryOut]:
        rows = await self._with_yield(await self.machines.list_all())
        out = []
        for row in rows:
            data = asdict(row)
            data.pop("capability", None)
            data.pop("slots", None)
            out.append(MachineSummaryOut.model_validate(data))
        return out

    async def curve(self, machine_id: str, index: int, since: float | None) -> CurveOut:
        machine = await self.machines.get(machine_id)
        if machine is None:
            raise ApiError(404, "NOT_FOUND", f"机台 {machine_id} 不存在")
        slot = next((item for item in machine.slots if item.index == index), None)
        if slot is None:
            raise ApiError(404, "NOT_FOUND", f"{machine_id} 没有槽位 {index}")
        run = await self.stats.get_run(slot.run_id) if slot.run_id else None
        if run is None:
            run = await self.stats.latest_run_for_slot(machine_id, index)
        plans = await self.stats.plans()
        plan_id = run.plan_id if run else machine.plan_id
        plan = next((item for item in plans if item.plan_id == plan_id and item.version == (run.plan_version if run else machine.plan_version)), None)
        if plan is None:
            plan = next((item for item in plans if item.plan_id == plan_id), None)
        points: list[CurvePoint] = []
        if run is not None:
            samples = await self.machines.samples(run.run_id, since)
            points = [CurvePoint(row.t_s, row.t0, row.t1, row.ta, row.power_w) for row in samples]
        deltas: dict[str, float] = {}
        if points:
            last = points[-1]
            deltas["Temp_T0-T1"] = round(last.T0 - last.T1, 3)
            if last.power_w:
                deltas["Rc"] = round((last.T1 - last.Ta) / last.power_w, 3)
        elif run is not None:
            if run.dt01 is not None:
                deltas["Temp_T0-T1"] = run.dt01
            if run.rc is not None:
                deltas["Rc"] = run.rc
        entity = CurveEntity(
            run_id=run.run_id if run else slot.run_id,
            plan_id=plan.plan_id if plan else plan_id,
            plan_version=plan.version if plan else (run.plan_version if run else machine.plan_version),
            duration_s=plan.duration_s if plan else 180,
            points=points,
            deltas=deltas,
        )
        return CurveOut.model_validate(asdict(entity))

    async def _with_yield(self, rows: list[MachineEntity]) -> list[MachineEntity]:
        recent = await self.stats.recent_runs(5000)
        counts: dict[str, YieldRecent] = {}
        for run in recent:
            if run.passed is None:
                continue
            bucket = counts.setdefault(run.machine_id, YieldRecent(0, 0))
            if bucket.n >= 400:
                continue
            bucket.n += 1
            if run.passed:
                bucket.passed += 1
        for row in rows:
            row.yield_recent = counts.get(row.machine_id, YieldRecent(0, 0))
        return rows

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entity.overview import MachineEntity, SlotEntity, YieldRecent
from models.orm.alarm import AlarmOrm
from models.orm.machine import ChannelBiasOrm, MachineOrm, RunSampleOrm, SlotOrm
from models.orm.stats import BatchStatOrm, RunOrm
from repo.mappers import machine_entity


class MachineRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def count(self) -> int:
        rows = await self.session.scalars(select(MachineOrm.machine_id))
        return len(list(rows))

    async def list_all(self) -> list[MachineEntity]:
        machines = list(await self.session.scalars(select(MachineOrm).order_by(MachineOrm.machine_id)))
        slots = list(await self.session.scalars(select(SlotOrm).order_by(SlotOrm.machine_id, SlotOrm.index)))
        grouped: dict[str, list[SlotOrm]] = {}
        for slot in slots:
            grouped.setdefault(slot.machine_id, []).append(slot)
        return [machine_entity(m, grouped.get(m.machine_id, [])) for m in machines]

    async def get(self, machine_id: str) -> MachineEntity | None:
        row = await self.session.get(MachineOrm, machine_id)
        if row is None:
            return None
        slots = list(await self.session.scalars(
            select(SlotOrm).where(SlotOrm.machine_id == machine_id).order_by(SlotOrm.index)
        ))
        return machine_entity(row, slots)

    async def save_machine(self, entity: MachineEntity) -> None:
        row = await self.session.get(MachineOrm, entity.machine_id)
        values = dict(
            serial=entity.serial,
            fixture=entity.fixture,
            holder=entity.holder,
            thermal_boards=entity.thermal_boards,
            plc=entity.plc,
            firmware=entity.firmware,
            slot_count=entity.slot_count,
            status=entity.status,
            comm_status=entity.comm_status,
            comm_note=entity.comm_note,
            speed=entity.speed,
            room_temp_c=entity.room_temp_c,
            alarm=entity.alarm,
            plan_id=entity.plan_id,
            plan_version=entity.plan_version,
            capability=entity.capability,
            last_sync_at=entity.last_sync_at,
        )
        if row is None:
            self.session.add(MachineOrm(machine_id=entity.machine_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
        await self.session.flush()

    async def replace_slots(self, machine_id: str, slots: list[SlotEntity]) -> None:
        existing = list(await self.session.scalars(select(SlotOrm).where(SlotOrm.machine_id == machine_id)))
        by_index = {row.index: row for row in existing}
        seen: set[int] = set()
        for slot in slots:
            seen.add(slot.index)
            row = by_index.get(slot.index)
            values = dict(
                phase=slot.phase,
                serial_number=slot.serial_number,
                tests_done=slot.tests_done,
                last_error=slot.last_error,
                power_w=slot.power_w,
                vacuum_kpa=slot.vacuum_kpa,
                t0=slot.t0,
                t1=slot.t1,
                ta=slot.ta,
                progress=slot.progress,
                run_id=slot.run_id,
            )
            if row is None:
                self.session.add(SlotOrm(machine_id=machine_id, index=slot.index, **values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        for row in existing:
            if row.index not in seen:
                await self.session.delete(row)

    async def samples(self, run_id: str, since: float | None) -> list[RunSampleOrm]:
        stmt = select(RunSampleOrm).where(RunSampleOrm.run_id == run_id).order_by(RunSampleOrm.t_s)
        if since is not None:
            stmt = stmt.where(RunSampleOrm.t_s > since)
        return list(await self.session.scalars(stmt))

    async def add_samples(self, run_id: str, points: list[tuple[float, float, float, float, float]]) -> None:
        have = {row.t_s for row in await self.samples(run_id, None)}
        for t_s, t0, t1, ta, power in points:
            if t_s in have:
                continue
            self.session.add(RunSampleOrm(run_id=run_id, t_s=t_s, t0=t0, t1=t1, ta=ta, power_w=power))

    async def delete_except(self, keep: set[str]) -> list[str]:
        """去掉当前集群列表里没有的机台，以及只属于这些机台的记录。"""
        ids = list(await self.session.scalars(select(MachineOrm.machine_id)))
        remove = [machine_id for machine_id in ids if machine_id not in keep]
        if not remove:
            return []
        await self.session.execute(delete(RunOrm).where(RunOrm.machine_id.in_(remove)))
        await self.session.execute(delete(AlarmOrm).where(AlarmOrm.machine_id.in_(remove)))
        await self.session.execute(delete(ChannelBiasOrm).where(ChannelBiasOrm.machine_id.in_(remove)))
        await self.session.execute(delete(BatchStatOrm))
        await self.session.execute(delete(MachineOrm).where(MachineOrm.machine_id.in_(remove)))
        return remove

    async def channel_biases(self) -> list[ChannelBiasOrm]:
        return list(await self.session.scalars(select(ChannelBiasOrm)))

    async def add_bias(self, machine_id: str, channel: str, value: float, measured_at: int) -> None:
        self.session.add(ChannelBiasOrm(machine_id=machine_id, channel=channel, value=value, measured_at=measured_at))

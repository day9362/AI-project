from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms

from models.entity.overview import AggEntity, BatchBrief, PlanEntity, RunEntity
from models.orm.stats import Agg5mOrm, BatchStatOrm, PlanOrm, RunOrm
from repo.mappers import agg_entity, batch_brief, plan_entity, run_entity


class StatsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def runs_between(self, start_ms: int, end_ms: int) -> list[RunEntity]:
        rows = await self.session.scalars(
            select(RunOrm).where(RunOrm.ended_at >= start_ms, RunOrm.ended_at < end_ms).order_by(RunOrm.ended_at)
        )
        return [run_entity(row) for row in rows]

    async def recent_runs(self, limit: int) -> list[RunEntity]:
        rows = await self.session.scalars(select(RunOrm).order_by(RunOrm.ended_at.desc()).limit(limit))
        return [run_entity(row) for row in rows]

    async def latest_ended_at(self) -> int:
        row = await self.session.scalar(select(RunOrm.ended_at).order_by(RunOrm.ended_at.desc()).limit(1))
        return int(row or 0)

    async def upsert_run(self, run: RunEntity) -> None:
        row = await self.session.get(RunOrm, run.run_id)
        values = dict(
            machine_id=run.machine_id,
            slot_index=run.slot_index,
            serial_number=run.serial_number,
            plan_id=run.plan_id,
            plan_version=run.plan_version,
            status=run.status,
            passed=run.passed,
            fail_items=run.fail_items,
            keep_result=run.keep_result,
            rc=run.rc,
            dt01=run.dt01,
            batch_id=run.batch_id,
            ended_at=run.ended_at,
        )
        if row is None:
            if not values["ended_at"]:
                values["ended_at"] = now_ms()
            self.session.add(RunOrm(run_id=run.run_id, **values))
        else:
            if not values["ended_at"]:
                values.pop("ended_at")
            if not values["batch_id"]:
                values.pop("batch_id")
            for key, value in values.items():
                setattr(row, key, value)

    async def delete_runs_except(self, keep_ids: set[str]) -> int:
        if not keep_ids:
            result = await self.session.execute(delete(RunOrm))
            return int(result.rowcount or 0)
        result = await self.session.execute(delete(RunOrm).where(RunOrm.run_id.not_in(keep_ids)))
        return int(result.rowcount or 0)

    async def get_run(self, run_id: str) -> RunEntity | None:
        row = await self.session.get(RunOrm, run_id)
        return run_entity(row) if row else None

    async def latest_run_for_slot(self, machine_id: str, slot_index: int) -> RunEntity | None:
        row = await self.session.scalar(
            select(RunOrm)
            .where(RunOrm.machine_id == machine_id, RunOrm.slot_index == slot_index)
            .order_by(RunOrm.ended_at.desc())
            .limit(1)
        )
        return run_entity(row) if row else None

    async def agg_between(self, start_ms: int, end_ms: int) -> list[AggEntity]:
        rows = await self.session.scalars(
            select(Agg5mOrm).where(Agg5mOrm.bucket >= start_ms, Agg5mOrm.bucket < end_ms).order_by(Agg5mOrm.bucket)
        )
        return [agg_entity(row) for row in rows]

    async def replace_agg(self, rows: list[AggEntity]) -> None:
        if not rows:
            return
        start, end = rows[0].bucket, rows[-1].bucket
        await self.session.execute(delete(Agg5mOrm).where(Agg5mOrm.bucket >= start, Agg5mOrm.bucket <= end))
        await self.session.flush()
        for row in rows:
            self.session.add(Agg5mOrm(
                bucket=row.bucket, tests=row.tests, passed=row.passed, failed=row.failed,
                aborted=row.aborted, rc_mean=row.rc_mean, dt01_mean=row.dt01_mean,
            ))

    async def plans(self) -> list[PlanEntity]:
        rows = await self.session.scalars(select(PlanOrm))
        return [plan_entity(row) for row in rows]

    async def add_plan(self, plan: PlanEntity) -> None:
        self.session.add(PlanOrm(
            plan_id=plan.plan_id, version=plan.version, name=plan.name, duration_s=plan.duration_s,
            power_w=plan.power_w, start_temp_c=plan.start_temp_c, ambient_low_c=plan.ambient_low_c,
            ambient_high_c=plan.ambient_high_c, draft=plan.draft,
        ))

    async def batches(self) -> list[BatchBrief]:
        rows = await self.session.scalars(select(BatchStatOrm))
        return [batch_brief(row) for row in rows]

    async def add_batch(self, batch: BatchBrief, model: str = "") -> None:
        self.session.add(BatchStatOrm(
            batch_id=batch.batch_id, model=model, count=batch.count, tested=batch.tested, state=batch.state,
            plan_id=batch.plan_id, plan_version=batch.plan_version,
        ))

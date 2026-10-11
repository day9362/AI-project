from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entity.overview import PlanEntity
from models.orm.plan import PlanRevisionOrm
from models.orm.stats import PlanOrm


class PlanRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_revisions(self) -> list[PlanRevisionOrm]:
        rows = await self.session.scalars(select(PlanRevisionOrm).order_by(PlanRevisionOrm.updated_at.desc()))
        return list(rows.all())

    async def get(self, plan_id: str, version: int) -> PlanRevisionOrm | None:
        return await self.session.get(PlanRevisionOrm, (plan_id, version))

    async def versions(self, plan_id: str) -> list[int]:
        rows = await self.session.scalars(
            select(PlanRevisionOrm.version).where(
                PlanRevisionOrm.plan_id == plan_id, PlanRevisionOrm.draft.is_(False)
            )
        )
        return sorted(int(value) for value in rows.all())

    async def latest_published(self, plan_id: str) -> PlanRevisionOrm | None:
        return await self.session.scalar(
            select(PlanRevisionOrm)
            .where(PlanRevisionOrm.plan_id == plan_id, PlanRevisionOrm.draft.is_(False))
            .order_by(PlanRevisionOrm.version.desc())
            .limit(1)
        )

    async def find_published_name(self, name: str) -> PlanRevisionOrm | None:
        return await self.session.scalar(
            select(PlanRevisionOrm)
            .where(PlanRevisionOrm.name == name, PlanRevisionOrm.draft.is_(False))
            .order_by(PlanRevisionOrm.version.desc())
            .limit(1)
        )

    async def save(self, row: PlanRevisionOrm) -> None:
        await self.session.merge(row)

    async def delete(self, row: PlanRevisionOrm) -> None:
        await self.session.delete(row)

    async def upsert_slim(self, plan: PlanEntity) -> None:
        current = await self.session.get(PlanOrm, (plan.plan_id, plan.version))
        if current is None:
            self.session.add(
                PlanOrm(
                    plan_id=plan.plan_id,
                    version=plan.version,
                    name=plan.name,
                    duration_s=plan.duration_s,
                    power_w=plan.power_w,
                    start_temp_c=plan.start_temp_c,
                    ambient_low_c=plan.ambient_low_c,
                    ambient_high_c=plan.ambient_high_c,
                    draft=plan.draft,
                )
            )
            return
        current.name = plan.name
        current.duration_s = plan.duration_s
        current.power_w = plan.power_w
        current.start_temp_c = plan.start_temp_c
        current.ambient_low_c = plan.ambient_low_c
        current.ambient_high_c = plan.ambient_high_c
        current.draft = plan.draft

import base64

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.orm.production import BatchRecordOrm, PlanDispatchOrm, ProductModelOrm, ProductionOrm, RunDetailOrm
from models.orm.stats import BatchStatOrm, RunOrm


def encode_cursor(mark: int, item_id: str) -> str:
    raw = f"{mark}|{item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, str]:
    pad = "=" * (-len(cursor) % 4)
    mark, item_id = base64.urlsafe_b64decode(cursor + pad).decode().split("|", 1)
    return int(mark), item_id


class ProductionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def models(self) -> list[ProductModelOrm]:
        rows = await self.session.scalars(select(ProductModelOrm).order_by(ProductModelOrm.model))
        return list(rows.all())

    async def replace_models(self, rows: list[ProductModelOrm]) -> None:
        await self.session.execute(delete(ProductModelOrm))
        for row in rows:
            self.session.add(row)

    async def model(self, name: str) -> ProductModelOrm | None:
        return await self.session.get(ProductModelOrm, name)

    async def batches(self) -> list[BatchRecordOrm]:
        rows = await self.session.scalars(select(BatchRecordOrm).order_by(BatchRecordOrm.started_at.desc()))
        return list(rows.all())

    async def batch(self, batch_id: str) -> BatchRecordOrm | None:
        return await self.session.get(BatchRecordOrm, batch_id)

    async def save_batch(self, row: BatchRecordOrm) -> None:
        await self.session.merge(row)
        await self.session.merge(BatchStatOrm(
            batch_id=row.batch_id,
            model=row.model,
            count=row.count,
            tested=row.tested,
            state=row.state,
            plan_id=row.plan_id,
            plan_version=row.plan_version,
        ))

    async def page_batches(
        self, *, state: str | None, model: str | None, q: str | None, cursor: str | None, limit: int,
    ) -> tuple[list[BatchRecordOrm], str | None]:
        stmt = select(BatchRecordOrm)
        if state:
            stmt = stmt.where(BatchRecordOrm.state == state)
        if model:
            stmt = stmt.where(BatchRecordOrm.model == model)
        if q:
            stmt = stmt.where(BatchRecordOrm.batch_id.ilike(f"%{q}%"))
        if cursor:
            mark, batch_id = decode_cursor(cursor)
            stmt = stmt.where(or_(
                BatchRecordOrm.started_at < mark,
                and_(BatchRecordOrm.started_at == mark, BatchRecordOrm.batch_id > batch_id),
            ))
        stmt = stmt.order_by(BatchRecordOrm.started_at.desc(), BatchRecordOrm.batch_id).limit(limit + 1)
        rows = list((await self.session.scalars(stmt)).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.started_at, last.batch_id)
        return rows, next_cursor

    async def production(self) -> ProductionOrm | None:
        row = await self.session.get(ProductionOrm, 1)
        if row is None or not row.active:
            return None
        return row

    async def save_production(self, row: ProductionOrm) -> None:
        row.id = 1
        await self.session.merge(row)

    async def add_dispatch(self, row: PlanDispatchOrm) -> None:
        self.session.add(row)

    async def save_result(self, run_id: str, result: dict) -> None:
        await self.session.merge(RunDetailOrm(run_id=run_id, result=result))

    async def result(self, run_id: str) -> dict:
        row = await self.session.get(RunDetailOrm, run_id)
        return dict(row.result) if row else {}

    async def page_runs(self, filters: dict, cursor: str | None, limit: int) -> tuple[list[RunOrm], str | None]:
        stmt = select(RunOrm)
        if filters.get("machine_id"):
            stmt = stmt.where(RunOrm.machine_id == filters["machine_id"])
        if filters.get("batch_id"):
            stmt = stmt.where(RunOrm.batch_id == filters["batch_id"])
        if filters.get("status"):
            stmt = stmt.where(RunOrm.status == filters["status"])
        if "passed" in filters and filters["passed"] != "":
            passed = filters["passed"]
            if passed is None:
                stmt = stmt.where(RunOrm.passed.is_(None))
            else:
                stmt = stmt.where(RunOrm.passed.is_(bool(passed)))
        if filters.get("q"):
            like = f"%{filters['q']}%"
            stmt = stmt.where(or_(RunOrm.run_id.ilike(like), RunOrm.serial_number.ilike(like)))
        if filters.get("from_ms"):
            stmt = stmt.where(RunOrm.ended_at >= filters["from_ms"])
        if filters.get("to_ms"):
            stmt = stmt.where(RunOrm.ended_at < filters["to_ms"])
        if cursor:
            mark, run_id = decode_cursor(cursor)
            stmt = stmt.where(or_(
                RunOrm.ended_at < mark,
                and_(RunOrm.ended_at == mark, RunOrm.run_id > run_id),
            ))
        stmt = stmt.order_by(RunOrm.ended_at.desc(), RunOrm.run_id).limit(limit + 1)
        rows = list((await self.session.scalars(stmt)).all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            last = rows[-1]
            next_cursor = encode_cursor(last.ended_at, last.run_id)
        return rows, next_cursor

    async def runs_for_export(self, batch_id: str | None, from_ms: int | None, to_ms: int | None) -> list[RunOrm]:
        stmt = select(RunOrm).order_by(RunOrm.ended_at)
        if batch_id:
            stmt = stmt.where(RunOrm.batch_id == batch_id)
        if from_ms:
            stmt = stmt.where(RunOrm.ended_at >= from_ms)
        if to_ms:
            stmt = stmt.where(RunOrm.ended_at < to_ms)
        return list((await self.session.scalars(stmt)).all())

    async def runs_of(self, batch_id: str) -> list[RunOrm]:
        rows = await self.session.scalars(select(RunOrm).where(RunOrm.batch_id == batch_id))
        return list(rows.all())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.errors import ApiError
from models.dto.report import ReportOut
from models.orm.plan import PlanRevisionOrm
from models.orm.production import RunDetailOrm
from models.orm.stats import RunOrm
from repo.production_repo import ProductionRepo
from service.report_rules import build_report


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProductionRepo(session)

    async def data(self, batch_ids: list[str]) -> ReportOut:
        ids = _ids(batch_ids)
        batches = []
        for batch_id in ids:
            row = await self.repo.batch(batch_id)
            if row is None:
                raise ApiError(404, "NOT_FOUND", "批次不存在", {"batch_id": batch_id})
            revision = await self.session.get(PlanRevisionOrm, (row.plan_id, row.plan_version))
            batches.append({
                "batch_id": row.batch_id,
                "model": row.model,
                "count": row.count,
                "tested": 0,
                "passed": 0,
                "failed": 0,
                "aborted": 0,
                "plan_id": row.plan_id,
                "plan_version": row.plan_version,
                "plan_name": revision.name if revision is not None else "",
                "machine_ids": list(row.machine_ids or []),
                "started_at": row.started_at,
                "ended_at": row.ended_at,
                "state": row.state,
                "rc_mean": 0,
                "rc_sd": 0,
                "top_fail": "",
                "eta_s": row.eta_s,
            })
        payload = build_report(batches, await self._runs(ids), await self._limits(batches))
        return ReportOut.model_validate(payload)

    async def _runs(self, batch_ids: list[str]) -> list[dict]:
        stmt = (
            select(RunOrm, RunDetailOrm.result)
            .outerjoin(RunDetailOrm, RunDetailOrm.run_id == RunOrm.run_id)
            .where(RunOrm.batch_id.in_(batch_ids))
        )
        rows = (await self.session.execute(stmt)).all()
        return [_run(run, result if isinstance(result, dict) else {}) for run, result in rows]

    async def _limits(self, batches: list[dict]) -> dict[tuple[str, int], list[dict]]:
        found: dict[tuple[str, int], list[dict]] = {}
        for batch in batches:
            key = (batch["plan_id"], batch["plan_version"])
            if key in found or not key[0]:
                continue
            revision = await self.session.get(PlanRevisionOrm, key)
            body = revision.body if revision is not None and isinstance(revision.body, dict) else {}
            found[key] = [item for item in body.get("limits") or [] if isinstance(item, dict)]
        return found


def _ids(batch_ids: list[str]) -> list[str]:
    ids: list[str] = []
    for raw in batch_ids:
        for part in raw.split(","):
            batch_id = part.strip()
            if batch_id and batch_id not in ids:
                ids.append(batch_id)
    if not ids:
        raise ApiError(400, "BAD_REQUEST", "要指定批次号")
    return ids


def _run(run: RunOrm, result: dict) -> dict:
    deltas = result.get("deltas") if isinstance(result.get("deltas"), dict) else {}
    rc = run.rc if run.rc is not None else _num(deltas.get("Rc"))
    dt01 = run.dt01 if run.dt01 is not None else _num(deltas.get("Temp_T0-T1"))
    return {
        "batch_id": run.batch_id,
        "machine_id": run.machine_id,
        "status": run.status,
        "passed": run.passed,
        "fail_items": list(run.fail_items or []),
        "rc": rc,
        "dt01": dt01,
        "deltas": deltas,
    }


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)

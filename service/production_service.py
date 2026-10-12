import csv
import io

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms
from core.config import settings
from core.errors import ApiError
from models.dto.production import (
    BatchOut,
    ProductModelOut,
    BatchStatOut,
    BatchStatPageOut,
    IssueOut,
    PrecheckOut,
    ProductionIn,
    ProductionOut,
    RunDetailOut,
    RunOut,
    RunPageOut,
    SampleOut,
    SkippedOut,
    StartOut,
    StopOut,
)
from models.entity.user import UserEntity
from models.orm.plan import PlanRevisionOrm
from models.orm.production import PlanDispatchOrm, ProductionOrm
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.production_repo import ProductionRepo, decode_cursor
from repo.stats_repo import StatsRepo
from service.cluster_sync import ClusterClient, _items
from service.mcp_agent import McpCallError, call_test
from service.production_rules import precheck
from service.realtime import hub


class ProductionService:
    def __init__(self, session: AsyncSession, user: UserEntity) -> None:
        self.session = session
        self.user = user
        self.repo = ProductionRepo(session)
        self.machines = MachineRepo(session)
        self.stats = StatsRepo(session)
        self.audit = AuditRepo(session)
        self.cluster = ClusterClient()

    async def models(self) -> list[ProductModelOut]:
        rows = await self.repo.models()
        return [ProductModelOut(model=row.model, resistance_mean=row.resistance_mean, resistance_sd=row.resistance_sd, power_w=row.power_w) for row in rows]

    async def batches(self) -> list[BatchOut]:
        return [BatchOut(
            batch_id=row.batch_id, model=row.model, count=row.count, defect_ratio=row.defect_ratio,
            batch_factor=row.batch_factor, remaining=row.remaining,
        ) for row in await self.repo.batches()]

    async def batch_stats(self, state: str | None, model: str | None, q: str | None, cursor: str | None, limit: int) -> BatchStatPageOut:
        self._limit(limit)
        self._cursor(cursor)
        rows, next_cursor = await self.repo.page_batches(state=state, model=model, q=q, cursor=cursor, limit=limit)
        return BatchStatPageOut(items=[_stat(row) for row in rows], next_cursor=next_cursor)

    async def batch_stat(self, batch_id: str) -> BatchStatOut:
        row = await self.repo.batch(batch_id)
        if row is None:
            raise ApiError(404, "NOT_FOUND", "批次不存在")
        return _stat(row)

    async def production(self) -> ProductionOut | None:
        row = await self.repo.production()
        if row is None:
            return None
        return ProductionOut(batch_id=row.batch_id, queue_remaining=row.queue_remaining, plan_id=row.plan_id, plan_version=row.plan_version)

    async def precheck_body(self, body: ProductionIn) -> PrecheckOut:
        issues = await self._issues(body)
        return PrecheckOut(ok=not any(item.level == "danger" for item in issues), issues=issues)

    async def start(self, body: ProductionIn, key: str | None) -> StartOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return StartOut.model_validate(cached)
        issues = await self._issues(body)
        if any(item.level == "danger" for item in issues):
            raise ApiError(422, "VALIDATION_ERROR", "下发前校验未通过", {"issues": [item.model_dump() for item in issues]})
        try:
            data = await call_test({
                "action": "production",
                "enable": True,
                "machine_ids": body.machine_ids,
                "plan_id": body.plan_id,
                "plan_version": body.plan_version,
                "batch_id": body.batch_id,
                "serial_numbers": body.serial_numbers,
                "auto_recover": body.auto_recover,
                "max_count": body.max_count,
            })
        except McpCallError as exc:
            raise ApiError(502, "CLUSTER_ERROR", str(exc), {"upstream": exc.detail}) from exc
        accepted, skipped = _outcome(data, body.machine_ids)
        batch_id = str(data.get("batch_id") or body.batch_id or "")
        await self.repo.save_production(ProductionOrm(
            id=1, active=True, batch_id=batch_id,
            queue_remaining=int(data.get("queue_remaining") or 0),
            plan_id=body.plan_id, plan_version=body.plan_version,
        ))
        for machine_id in accepted:
            await self.repo.add_dispatch(PlanDispatchOrm(
                machine_id=machine_id, plan_id=body.plan_id, plan_version=body.plan_version,
                batch_id=batch_id, actor=self.user.user_id, accepted=True, created_at=now_ms(),
            ))
        for item in skipped:
            await self.repo.add_dispatch(PlanDispatchOrm(
                machine_id=item.machine_id, plan_id=body.plan_id, plan_version=body.plan_version,
                batch_id=batch_id, actor=self.user.user_id, accepted=False, reason=item.reason, created_at=now_ms(),
            ))
        row = await self.repo.batch(batch_id)
        if row is not None:
            row.state = "running"
            row.ended_at = None
            row.plan_id = body.plan_id
            row.plan_version = body.plan_version
            row.machine_ids = accepted or list(body.machine_ids)
            if not row.started_at:
                row.started_at = now_ms()
            await self.repo.save_batch(row)
        audit_id = await self.audit.write(self.user.user_id, "production.start", {"batch_id": batch_id, "accepted": accepted})
        result = StartOut(batch_id=batch_id, accepted=accepted, skipped=skipped, audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        await hub.publish("production", result.model_dump())
        return result

    async def stop(self, batch_id: str, key: str | None) -> StopOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return StopOut.model_validate(cached)
        try:
            await self.cluster.post("/fleet/production/stop", {"batch_id": batch_id})
        except httpx.TimeoutException as exc:
            raise ApiError(504, "CLUSTER_TIMEOUT", "集群响应超时", {"upstream": repr(exc)}) from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "停止连续生产失败", {"upstream": repr(exc)}) from exc
        current = await self.repo.production()
        if current is not None and current.batch_id == batch_id:
            current.active = False
        row = await self.repo.batch(batch_id)
        if row is not None and row.state == "running":
            row.state = "stopped"
            row.ended_at = now_ms()
            row.eta_s = None
            await self.repo.save_batch(row)
        audit_id = await self.audit.write(self.user.user_id, "production.stop", {"batch_id": batch_id})
        result = StopOut(audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        await hub.publish("production", None)
        return result

    async def runs(self, filters: dict, cursor: str | None, limit: int) -> RunPageOut:
        self._limit(limit)
        self._cursor(cursor)
        rows, next_cursor = await self.repo.page_runs(filters, cursor, limit)
        return RunPageOut(items=[_run(row) for row in rows], next_cursor=next_cursor)

    async def run(self, run_id: str) -> RunDetailOut:
        row = await self.stats.get_run(run_id)
        if row is None:
            raise ApiError(404, "NOT_FOUND", "测试记录不存在")
        base = _run_entity(row)
        return RunDetailOut(**base.model_dump(), result=await self.repo.result(run_id))

    async def samples(self, run_id: str, since: float | None) -> list[SampleOut]:
        if await self.stats.get_run(run_id) is None:
            raise ApiError(404, "NOT_FOUND", "测试记录不存在")
        rows = await self.machines.samples(run_id, since)
        if not rows:
            rows = await self._pull_samples(run_id, since)
        return [SampleOut(seq=index, t_s=row.t_s, t0=row.t0, t1=row.t1, ta=row.ta, power_w=row.power_w) for index, row in enumerate(rows, start=1)]

    async def export_csv(self, batch_id: str | None, from_ms: int | None, to_ms: int | None) -> str:
        rows = await self.repo.runs_for_export(batch_id, from_ms, to_ms)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["run_id", "machine_id", "slot_index", "serial_number", "plan_id", "plan_version", "status", "passed", "fail_items", "rc", "dt01", "batch_id", "ended_at"])
        for row in rows:
            writer.writerow([
                row.run_id, row.machine_id, row.slot_index, row.serial_number, row.plan_id, row.plan_version,
                row.status, row.passed, "|".join(row.fail_items or []), row.rc, row.dt01, row.batch_id, row.ended_at,
            ])
        return buffer.getvalue()

    async def _issues(self, body: ProductionIn) -> list[IssueOut]:
        plan = await self.session.get(PlanRevisionOrm, (body.plan_id, body.plan_version))
        limits = list((plan.body or {}).get("limits") or []) if plan else []
        plan_power = float(plan.body["power_w"]) if plan else None
        model_power = None
        remaining = None
        if body.batch_id:
            batch = await self.repo.batch(body.batch_id)
            if batch is not None:
                remaining = batch.remaining
                model = await self.repo.model(batch.model)
                if model is not None:
                    model_power = model.power_w
        machines = []
        for row in await self.machines.list_all():
            machines.append({
                "machine_id": row.machine_id,
                "status": row.status,
                "comm_status": row.comm_status,
                "plan_id": row.plan_id,
                "plan_version": row.plan_version,
                "speed": row.speed,
                "slots": [{"phase": slot.phase} for slot in row.slots],
            })
        return precheck(
            body, plan_power=plan_power, limits=limits, model_power=model_power,
            remaining=remaining, machines=machines, sim_mode=settings.sim_mode,
        )

    async def _pull_samples(self, run_id: str, since: float | None):
        try:
            payload = await self.cluster.get(f"/runs/{run_id}/samples", timeout=8)
        except httpx.HTTPError:
            return []
        points = []
        for raw in _items(payload, "samples", "items"):
            t_s = raw.get("t_s", raw.get("seq"))
            if t_s is None or (since is not None and float(t_s) <= since):
                continue
            temps = raw.get("temps") if isinstance(raw.get("temps"), dict) else {}
            points.append(type("S", (), {
                "t_s": float(t_s),
                "t0": float(raw.get("t0", temps.get("T0", 0)) or 0),
                "t1": float(raw.get("t1", temps.get("T1", 0)) or 0),
                "ta": float(raw.get("ta", temps.get("Ta", 0)) or 0),
                "power_w": float(raw.get("power_w") or 0),
            })())
        return points

    def _require_key(self, key: str | None) -> None:
        if not key:
            raise ApiError(400, "BAD_REQUEST", "缺少 Idempotency-Key")

    def _limit(self, limit: int) -> None:
        if limit < 1 or limit > 500:
            raise ApiError(400, "BAD_REQUEST", "limit 范围是 1 到 500")

    def _cursor(self, cursor: str | None) -> None:
        if not cursor:
            return
        try:
            decode_cursor(cursor)
        except Exception as exc:
            raise ApiError(400, "BAD_REQUEST", "cursor 无法解析") from exc


def _stat(row) -> BatchStatOut:
    state = row.state if row.state in {"running", "done", "stopped"} else "done"
    return BatchStatOut(
        batch_id=row.batch_id, model=row.model, count=row.count, tested=row.tested, passed=row.passed,
        failed=row.failed, aborted=row.aborted, plan_id=row.plan_id, plan_version=row.plan_version,
        machine_ids=list(row.machine_ids or []), started_at=row.started_at, ended_at=row.ended_at,
        state=state, rc_mean=row.rc_mean, rc_sd=row.rc_sd, top_fail=row.top_fail, eta_s=row.eta_s,
    )


def _run(row) -> RunOut:
    return RunOut(
        run_id=row.run_id, machine_id=row.machine_id, slot_index=row.slot_index, serial_number=row.serial_number,
        plan_id=row.plan_id, plan_version=row.plan_version, status=row.status, passed=row.passed,
        fail_items=list(row.fail_items or []), keep_result=row.keep_result, rc=row.rc, dt01=row.dt01,
        batch_id=row.batch_id, ended_at=row.ended_at,
    )


def _run_entity(row) -> RunOut:
    return RunOut(
        run_id=row.run_id, machine_id=row.machine_id, slot_index=row.slot_index, serial_number=row.serial_number,
        plan_id=row.plan_id, plan_version=row.plan_version, status=row.status, passed=row.passed,
        fail_items=list(row.fail_items or []), keep_result=row.keep_result, rc=row.rc, dt01=row.dt01,
        batch_id=row.batch_id, ended_at=row.ended_at,
    )


def _outcome(data: dict, requested: list[str]) -> tuple[list[str], list[SkippedOut]]:
    skipped_raw = data.get("skipped") if isinstance(data.get("skipped"), list) else []
    skipped = []
    for item in skipped_raw:
        if isinstance(item, dict) and item.get("machine_id"):
            skipped.append(SkippedOut(machine_id=str(item["machine_id"]), reason=str(item.get("reason") or "被跳过")))
    skipped_ids = {item.machine_id for item in skipped}
    accepted_raw = data.get("accepted")
    if isinstance(accepted_raw, list):
        accepted = [str(item) for item in accepted_raw]
    else:
        accepted = [machine_id for machine_id in requested if machine_id not in skipped_ids]
    return accepted, skipped

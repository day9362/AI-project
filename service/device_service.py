import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms
from core.config import settings
from core.errors import ApiError
from models.dto.device import (
    AuditOnlyOut,
    ChannelBiasOut,
    CompensationHistoryOut,
    CompensationIn,
    CompensationOut,
    DriftsOut,
    MaintenanceIn,
    PlanHistoryOut,
    SuggestionOut,
)
from models.dto.overview import MachineOut
from models.entity.user import UserEntity
from models.orm.machine import CompensationWriteOrm
from models.orm.plan import PlanRevisionOrm
from models.orm.production import PlanDispatchOrm
from models.orm.stats import RunOrm
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.cluster_sync import ClusterClient, machine_from_cluster
from service.device_rules import (
    cluster_compensation,
    compensation_channels,
    compensation_suggestion,
    drift_rows,
    ensure_online,
    plan_spans,
    sampling_run_ids,
)
from service.overview.machine_service import MachineService
from service.platform_state import live
from service.realtime import hub


class DeviceService:
    def __init__(self, session: AsyncSession, user: UserEntity) -> None:
        self.session = session
        self.user = user
        self.machines = MachineRepo(session)
        self.stats = StatsRepo(session)
        self.audit = AuditRepo(session)
        self.cluster = ClusterClient()

    async def power_on(self, machine_id: str, key: str | None) -> AuditOnlyOut:
        return await self._operate(machine_id, key, "machine.power_on", "POST", "/fleet/power-on", {"machine_ids": [machine_id]})

    async def power_off(self, machine_id: str, key: str | None) -> AuditOnlyOut:
        machine = await self._online(machine_id)
        result = await self._operate(
            machine_id, key, "machine.power_off", "POST", f"/machines/{machine_id}/power-off", None, machine=machine,
        )
        await self._abort(machine)
        return result

    async def maintenance(self, machine_id: str, body: MaintenanceIn, key: str | None) -> AuditOnlyOut:
        machine = await self._online(machine_id)
        method = "POST" if body.on else "DELETE"
        result = await self._operate(
            machine_id, key, "machine.maintenance", method, f"/machines/{machine_id}/maintenance",
            {"on": body.on} if body.on else None, machine=machine,
        )
        if body.on:
            await self._abort(machine)
        return result

    async def reset(self, machine_id: str, key: str | None) -> AuditOnlyOut:
        return await self._operate(machine_id, key, "machine.reset", "POST", f"/machines/{machine_id}/reset", None)

    async def plan_history(self, machine_id: str) -> PlanHistoryOut:
        machine = await self._machine(machine_id)
        rows = list(await self.session.scalars(
            select(PlanDispatchOrm).where(PlanDispatchOrm.machine_id == machine_id).order_by(PlanDispatchOrm.created_at)
        ))
        names = await self._plan_names({(row.plan_id, row.plan_version) for row in rows})
        current = (machine.plan_id, machine.plan_version) if machine.plan_id and machine.plan_version else None
        spans = plan_spans([
            {
                "plan_id": row.plan_id,
                "version": row.plan_version,
                "created_at": row.created_at,
                "accepted": row.accepted,
                "name": names.get((row.plan_id, row.plan_version), row.plan_id),
            }
            for row in rows
        ], current, now_ms())
        if current:
            names.update(await self._plan_names({current}))
        items = []
        for span in spans:
            span["name"] = names.get((span["plan_id"], span["version"]), span["name"])
            items.append({**span, "runs": await self._run_count(machine_id, span), "from": span["from"]})
        return PlanHistoryOut.model_validate({"items": items})

    async def channel_bias(self, machine_id: str) -> ChannelBiasOut:
        await self._machine(machine_id)
        rows = [row for row in await self.machines.channel_biases() if row.machine_id == machine_id]
        measured = max((row.measured_at for row in rows), default=0)
        return ChannelBiasOut(
            measured_at=measured,
            samples=0,
            threshold_c=live.drift_c if live.ready else settings.drift_c,
            items=[{"channel": row.channel, "value": row.value} for row in rows],
        )

    async def compensation(self, machine_id: str) -> CompensationOut:
        await self._online(machine_id)
        payload = await self._cluster("GET", f"/machines/{machine_id}/compensation", missing_ok=True)
        return CompensationOut(compensation=compensation_channels(payload))

    async def write_compensation(self, machine_id: str, body: CompensationIn, key: str | None) -> AuditOnlyOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return AuditOnlyOut.model_validate(cached)
        await self._online(machine_id)
        if body.mode not in {"add", "set"}:
            raise ApiError(422, "VALIDATION_ERROR", "mode 只能是 add 或 set")
        items = [item.model_dump() for item in body.compensation]
        if body.mode == "add" and not items:
            raise ApiError(422, "VALIDATION_ERROR", "叠加补偿至少要有一个通道")
        before = compensation_channels(await self._cluster("GET", f"/machines/{machine_id}/compensation", missing_ok=True))
        payload = await self._cluster("PUT", f"/machines/{machine_id}/compensation", cluster_compensation(body.mode, items))
        after = compensation_channels(payload) or items
        audit_id = await self.audit.write(self.user.user_id, "machine.compensation", {
            "machine_id": machine_id, "mode": body.mode, "compensation": items,
        })
        self.session.add(CompensationWriteOrm(
            machine_id=machine_id, actor=self.user.name or self.user.username, mode=body.mode,
            before=before, after=after, audit_id=audit_id, created_at=now_ms(),
        ))
        result = AuditOnlyOut(audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        return result

    async def suggestion(self, machine_id: str) -> SuggestionOut:
        bias = await self.channel_bias(machine_id)
        payload = compensation_suggestion([item.model_dump() for item in bias.items], bias.measured_at)
        return SuggestionOut.model_validate(payload)

    async def drifts(self, machine_id: str) -> DriftsOut:
        await self._machine(machine_id)
        if live.ready and live.source != "sim":
            return DriftsOut(items=[], supported=False)
        payload = await self._cluster("GET", f"/machines/{machine_id}/drifts", missing_ok=True)
        if not isinstance(payload, (dict, list)) or payload == {}:
            return DriftsOut(items=[], supported=False)
        return DriftsOut(items=drift_rows(payload), supported=True)

    async def compensation_history(self, machine_id: str) -> CompensationHistoryOut:
        await self._machine(machine_id)
        rows = list(await self.session.scalars(
            select(CompensationWriteOrm)
            .where(CompensationWriteOrm.machine_id == machine_id)
            .order_by(CompensationWriteOrm.created_at.desc())
        ))
        return CompensationHistoryOut(items=[
            {
                "at": row.created_at, "actor": row.actor, "mode": row.mode,
                "before": row.before or [], "after": row.after or [], "audit_id": row.audit_id,
            }
            for row in rows
        ])

    async def _operate(
        self, machine_id: str, key: str | None, action: str, method: str, path: str,
        body: dict | None, machine=None,
    ) -> AuditOnlyOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return AuditOnlyOut.model_validate(cached)
        if machine is None:
            await self._online(machine_id)
        await self._cluster(method, path, body)
        await self._refresh(machine_id)
        audit_id = await self.audit.write(self.user.user_id, action, {"machine_id": machine_id, **(body or {})})
        result = AuditOnlyOut(audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        return result

    async def _refresh(self, machine_id: str) -> None:
        try:
            payload = await self.cluster.get(f"/machines/{machine_id}")
        except httpx.HTTPError:
            return
        entity = machine_from_cluster(payload if isinstance(payload, dict) else {}, now_ms())
        if entity is None:
            return
        await self.machines.save_machine(entity)
        if entity.slots:
            await self.machines.replace_slots(machine_id, entity.slots)
        view = await MachineService(self.machines, self.stats).get_machine(machine_id)
        await hub.publish("fleet", [_summary(view)])
        await hub.publish("slots", {"machine_id": machine_id, "slots": [slot.model_dump() for slot in view.slots]})

    async def _abort(self, machine) -> None:
        running = list(await self.session.scalars(
            select(RunOrm.run_id).where(RunOrm.machine_id == machine.machine_id, RunOrm.status == "RUNNING")
        ))
        slots = [
            {"phase": slot.phase, "run_id": slot.run_id}
            for slot in machine.slots
        ]
        ids = sampling_run_ids(slots, list(running))
        if not ids:
            return
        await self.session.execute(
            update(RunOrm)
            .where(RunOrm.run_id.in_(ids))
            .values(status="ABORTED", passed=None, ended_at=now_ms())
        )

    async def _run_count(self, machine_id: str, span: dict) -> int:
        stmt = select(func.count()).select_from(RunOrm).where(
            RunOrm.machine_id == machine_id,
            RunOrm.plan_id == span["plan_id"],
            RunOrm.plan_version == span["version"],
        )
        if span["to"] is not None:
            stmt = stmt.where(RunOrm.ended_at >= span["from"], RunOrm.ended_at < span["to"])
        return int(await self.session.scalar(stmt) or 0)

    async def _plan_names(self, keys: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
        names = {}
        for plan_id, version in keys:
            revision = await self.session.get(PlanRevisionOrm, (plan_id, version))
            if revision is not None and revision.name:
                names[(plan_id, version)] = revision.name
        return names

    async def _online(self, machine_id: str):
        machine = await self._machine(machine_id)
        if ensure_online(machine.comm_status):
            raise ApiError(503, "MACHINE_DISCONNECTED", "机台通信断开，指令没有转发")
        return machine

    async def _machine(self, machine_id: str):
        machine = await self.machines.get(machine_id)
        if machine is None:
            raise ApiError(404, "NOT_FOUND", f"机台 {machine_id} 不存在")
        return machine

    async def _cluster(self, method: str, path: str, body: dict | None = None, missing_ok: bool = False):
        try:
            if method == "GET":
                return await self.cluster.get(path)
            if method == "PUT":
                return await self.cluster.put(path, body or {})
            if method == "DELETE":
                return await self.cluster.delete(path)
            return await self.cluster.post(path, body)
        except httpx.TimeoutException as exc:
            raise ApiError(504, "CLUSTER_TIMEOUT", "集群响应超时") from exc
        except httpx.HTTPStatusError as exc:
            if missing_ok and exc.response.status_code == 404:
                return {}
            if exc.response.status_code == 503:
                raise ApiError(503, "MACHINE_DISCONNECTED", "机台通信断开") from exc
            raise ApiError(502, "CLUSTER_ERROR", "集群拒绝了这次操作", {"status": exc.response.status_code}) from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "集群没有响应") from exc

    def _require_key(self, key: str | None) -> None:
        if not key:
            raise ApiError(400, "BAD_REQUEST", "缺少 Idempotency-Key")


def _summary(machine: MachineOut) -> dict:
    data = machine.model_dump()
    data.pop("capability", None)
    data.pop("slots", None)
    return data

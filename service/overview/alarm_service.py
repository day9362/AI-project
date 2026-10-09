import uuid
from dataclasses import asdict

from core.clock import now_ms
from core.config import settings
from core.errors import ApiError
from models.dto.overview import AlarmOut, AlarmPageOut, AttributionOut, AuditOut
from models.entity.overview import AlarmEntity, AttributionEntity
from models.entity.user import UserEntity
from repo.alarm_repo import AlarmRepo, decode_cursor
from repo.job_repo import JobRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.overview.rules import attribute, is_sentinel

IDEMPOTENCY_MS = 10 * 60 * 1000


class AlarmService:
    def __init__(self, alarms: AlarmRepo, machines: MachineRepo, stats: StatsRepo, jobs: JobRepo):
        self.alarms = alarms
        self.machines = machines
        self.stats = stats
        self.jobs = jobs

    async def page(self, acked: bool | None, machine_id: str | None, level: str | None, cursor: str | None, limit: int) -> AlarmPageOut:
        if limit < 1 or limit > 500:
            raise ApiError(400, "BAD_REQUEST", "limit 范围是 1 到 500")
        if cursor:
            try:
                decode_cursor(cursor)
            except Exception as exc:
                raise ApiError(400, "BAD_REQUEST", "cursor 无法解析") from exc
        items, next_cursor = await self.alarms.page(
            acked=acked, machine_id=machine_id, level=level, cursor=cursor, limit=limit,
        )
        return AlarmPageOut(items=[AlarmOut.model_validate(asdict(item)) for item in items], next_cursor=next_cursor)

    async def ack(self, alarm_id: str, user: UserEntity, idem_key: str | None, undo: bool) -> AuditOut:
        cached = await self._cached(user, idem_key)
        if cached is not None:
            return AuditOut.model_validate(cached)
        row = await self.alarms.get(alarm_id)
        if row is None:
            raise ApiError(404, "NOT_FOUND", f"告警 {alarm_id} 不存在")
        if undo:
            row.acked = False
            row.acked_by = None
            row.acked_at = None
        else:
            row.acked = True
            row.acked_by = user.name
            row.acked_at = now_ms()
        await self.alarms.save_ack(row)
        body = AuditOut(audit_id=_audit_id(), alarm=AlarmOut.model_validate(asdict(row)))
        await self._store(user, idem_key, body)
        await self.alarms.session.commit()
        return body

    async def ack_all(self, user: UserEntity, idem_key: str | None) -> AuditOut:
        cached = await self._cached(user, idem_key)
        if cached is not None:
            return AuditOut.model_validate(cached)
        open_rows = await self.alarms.open_alarms()
        ts = now_ms()
        for row in open_rows:
            row.acked = True
            row.acked_by = user.name
            row.acked_at = ts
            await self.alarms.save_ack(row)
        body = AuditOut(audit_id=_audit_id(), acked=len(open_rows))
        await self._store(user, idem_key, body)
        await self.alarms.session.commit()
        return body

    async def attribution(self, alarm_id: str) -> AttributionOut:
        alarm = await self.alarms.get(alarm_id)
        if alarm is None:
            raise ApiError(404, "NOT_FOUND", f"告警 {alarm_id} 不存在")
        row = await self.alarms.attribution(alarm_id)
        if row is None:
            return AttributionOut(alarm_id=alarm_id, status="pending")
        return AttributionOut.model_validate(asdict(row))

    async def run_attribution(self, alarm_id: str) -> AttributionEntity:
        alarm = await self.alarms.get(alarm_id)
        if alarm is None:
            raise ApiError(404, "NOT_FOUND", f"告警 {alarm_id} 不存在")
        result = attribute(alarm, now_ms())
        await self.alarms.save_attribution(result)
        return result

    async def scan(self) -> list[AlarmEntity]:
        machines = await self.machines.list_all()
        plans = {plan.plan_id: plan for plan in await self.stats.plans()}
        open_keys = {(a.machine_id, a.slot_index, a.code) for a in await self.alarms.open_alarms()}
        seq = await self.alarms.next_seq()
        created: list[AlarmEntity] = []

        def push(alarm: AlarmEntity) -> None:
            nonlocal seq
            key = (alarm.machine_id, alarm.slot_index, alarm.code)
            if key in open_keys:
                return
            open_keys.add(key)
            created.append(alarm)
            seq += 1

        for machine in machines:
            if machine.status == "FAULT":
                push(AlarmEntity(
                    id=f"AL-{seq}", time=now_ms(), level="critical", machine_id=machine.machine_id,
                    source="机台", code="PLC_FAULT", message=machine.alarm or "机台进入 FAULT", acked=False,
                ))
            if machine.comm_status == "DISCONNECTED":
                push(AlarmEntity(
                    id=f"AL-{seq}", time=now_ms(), level="critical", machine_id=machine.machine_id,
                    source="通信", code="COMM_DISCONNECT", message="通信断开（DISCONNECTED），状态查询与指令下发均返回 503", acked=False,
                ))
            elif machine.comm_status == "DEGRADED" and settings.degraded_alarm:
                push(AlarmEntity(
                    id=f"AL-{seq}", time=now_ms(), level="minor", machine_id=machine.machine_id,
                    source="通信", code="PACKET_LOSS", message=f"通信降级（DEGRADED · {machine.comm_note or '丢包'}）", acked=False,
                ))
            plan = plans.get(machine.plan_id or "")
            if plan and (machine.room_temp_c < plan.ambient_low_c or machine.room_temp_c > plan.ambient_high_c):
                push(AlarmEntity(
                    id=f"AL-{seq}", time=now_ms(), level="minor", machine_id=machine.machine_id,
                    source="机台", code="AMBIENT_EXCURSION",
                    message=f"房间温度 {machine.room_temp_c:.1f} ℃ 超出方案范围 {plan.ambient_low_c:g}–{plan.ambient_high_c:g} ℃",
                    acked=False,
                ))
            for slot in machine.slots:
                if slot.phase == "ERROR":
                    push(AlarmEntity(
                        id=f"AL-{seq}", time=now_ms(), level="major", machine_id=machine.machine_id, slot_index=slot.index,
                        source="槽位", code=_slot_code(slot.last_error), message=slot.last_error or "槽位进入 ERROR", acked=False,
                    ))
                if settings.sentinel_as_data_anomaly:
                    for name, value in (("T0", slot.t0), ("T1", slot.t1), ("Ta", slot.ta)):
                        if is_sentinel(value):
                            push(AlarmEntity(
                                id=f"AL-{seq}", time=now_ms(), level="minor", machine_id=machine.machine_id, slot_index=slot.index,
                                source="数据", code="SENSOR_99999", message=f"{name} 读数 {value:g}（哨兵值）", acked=False,
                            ))
                            break
        for bias in await self.machines.channel_biases():
            if abs(bias.value) <= settings.drift_c:
                continue
            push(AlarmEntity(
                id=f"AL-{seq}", time=now_ms(), level="major", machine_id=bias.machine_id,
                source="漂移", code="EQUIPMENT_ANOMALY",
                message=f"{bias.channel} 通道估计漂移 {bias.value:+.2f} ℃，超过 {settings.drift_c:g} ℃ 设备异常阈值",
                acked=False,
            ))
        for machine_id, item in await self._consecutive_failures():
            push(AlarmEntity(
                id=f"AL-{seq}", time=now_ms(), level="major", machine_id=machine_id,
                source="判定", code=item, message=f"连续 3 片 {item} 不合格", acked=False,
            ))
        for alarm in created:
            await self.alarms.add(alarm)
        return created

    async def _consecutive_failures(self) -> list[tuple[str, str]]:
        runs = await self.stats.recent_runs(400)
        grouped: dict[str, list] = {}
        for run in runs:
            if run.status != "COMPLETED":
                continue
            bucket = grouped.setdefault(run.machine_id, [])
            if len(bucket) < 3:
                bucket.append(run)
        found: list[tuple[str, str]] = []
        for machine_id, rows in grouped.items():
            if len(rows) < 3 or any(row.passed for row in rows):
                continue
            item = rows[0].fail_items[0] if rows[0].fail_items else "Temp_T0-T1"
            found.append((machine_id, item))
        return found

    async def _cached(self, user: UserEntity, key: str | None) -> dict | None:
        if not key:
            raise ApiError(400, "BAD_REQUEST", "缺少 Idempotency-Key")
        return await self.jobs.get_idempotent(user.user_id, key, now_ms() - IDEMPOTENCY_MS)

    async def _store(self, user: UserEntity, key: str | None, body: AuditOut) -> None:
        if key:
            await self.jobs.save_idempotent(user.user_id, key, body.model_dump(), now_ms())


def _audit_id() -> str:
    return "aud_" + uuid.uuid4().hex[:12]


def _slot_code(last_error: str) -> str:
    head = (last_error or "SLOT_ERROR").split("·", 1)[0].strip()
    return head or "SLOT_ERROR"

from core.clock import now_ms
from core.config import settings
from core.errors import ApiError
from models.dto.overview import Agg5mOut, AnomalyTrendOut, KpiOut, KpiPrevOut, PipelineOut, PipelineStepOut, RcBiasItemOut, RcBiasOut
from models.entity.overview import AggEntity, MachineEntity
from repo.alarm_repo import AlarmRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from service.overview.aggregate import aggregate_runs, yield_rate
from service.overview.rules import alarm_category

HOUR = 3_600_000
SHIFT = 8 * HOUR


class StatsService:
    def __init__(self, stats: StatsRepo, machines: MachineRepo, alarms: AlarmRepo):
        self.stats = stats
        self.machines = machines
        self.alarms = alarms

    async def rebuild_recent(self, hours: int = 16) -> list[AggEntity]:
        end = now_ms()
        start = end - hours * HOUR
        runs = await self.stats.runs_between(start, end + 1)
        rows = aggregate_runs(runs, start, end)
        await self.stats.replace_agg(rows)
        return rows

    async def kpi(self, range_name: str) -> KpiOut:
        if range_name not in {"shift", "2h"}:
            raise ApiError(400, "BAD_REQUEST", "range 只能是 shift 或 2h")
        window = SHIFT if range_name == "shift" else 2 * HOUR
        end = now_ms()
        current = await self.stats.agg_between(end - window, end + 1)
        previous = await self.stats.agg_between(end - 2 * window, end - window)
        machines = await self.machines.list_all()
        alarms = await self.alarms.open_alarms()
        runs = await self.stats.recent_runs(120)
        rcs = [run.rc for run in runs if run.rc is not None]
        tests = sum(row.tests for row in current)
        passed = sum(row.passed for row in current)
        prev_tests = sum(row.tests for row in previous)
        prev_passed = sum(row.passed for row in previous)
        return KpiOut(
            online=_online(machines),
            total=len(machines),
            busy_slots=_busy(machines),
            error_slots=_errors(machines),
            slot_total=sum(m.slot_count for m in machines),
            tests=tests,
            yield_rate=yield_rate(passed, tests),
            rc_mean=round(sum(rcs) / len(rcs), 3) if rcs else 0,
            open_alarms=len(alarms),
            critical_alarms=sum(1 for a in alarms if a.level == "critical"),
            prev=KpiPrevOut(tests=prev_tests, yield_rate=yield_rate(prev_passed, prev_tests)),
        )

    async def agg(self, start_ms: int | None, end_ms: int | None) -> list[Agg5mOut]:
        end = end_ms or now_ms()
        start = start_ms if start_ms is not None else end - SHIFT
        if start > end:
            raise ApiError(400, "BAD_REQUEST", "from 不能大于 to")
        rows = await self.stats.agg_between(start, end + 1)
        return [Agg5mOut.model_validate(row.__dict__) for row in rows]

    async def anomaly_trend(self, hours: int) -> AnomalyTrendOut:
        if hours < 1 or hours > 48:
            raise ApiError(400, "BAD_REQUEST", "hours 范围是 1 到 48")
        end_hour = now_ms() // HOUR * HOUR
        start = end_hour - (hours - 1) * HOUR
        alarms = await self.alarms.between(start, end_hour + HOUR)
        attributions = await self.alarms.attributions_for([a.id for a in alarms])
        labels = [start + i * HOUR for i in range(hours)]
        series = {key: [0] * hours for key in ("equipment", "product", "communication", "data")}
        for alarm in alarms:
            index = (alarm.time - start) // HOUR
            if index < 0 or index >= hours:
                continue
            attr = attributions.get(alarm.id)
            category = attr.category if attr and attr.status == "done" and attr.category in series else alarm_category(alarm.source, alarm.code)
            if category == "environment":
                category = "equipment"
            if category in series:
                series[category][index] += 1
        return AnomalyTrendOut(hours=labels, series=series)

    async def rc_bias(self) -> RcBiasOut:
        runs = await self.stats.recent_runs(4000)
        grouped: dict[str, list[float]] = {}
        for run in runs:
            if run.rc is None:
                continue
            bucket = grouped.setdefault(run.machine_id, [])
            if len(bucket) < 120:
                bucket.append(run.rc)
        means = {mid: sum(vals) / len(vals) for mid, vals in grouped.items() if vals}
        if not means:
            return RcBiasOut(median=0, items=[])
        ordered = sorted(means.values())
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        items = [RcBiasItemOut(machine_id=mid, bias=round(value - median, 3)) for mid, value in sorted(means.items())]
        return RcBiasOut(median=round(median, 3), items=items)

    async def pipeline(self) -> PipelineOut:
        machines = await self.machines.list_all()
        plans = await self.stats.plans()
        batches = await self.stats.batches()
        alarms = await self.alarms.open_alarms()
        biases = await self.machines.channel_biases()
        drafts = sum(1 for plan in plans if plan.draft)
        running = next((b for b in batches if b.state == "running"), None)
        online = _online(machines)
        total = len(machines)
        critical = sum(1 for a in alarms if a.level == "critical")
        hot = next((b for b in biases if abs(b.value) > settings.drift_c), None)
        reportable = sum(1 for b in batches if b.state != "running" and b.tested > 0)
        return PipelineOut(
            gen=PipelineStepOut(text=f"{drafts} 草稿", state="ok"),
            check=PipelineStepOut(text="能力范围校验", state="ok"),
            dispatch=PipelineStepOut(
                text=f"剩余 {running.count - running.tested} 片" if running else "无连续生产",
                state="ok" if running else "idle",
            ),
            collect=PipelineStepOut(
                text=f"{online}/{total} 台在线",
                state="warn" if online < total else "ok",
            ),
            anomaly=PipelineStepOut(
                text=f"{len(alarms)} 条未确认",
                state="danger" if critical else ("warn" if alarms else "ok"),
            ),
            calib=PipelineStepOut(
                text=f"{hot.machine_id} {hot.channel} 漂移待补偿" if hot else "通道偏差在阈值内",
                state="warn" if hot else "ok",
            ),
            report=PipelineStepOut(text=f"{reportable} 个批次可出报告", state="ok"),
        )


def _online(machines: list[MachineEntity]) -> int:
    return sum(1 for m in machines if m.comm_status != "DISCONNECTED" and m.status not in {"OFFLINE", "STOPPED"})


def _busy(machines: list[MachineEntity]) -> int:
    count = 0
    for machine in machines:
        if machine.comm_status == "DISCONNECTED":
            continue
        count += sum(1 for slot in machine.slots if slot.phase not in {"IDLE", "ERROR", "COMPLETED"})
    return count


def _errors(machines: list[MachineEntity]) -> int:
    count = 0
    for machine in machines:
        if machine.comm_status == "DISCONNECTED":
            continue
        count += sum(1 for slot in machine.slots if slot.phase == "ERROR")
    return count

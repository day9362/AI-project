from typing import Literal

from pydantic import BaseModel, Field


class YieldRecentOut(BaseModel):
    n: int
    passed: int


class SlotOut(BaseModel):
    index: int
    phase: str
    serial_number: str | None
    tests_done: int
    last_error: str
    power_w: float
    vacuum_kpa: float
    t0: float
    t1: float
    ta: float
    progress: float
    run_id: str | None


class MachineOut(BaseModel):
    machine_id: str
    serial: str
    fixture: str
    holder: str
    thermal_boards: str
    plc: str
    firmware: str
    slot_count: int
    status: str
    comm_status: str
    comm_note: str
    speed: float
    room_temp_c: float
    alarm: str
    plan_id: str | None
    plan_version: int | None
    capability: dict
    slots: list[SlotOut]
    last_sync_at: int
    yield_recent: YieldRecentOut


class MachineSummaryOut(BaseModel):
    machine_id: str
    serial: str
    fixture: str
    holder: str
    thermal_boards: str
    plc: str
    firmware: str
    slot_count: int
    status: str
    comm_status: str
    comm_note: str
    speed: float
    room_temp_c: float
    alarm: str
    plan_id: str | None
    plan_version: int | None
    last_sync_at: int
    yield_recent: YieldRecentOut


class CurvePointOut(BaseModel):
    t_s: float
    T0: float
    T1: float
    Ta: float
    power_w: float


class CurveOut(BaseModel):
    run_id: str | None
    plan_id: str | None
    plan_version: int | None
    duration_s: int
    points: list[CurvePointOut]
    deltas: dict[str, float]


class KpiPrevOut(BaseModel):
    tests: int
    yield_rate: float


class KpiOut(BaseModel):
    online: int
    total: int
    busy_slots: int
    error_slots: int
    slot_total: int
    tests: int
    yield_rate: float
    rc_mean: float
    open_alarms: int
    critical_alarms: int
    prev: KpiPrevOut


class Agg5mOut(BaseModel):
    bucket: int
    tests: int
    passed: int
    failed: int
    aborted: int
    rc_mean: float
    dt01_mean: float


class AnomalyTrendOut(BaseModel):
    hours: list[int]
    series: dict[str, list[int]]


class RcBiasItemOut(BaseModel):
    machine_id: str
    bias: float


class RcBiasOut(BaseModel):
    median: float
    items: list[RcBiasItemOut]


class PipelineStepOut(BaseModel):
    text: str
    state: Literal["ok", "warn", "danger", "idle"]


class PipelineOut(BaseModel):
    gen: PipelineStepOut
    check: PipelineStepOut
    dispatch: PipelineStepOut
    collect: PipelineStepOut
    anomaly: PipelineStepOut
    calib: PipelineStepOut
    report: PipelineStepOut


class AlarmOut(BaseModel):
    id: str
    time: int
    level: str
    machine_id: str
    slot_index: int | None = None
    source: str
    code: str
    message: str
    acked: bool
    acked_by: str | None = None
    acked_at: int | None = None


class AlarmPageOut(BaseModel):
    items: list[AlarmOut]
    next_cursor: str | None


class AuditOut(BaseModel):
    audit_id: str
    alarm: AlarmOut | None = None
    acked: int | None = None


class AttributionOut(BaseModel):
    alarm_id: str
    status: Literal["pending", "done", "failed"]
    category: str = ""
    confidence: float = 0
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    suggestion: str = ""
    model: str = ""
    created_at: int = 0

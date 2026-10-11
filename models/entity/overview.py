from dataclasses import dataclass, field


@dataclass
class SlotEntity:
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


@dataclass
class YieldRecent:
    n: int
    passed: int


@dataclass
class MachineEntity:
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
    slots: list[SlotEntity] = field(default_factory=list)
    last_sync_at: int = 0
    yield_recent: YieldRecent = field(default_factory=lambda: YieldRecent(0, 0))


@dataclass
class RunEntity:
    run_id: str
    machine_id: str
    slot_index: int
    serial_number: str
    plan_id: str
    plan_version: int
    status: str
    passed: bool | None
    fail_items: list[str]
    keep_result: bool
    rc: float | None
    dt01: float | None
    batch_id: str
    ended_at: int


@dataclass
class AggEntity:
    bucket: int
    tests: int
    passed: int
    failed: int
    aborted: int
    rc_mean: float
    dt01_mean: float


@dataclass
class AlarmEntity:
    id: str
    time: int
    level: str
    machine_id: str
    source: str
    code: str
    message: str
    acked: bool
    slot_index: int | None = None
    acked_by: str | None = None
    acked_at: int | None = None


@dataclass
class AttributionEntity:
    alarm_id: str
    status: str
    category: str
    confidence: float
    summary: str
    evidence: list[str]
    suggestion: str
    model: str
    created_at: int


@dataclass
class CurvePoint:
    t_s: float
    T0: float
    T1: float
    Ta: float
    power_w: float


@dataclass
class CurveEntity:
    run_id: str | None
    plan_id: str | None
    plan_version: int | None
    duration_s: int
    points: list[CurvePoint]
    deltas: dict[str, float]


@dataclass
class PlanEntity:
    plan_id: str
    version: int
    name: str
    duration_s: int
    power_w: float
    start_temp_c: float
    ambient_low_c: float
    ambient_high_c: float
    draft: bool


@dataclass
class BatchBrief:
    batch_id: str
    count: int
    tested: int
    state: str
    plan_id: str
    plan_version: int

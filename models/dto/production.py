from typing import Literal

from pydantic import BaseModel, Field


class ProductModelOut(BaseModel):
    model: str
    resistance_mean: float
    resistance_sd: float
    power_w: float


class BatchOut(BaseModel):
    batch_id: str
    model: str
    count: int
    defect_ratio: float
    batch_factor: float
    remaining: int


class BatchStatOut(BaseModel):
    batch_id: str
    model: str
    count: int
    tested: int
    passed: int
    failed: int
    aborted: int
    plan_id: str
    plan_version: int
    machine_ids: list[str]
    started_at: int
    ended_at: int | None
    state: Literal["running", "done", "stopped"]
    rc_mean: float
    rc_sd: float
    top_fail: str
    eta_s: int | None


class BatchStatPageOut(BaseModel):
    items: list[BatchStatOut]
    next_cursor: str | None = None


class ProductionOut(BaseModel):
    batch_id: str
    queue_remaining: int
    plan_id: str
    plan_version: int


class ProductionIn(BaseModel):
    machine_ids: list[str] = Field(default_factory=list)
    plan_id: str
    plan_version: int
    batch_id: str | None = None
    serial_numbers: list[str] | None = None
    auto_recover: bool = True
    max_count: int | None = None


class StopIn(BaseModel):
    batch_id: str


class IssueOut(BaseModel):
    level: Literal["ok", "warn", "danger"]
    field: str | None = None
    message: str


class PrecheckOut(BaseModel):
    ok: bool
    issues: list[IssueOut]


class SkippedOut(BaseModel):
    machine_id: str
    reason: str


class StartOut(BaseModel):
    batch_id: str
    accepted: list[str]
    skipped: list[SkippedOut]
    audit_id: str


class StopOut(BaseModel):
    audit_id: str


class RunOut(BaseModel):
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


class RunDetailOut(RunOut):
    result: dict = Field(default_factory=dict)


class RunPageOut(BaseModel):
    items: list[RunOut]
    next_cursor: str | None = None


class SampleOut(BaseModel):
    seq: int
    t_s: float
    t0: float
    t1: float
    ta: float
    power_w: float

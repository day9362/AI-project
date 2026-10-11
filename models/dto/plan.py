from typing import Literal

from pydantic import BaseModel, Field


class LimitIn(BaseModel):
    item: str
    low: float | None = None
    high: float | None = None
    unit: str = ""
    skipped: bool = False


class PlanBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    start_temp_c: float
    duration_s: int
    sample_period_s: float
    power_w: float
    force_g: float
    orientation: int
    overtemp_c: float
    ambient_low_c: float
    ambient_high_c: float
    limits: list[LimitIn] = Field(default_factory=list)


class PublishIn(PlanBody):
    plan_id: str | None = None


class PlanOut(PlanBody):
    plan_id: str
    version: int


class PlanMetaOut(BaseModel):
    plan_id: str
    versions: list[int]
    updated_at: int
    author: str
    source: Literal["agent", "manual"]
    draft: bool


class PlanItemOut(BaseModel):
    plan: PlanOut
    meta: PlanMetaOut


class IssueOut(BaseModel):
    level: Literal["ok", "warn", "danger"]
    field: str | None = None
    message: str


class ValidateOut(BaseModel):
    ok: bool
    issues: list[IssueOut]


class PublishOut(BaseModel):
    plan_id: str
    version: int
    audit_id: str


class DraftOut(PlanItemOut):
    audit_id: str

from pydantic import BaseModel, Field, model_serializer

from models.dto.production import BatchStatOut


class ReportBatchOut(BatchStatOut):
    plan_name: str = ""
    yield_rate: float = 0


class ReportSummaryOut(BaseModel):
    tested: int = 0
    passed: int = 0
    failed: int = 0
    aborted: int = 0
    yield_rate: float = 0
    rc_mean: float = 0
    rc_sd: float = 0
    cpk_t01: float | None = None
    usl_t01: float | None = None
    machine_count: int = 0


class MachineYieldOut(BaseModel):
    machine_id: str
    n: int
    passed: int


class HistogramOut(BaseModel):
    edges: list[float] = Field(default_factory=list)
    counts: dict[str, list[int]] = Field(default_factory=dict)


class ParetoOut(BaseModel):
    item: str
    count: int


class DeltaProfileOut(BaseModel):
    items: list[str] = Field(default_factory=list)
    mean: dict[str, list[float | None]] = Field(default_factory=dict)
    p95: list[float | None] | None = None
    limit: list[float | None] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _drop_empty_p95(self, handler):
        data = handler(self)
        if data.get("p95") is None:
            data.pop("p95", None)
        return data


class CompareOut(BaseModel):
    batch_id: str
    yield_rate: float
    rc_mean: float


class ReportOut(BaseModel):
    batches: list[ReportBatchOut]
    summary: ReportSummaryOut
    machine_yield: list[MachineYieldOut]
    rc_histogram: HistogramOut
    fail_pareto: list[ParetoOut]
    delta_profile: DeltaProfileOut
    compare: list[CompareOut]

from pydantic import BaseModel, Field


class AuditOnlyOut(BaseModel):
    audit_id: str


class PlanHistoryItem(BaseModel):
    plan_id: str
    name: str
    version: int
    from_: int = Field(alias="from")
    to: int | None = None
    runs: int = 0

    model_config = {"populate_by_name": True}


class PlanHistoryOut(BaseModel):
    items: list[PlanHistoryItem]


class ChannelBiasItem(BaseModel):
    channel: str
    value: float


class ChannelBiasOut(BaseModel):
    measured_at: int = 0
    golden_model: str = "HVP1307G17-1"
    samples: int = 0
    threshold_c: float
    items: list[ChannelBiasItem]


class CompensationItem(BaseModel):
    channel: str
    value: float


class CompensationIn(BaseModel):
    mode: str
    compensation: list[CompensationItem]


class CompensationOut(BaseModel):
    compensation: list[CompensationItem]


class CompensationWriteOut(BaseModel):
    at: int
    actor: str
    mode: str
    before: list[CompensationItem]
    after: list[CompensationItem]
    audit_id: str


class CompensationHistoryOut(BaseModel):
    items: list[CompensationWriteOut]


class SuggestionItem(BaseModel):
    channel: str
    value: float
    reason: str


class SuggestionOut(BaseModel):
    items: list[SuggestionItem]
    basis_at: int = 0


class DriftItem(BaseModel):
    drift_id: str = ""
    channel: str = ""
    kind: str = ""
    value: float = 0
    current: float = 0


class DriftsOut(BaseModel):
    items: list[DriftItem]
    supported: bool


class MaintenanceIn(BaseModel):
    on: bool

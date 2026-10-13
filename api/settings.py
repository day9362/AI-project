from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from api.deps import settings_service
from service.settings_service import SettingsService

router = APIRouter(tags=["settings"])


class ConnectionIn(BaseModel):
    source: str
    base_url: str
    token: str = ""


class ClockIn(BaseModel):
    speed: float


class ScenarioIn(BaseModel):
    machine_id: str = ""


class FaultIn(BaseModel):
    machine_id: str
    kind: str
    slot_index: int | None = None


@router.get("/settings")
async def get_settings(service: Annotated[SettingsService, Depends(settings_service)]) -> dict:
    return await service.get()


@router.put("/settings")
async def save_settings(
    body: dict,
    service: Annotated[SettingsService, Depends(settings_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    return await service.save(body, idempotency_key)


@router.post("/settings/test-connection")
async def test_connection(
    body: ConnectionIn,
    service: Annotated[SettingsService, Depends(settings_service)],
) -> dict:
    return await service.test_connection(body.source, body.base_url, body.token)


@router.get("/sync/jobs/status")
async def job_status(service: Annotated[SettingsService, Depends(settings_service)]) -> dict:
    return await service.job_status()


@router.put("/sim/clock")
async def sim_clock(
    body: ClockIn,
    service: Annotated[SettingsService, Depends(settings_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    return await service.clock(body.speed, idempotency_key)


@router.get("/sim/scenarios")
async def sim_scenarios(service: Annotated[SettingsService, Depends(settings_service)]) -> dict:
    return await service.scenarios()


@router.post("/sim/scenarios/{name}/apply")
async def apply_scenario(
    name: str,
    body: ScenarioIn,
    service: Annotated[SettingsService, Depends(settings_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    return await service.apply_scenario(name, body.machine_id, idempotency_key)


@router.get("/sim/fault-catalog")
async def fault_catalog(service: Annotated[SettingsService, Depends(settings_service)]) -> dict:
    return await service.fault_catalog()


@router.post("/sim/faults")
async def inject_fault(
    body: FaultIn,
    service: Annotated[SettingsService, Depends(settings_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    return await service.inject_fault(body.machine_id, body.kind, body.slot_index, idempotency_key)


@router.get("/runs/{run_id}/ground-truth")
async def ground_truth(
    run_id: str,
    service: Annotated[SettingsService, Depends(settings_service)],
) -> dict:
    return await service.ground_truth(run_id)

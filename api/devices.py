from typing import Annotated

from fastapi import APIRouter, Depends, Header

from api.deps import device_service
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
from service.device_service import DeviceService

router = APIRouter(tags=["devices"])


@router.post("/machines/{machine_id}/power-on", response_model=AuditOnlyOut)
async def power_on(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOnlyOut:
    return await service.power_on(machine_id, idempotency_key)


@router.post("/machines/{machine_id}/power-off", response_model=AuditOnlyOut)
async def power_off(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOnlyOut:
    return await service.power_off(machine_id, idempotency_key)


@router.post("/machines/{machine_id}/maintenance", response_model=AuditOnlyOut)
async def maintenance(
    machine_id: str,
    body: MaintenanceIn,
    service: Annotated[DeviceService, Depends(device_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOnlyOut:
    return await service.maintenance(machine_id, body, idempotency_key)


@router.post("/machines/{machine_id}/reset", response_model=AuditOnlyOut)
async def reset(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOnlyOut:
    return await service.reset(machine_id, idempotency_key)


@router.get("/machines/{machine_id}/plan-history", response_model=PlanHistoryOut)
async def plan_history(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> PlanHistoryOut:
    return await service.plan_history(machine_id)


@router.get("/machines/{machine_id}/channel-bias", response_model=ChannelBiasOut)
async def channel_bias(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> ChannelBiasOut:
    return await service.channel_bias(machine_id)


@router.get("/machines/{machine_id}/compensation", response_model=CompensationOut)
async def compensation(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> CompensationOut:
    return await service.compensation(machine_id)


@router.put("/machines/{machine_id}/compensation", response_model=AuditOnlyOut)
async def write_compensation(
    machine_id: str,
    body: CompensationIn,
    service: Annotated[DeviceService, Depends(device_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOnlyOut:
    return await service.write_compensation(machine_id, body, idempotency_key)


@router.get("/machines/{machine_id}/compensation/suggestion", response_model=SuggestionOut)
async def compensation_suggestion(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> SuggestionOut:
    return await service.suggestion(machine_id)


@router.get("/machines/{machine_id}/drifts", response_model=DriftsOut)
async def machine_drifts(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> DriftsOut:
    return await service.drifts(machine_id)


@router.get("/machines/{machine_id}/compensation/history", response_model=CompensationHistoryOut)
async def compensation_history(
    machine_id: str,
    service: Annotated[DeviceService, Depends(device_service)],
) -> CompensationHistoryOut:
    return await service.compensation_history(machine_id)

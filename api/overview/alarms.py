from typing import Annotated

from fastapi import APIRouter, Depends, Header

from api.deps import alarm_service, current_user
from models.dto.overview import AlarmPageOut, AttributionOut, AuditOut
from models.entity.user import UserEntity
from service.overview.alarm_service import AlarmService
router = APIRouter(prefix="/alarms", tags=["overview"])


@router.get("", response_model=AlarmPageOut)
async def list_alarms(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[AlarmService, Depends(alarm_service)],
    acked: bool | None = None,
    machine_id: str | None = None,
    level: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> AlarmPageOut:
    return await service.page(acked, machine_id, level, cursor, limit)


@router.post("/ack-all", response_model=AuditOut)
async def ack_all(
    user: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[AlarmService, Depends(alarm_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOut:
    return await service.ack_all(user, idempotency_key)


@router.post("/{alarm_id}/ack", response_model=AuditOut)
async def ack(
    alarm_id: str,
    user: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[AlarmService, Depends(alarm_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOut:
    return await service.ack(alarm_id, user, idempotency_key, undo=False)


@router.post("/{alarm_id}/unack", response_model=AuditOut)
async def unack(
    alarm_id: str,
    user: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[AlarmService, Depends(alarm_service)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> AuditOut:
    return await service.ack(alarm_id, user, idempotency_key, undo=True)


@router.get("/{alarm_id}/attribution", response_model=AttributionOut)
async def get_attribution(
    alarm_id: str,
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[AlarmService, Depends(alarm_service)],
) -> AttributionOut:
    return await service.attribution(alarm_id)

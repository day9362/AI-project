from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import current_user, machine_service
from models.dto.overview import CurveOut, MachineOut
from models.entity.user import UserEntity
from service.overview.machine_service import MachineService

router = APIRouter(tags=["overview"])


@router.get("/machines", response_model=list[MachineOut])
async def list_machines(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[MachineService, Depends(machine_service)],
) -> list[MachineOut]:
    return await service.list_machines()


@router.get("/machines/{machine_id}", response_model=MachineOut)
async def get_machine(
    machine_id: str,
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[MachineService, Depends(machine_service)],
) -> MachineOut:
    return await service.get_machine(machine_id)


@router.get("/machines/{machine_id}/slots/{index}/curve", response_model=CurveOut)
async def slot_curve(
    machine_id: str,
    index: int,
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[MachineService, Depends(machine_service)],
    since: Annotated[float | None, Query()] = None,
) -> CurveOut:
    return await service.curve(machine_id, index, since)

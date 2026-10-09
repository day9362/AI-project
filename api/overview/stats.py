from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.deps import current_user, stats_service
from models.dto.overview import Agg5mOut, AnomalyTrendOut, KpiOut, PipelineOut, RcBiasOut
from models.entity.user import UserEntity
from service.overview.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["overview"])


@router.get("/kpi", response_model=KpiOut)
async def kpi(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[StatsService, Depends(stats_service)],
    range: str = "shift",
) -> KpiOut:
    return await service.kpi(range)


@router.get("/agg5m", response_model=list[Agg5mOut])
async def agg5m(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[StatsService, Depends(stats_service)],
    start: Annotated[int | None, Query(alias="from")] = None,
    end: Annotated[int | None, Query(alias="to")] = None,
) -> list[Agg5mOut]:
    return await service.agg(start, end)


@router.get("/anomaly-trend", response_model=AnomalyTrendOut)
async def anomaly_trend(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[StatsService, Depends(stats_service)],
    hours: int = 8,
) -> AnomalyTrendOut:
    return await service.anomaly_trend(hours)


@router.get("/rc-bias", response_model=RcBiasOut)
async def rc_bias(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[StatsService, Depends(stats_service)],
) -> RcBiasOut:
    return await service.rc_bias()


@router.get("/pipeline", response_model=PipelineOut)
async def pipeline(
    _: Annotated[UserEntity, Depends(current_user)],
    service: Annotated[StatsService, Depends(stats_service)],
) -> PipelineOut:
    return await service.pipeline()

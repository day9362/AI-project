from fastapi import APIRouter, Depends, Query

from api.deps import report_service
from models.dto.report import ReportOut
from service.report_service import ReportService

router = APIRouter(tags=["reports"])


@router.get("/reports/data", response_model=ReportOut)
async def report_data(
    batch_ids: str = Query(default=""),
    service: ReportService = Depends(report_service),
) -> ReportOut:
    return await service.data([batch_ids])

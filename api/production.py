from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import Response

from api.deps import production_service
from models.dto.production import (
    BatchOut,
    BatchStatOut,
    BatchStatPageOut,
    PrecheckOut,
    ProductModelOut,
    ProductionIn,
    ProductionOut,
    RunDetailOut,
    RunPageOut,
    SampleOut,
    StartOut,
    StopIn,
    StopOut,
)
from service.production_service import ProductionService

router = APIRouter(tags=["production"])


@router.get("/models", response_model=list[ProductModelOut])
async def list_models(service: ProductionService = Depends(production_service)) -> list[ProductModelOut]:
    return await service.models()


@router.get("/batches", response_model=list[BatchOut])
async def list_batches(service: ProductionService = Depends(production_service)) -> list[BatchOut]:
    return await service.batches()


@router.get("/batch-stats", response_model=BatchStatPageOut)
async def list_batch_stats(
    state: str | None = None,
    model: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    service: ProductionService = Depends(production_service),
) -> BatchStatPageOut:
    return await service.batch_stats(state, model, q, cursor, limit)


@router.get("/batch-stats/{batch_id}", response_model=BatchStatOut)
async def get_batch_stat(batch_id: str, service: ProductionService = Depends(production_service)) -> BatchStatOut:
    return await service.batch_stat(batch_id)


@router.get("/production", response_model=ProductionOut | None)
async def get_production(service: ProductionService = Depends(production_service)) -> ProductionOut | None:
    return await service.production()


@router.post("/production/precheck", response_model=PrecheckOut)
async def precheck(body: ProductionIn, service: ProductionService = Depends(production_service)) -> PrecheckOut:
    return await service.precheck_body(body)


@router.post("/production/start", response_model=StartOut)
async def start_production(
    body: ProductionIn,
    service: ProductionService = Depends(production_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StartOut:
    return await service.start(body, idempotency_key)


@router.post("/production/stop", response_model=StopOut)
async def stop_production(
    body: StopIn,
    service: ProductionService = Depends(production_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StopOut:
    return await service.stop(body.batch_id, idempotency_key)


@router.get("/runs", response_model=RunPageOut)
async def list_runs(
    machine_id: str | None = None,
    batch_id: str | None = None,
    passed: str | None = None,
    status: str | None = None,
    q: str | None = None,
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    cursor: str | None = None,
    limit: int = 50,
    service: ProductionService = Depends(production_service),
) -> RunPageOut:
    flag: bool | None | str = ""
    if passed == "true":
        flag = True
    elif passed == "false":
        flag = False
    elif passed == "null":
        flag = None
    return await service.runs({
        "machine_id": machine_id, "batch_id": batch_id, "status": status, "q": q,
        "passed": flag, "from_ms": from_ms, "to_ms": to_ms,
    }, cursor, limit)


@router.get("/runs/{run_id}/samples", response_model=list[SampleOut])
async def run_samples(
    run_id: str,
    since: float | None = None,
    service: ProductionService = Depends(production_service),
) -> list[SampleOut]:
    return await service.samples(run_id, since)


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: str, service: ProductionService = Depends(production_service)) -> RunDetailOut:
    return await service.run(run_id)


@router.get("/export/production.csv")
async def export_production(
    batch_id: str | None = None,
    from_ms: int | None = Query(default=None, alias="from"),
    to_ms: int | None = Query(default=None, alias="to"),
    service: ProductionService = Depends(production_service),
) -> Response:
    text = await service.export_csv(batch_id, from_ms, to_ms)
    return Response(content=text, media_type="text/csv")

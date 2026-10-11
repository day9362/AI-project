from fastapi import APIRouter, Depends, Header, Query

from api.deps import plan_service
from models.dto.plan import DraftOut, PlanBody, PlanItemOut, PublishIn, PublishOut, ValidateOut
from service.plan_service import PlanService

router = APIRouter(tags=["plans"])


@router.get("/plans", response_model=list[PlanItemOut])
async def list_plans(plans: PlanService = Depends(plan_service)) -> list[PlanItemOut]:
    return await plans.list_plans()


@router.get("/plans/{plan_id}", response_model=PlanItemOut)
async def get_plan(
    plan_id: str,
    version: int | None = Query(default=None),
    plans: PlanService = Depends(plan_service),
) -> PlanItemOut:
    return await plans.get_plan(plan_id, version)


@router.post("/plans/validate", response_model=ValidateOut)
async def validate_plan(
    body: PlanBody,
    plans: PlanService = Depends(plan_service),
) -> ValidateOut:
    return await plans.validate(body)


@router.post("/plans", response_model=PublishOut)
async def publish_plan(
    body: PublishIn,
    plans: PlanService = Depends(plan_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PublishOut:
    return await plans.publish(body, idempotency_key)


@router.post("/plan-drafts", response_model=DraftOut)
async def create_draft(
    body: PlanBody,
    plans: PlanService = Depends(plan_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DraftOut:
    return await plans.create_draft(body, idempotency_key)


@router.put("/plan-drafts/{plan_id}", response_model=DraftOut)
async def update_draft(
    plan_id: str,
    body: PlanBody,
    plans: PlanService = Depends(plan_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DraftOut:
    return await plans.update_draft(plan_id, body, idempotency_key)


@router.delete("/plan-drafts/{plan_id}")
async def delete_draft(
    plan_id: str,
    plans: PlanService = Depends(plan_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    return await plans.delete_draft(plan_id, idempotency_key)

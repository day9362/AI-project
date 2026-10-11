import logging
import secrets
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms
from core.errors import ApiError
from models.dto.plan import DraftOut, PlanBody, PlanItemOut, PlanMetaOut, PlanOut, PublishIn, PublishOut, ValidateOut
from models.entity.overview import PlanEntity
from models.entity.user import UserEntity
from models.orm.plan import PlanRevisionOrm
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.plan_repo import PlanRepo
from service.cluster_sync import ClusterClient
from service.plan_rules import capability_bounds, validate_plan

log = logging.getLogger(__name__)
_cluster_pull_at = 0


class PlanService:
    def __init__(self, session: AsyncSession, user: UserEntity) -> None:
        self.session = session
        self.user = user
        self.plans = PlanRepo(session)
        self.machines = MachineRepo(session)
        self.audit = AuditRepo(session)
        self.cluster = ClusterClient()

    async def list_plans(self) -> list[PlanItemOut]:
        await self._pull_cluster()
        rows = await self.plans.list_revisions()
        grouped: dict[str, list[PlanRevisionOrm]] = {}
        for row in rows:
            grouped.setdefault(row.plan_id, []).append(row)
        items: list[PlanItemOut] = []
        for plan_id, group in grouped.items():
            drafts = [row for row in group if row.draft]
            published = [row for row in group if not row.draft]
            if published:
                latest = max(published, key=lambda row: row.version)
                items.append(self._item(latest, sorted(row.version for row in published)))
            for draft in drafts:
                items.append(self._item(draft, []))
        return items

    async def get_plan(self, plan_id: str, version: int | None) -> PlanItemOut:
        await self._pull_cluster()
        if version is None:
            row = await self.plans.latest_published(plan_id)
            if row is None:
                row = await self.plans.get(plan_id, 0)
        else:
            row = await self.plans.get(plan_id, version)
        if row is None:
            raise ApiError(404, "NOT_FOUND", "方案不存在")
        versions = [] if row.draft else await self.plans.versions(plan_id)
        return self._item(row, versions)

    async def validate(self, body: PlanBody) -> ValidateOut:
        issues = validate_plan(body, await self._bounds())
        return ValidateOut(ok=not any(item.level == "danger" for item in issues), issues=issues)

    async def publish(self, body: PublishIn, key: str | None) -> PublishOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return PublishOut.model_validate(cached)
        issues = validate_plan(body, await self._bounds())
        if any(item.level == "danger" for item in issues):
            raise ApiError(422, "VALIDATION_ERROR", "方案未通过校验", {"issues": [item.model_dump() for item in issues]})
        same = await self.plans.find_published_name(body.name)
        plan_id = same.plan_id if same is not None else None
        if body.plan_id and not body.plan_id.startswith("DRAFT-"):
            plan_id = body.plan_id
        created = await self._create_on_cluster(body, plan_id)
        row = self._revision(created["plan_id"], int(created["version"]), body, draft=False)
        await self.plans.save(row)
        await self.plans.upsert_slim(self._slim(row))
        draft = await self.plans.get(body.plan_id, 0) if body.plan_id else None
        if draft is not None and draft.draft:
            await self.plans.delete(draft)
        audit_id = await self.audit.write(
            self.user.user_id, "plan.publish", {"plan_id": row.plan_id, "version": row.version}
        )
        result = PublishOut(plan_id=row.plan_id, version=row.version, audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        return result

    async def create_draft(self, body: PlanBody, key: str | None) -> DraftOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return DraftOut.model_validate(cached)
        plan_id = f"DRAFT-{secrets.token_hex(4)}"
        row = self._revision(plan_id, 0, body, draft=True)
        await self.plans.save(row)
        audit_id = await self.audit.write(self.user.user_id, "plan_draft.create", {"plan_id": plan_id})
        result = DraftOut(**self._item(row, []).model_dump(), audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        return result

    async def update_draft(self, plan_id: str, body: PlanBody, key: str | None) -> DraftOut:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return DraftOut.model_validate(cached)
        row = await self._draft(plan_id)
        row.name = body.name
        row.body = body.model_dump()
        row.author = self.user.name
        row.updated_at = now_ms()
        audit_id = await self.audit.write(self.user.user_id, "plan_draft.update", {"plan_id": plan_id})
        result = DraftOut(**self._item(row, []).model_dump(), audit_id=audit_id)
        await self.audit.save_idempotent(self.user.user_id, key, result.model_dump())
        return result

    async def delete_draft(self, plan_id: str, key: str | None) -> dict:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return cached
        row = await self._draft(plan_id)
        await self.plans.delete(row)
        audit_id = await self.audit.write(self.user.user_id, "plan_draft.delete", {"plan_id": plan_id})
        result = {"audit_id": audit_id}
        await self.audit.save_idempotent(self.user.user_id, key, result)
        return result

    async def _draft(self, plan_id: str) -> PlanRevisionOrm:
        row = await self.plans.get(plan_id, 0)
        if row is None or not row.draft:
            raise ApiError(404, "NOT_FOUND", "草稿不存在")
        return row

    async def _bounds(self) -> dict[str, float]:
        machines = await self.machines.list_all()
        return capability_bounds([{"capability": row.capability} for row in machines])

    async def _pull_cluster(self) -> None:
        global _cluster_pull_at
        if now_ms() - _cluster_pull_at < 30_000:
            return
        _cluster_pull_at = now_ms()
        try:
            payload = await self.cluster.get("/plans", timeout=5)
        except (httpx.HTTPError, ValueError) as exc:
            log.info("cluster plans unavailable: %r", exc)
            return
        rows = _plan_rows(payload)
        saved = 0
        for raw in rows:
            parsed = _published_plan(raw)
            if parsed is None:
                continue
            plan_id, version, body = parsed
            if await self.plans.get(plan_id, version) is not None:
                saved += 1
                continue
            row = PlanRevisionOrm(
                plan_id=plan_id,
                version=version,
                name=body.name,
                body=body.model_dump(),
                author=str(raw.get("author") or ""),
                source="manual",
                updated_at=int(raw.get("updated_at") or now_ms()),
                draft=False,
            )
            await self.plans.save(row)
            await self.plans.upsert_slim(self._slim(row))
            saved += 1
        if rows and saved == 0:
            log.info("cluster plans not stored, first keys=%s", sorted(rows[0])[:12])

    async def _create_on_cluster(self, body: PlanBody, plan_id: str | None) -> dict[str, Any]:
        payload = body.model_dump()
        if plan_id:
            payload["plan_id"] = plan_id
        try:
            created = await self.cluster.post("/plans", payload)
        except httpx.TimeoutException as exc:
            raise ApiError(504, "CLUSTER_TIMEOUT", "集群响应超时", {"upstream": repr(exc)}) from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "集群发布失败", {"upstream": repr(exc)}) from exc
        parsed = _published_ids(created)
        if parsed is None:
            raise ApiError(502, "CLUSTER_ERROR", "集群没有返回方案编号", {"upstream": created})
        return {"plan_id": parsed[0], "version": parsed[1]}

    def _revision(self, plan_id: str, version: int, body: PlanBody, draft: bool) -> PlanRevisionOrm:
        return PlanRevisionOrm(
            plan_id=plan_id,
            version=version,
            name=body.name,
            body=body.model_dump(exclude={"plan_id", "version"}),
            author=self.user.name,
            source="manual",
            updated_at=now_ms(),
            draft=draft,
        )

    def _slim(self, row: PlanRevisionOrm) -> PlanEntity:
        body = row.body
        return PlanEntity(
            row.plan_id,
            row.version,
            row.name,
            int(body["duration_s"]),
            float(body["power_w"]),
            float(body["start_temp_c"]),
            float(body["ambient_low_c"]),
            float(body["ambient_high_c"]),
            row.draft,
        )

    def _item(self, row: PlanRevisionOrm, versions: list[int]) -> PlanItemOut:
        stored = {key: value for key, value in row.body.items() if key not in {"plan_id", "version"}}
        plan = PlanOut(plan_id=row.plan_id, version=row.version, **stored)
        meta = PlanMetaOut(
            plan_id=row.plan_id,
            versions=versions,
            updated_at=row.updated_at,
            author=row.author,
            source="agent" if row.source == "agent" else "manual",
            draft=row.draft,
        )
        return PlanItemOut(plan=plan, meta=meta)

    def _require_key(self, key: str | None) -> None:
        if not key:
            raise ApiError(400, "BAD_REQUEST", "缺少 Idempotency-Key")


def _plan_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("plans", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if payload.get("plan_id"):
            return [payload]
    return []


def _published_ids(raw: Any) -> tuple[str, int] | None:
    if not isinstance(raw, dict):
        return None
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else raw
    plan_id = plan.get("plan_id") or raw.get("plan_id")
    version = plan.get("version", raw.get("version"))
    if not plan_id or version in (None, 0):
        return None
    return str(plan_id), int(version)


def _published_plan(raw: Any) -> tuple[str, int, PlanBody] | None:
    found = _published_ids(raw)
    if found is None or not isinstance(raw, dict):
        return None
    plan = raw.get("plan") if isinstance(raw.get("plan"), dict) else raw
    try:
        body = PlanBody.model_validate(plan)
    except ValueError:
        return None
    return found[0], found[1], body

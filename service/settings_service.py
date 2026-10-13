import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import now_ms
from core.config import settings as env
from core.errors import ApiError
from models.entity.user import UserEntity
from models.orm.audit import JobRunOrm
from models.orm.settings import PlatformSettingsOrm
from repo.audit_repo import AuditRepo
from service.cluster_sync import ClusterClient, _items
from service.platform_state import apply_live, live
from service.settings_rules import interval_issues, merge_secrets, present
from tasks.scheduler import apply_job_intervals

_RUN_NAME = {
    "fleet": "sync.fleet",
    "slots": "sync.slots",
    "machine": "sync.fleet",
    "runs": "sync.runs",
    "samples": "sync.samples",
    "plans": "sync.catalog",
    "batches": "sync.catalog",
    "calib": "sync.calib",
    "agg": "rollup.agg",
}


class SettingsService:
    def __init__(self, session: AsyncSession, user: UserEntity | None = None) -> None:
        self.session = session
        self.user = user
        self.audit = AuditRepo(session)
        self.cluster = ClusterClient()

    async def get(self) -> dict:
        return present(await self._stored())

    async def save(self, incoming: dict, key: str | None) -> dict:
        self._require_key(key)
        cached = await self.audit.get_idempotent(self.user.user_id, key)
        if cached is not None:
            return cached
        issues = interval_issues(incoming.get("jobs") or [])
        if issues or incoming.get("source") not in {"cluster", "sim"}:
            if incoming.get("source") not in {"cluster", "sim"}:
                issues.append({"field": "source", "message": "数据源只能是 cluster 或 sim"})
            raise ApiError(422, "VALIDATION_ERROR", "设置没有通过校验", {"issues": issues})
        stored = await self._stored()
        try:
            merged = merge_secrets(incoming, stored)
        except (KeyError, TypeError) as exc:
            raise ApiError(422, "VALIDATION_ERROR", "设置结构不完整") from exc
        row = await self.session.get(PlatformSettingsOrm, 1)
        row.body = merged
        row.updated_at = now_ms()
        apply_live(merged)
        apply_job_intervals(merged["jobs"])
        if merged["source"] == "sim":
            await self._push_clock(float(merged["sim"]["speed"]))
        audit_id = await self.audit.write(self.user.user_id, "settings.save", {"source": merged["source"]})
        result = {**present(merged), "audit_id": audit_id}
        await self.audit.save_idempotent(self.user.user_id, key, result)
        return result

    async def test_connection(self, source: str, base_url: str, token: str) -> dict:
        stored = await self._stored()
        if "****" in (token or ""):
            token = stored["cluster"].get("token") or ""
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=8) as client:
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                response = await client.get("/fleet", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError:
            return {"ok": False, "latency_ms": 0, "machines": 0, "reachable": 0, "server_version": ""}
        machines = _items(payload, "machines", "items")
        reachable = sum(1 for row in machines if row.get("comm_status") != "DISCONNECTED")
        version = ""
        if isinstance(payload, dict):
            version = str(payload.get("server_version") or payload.get("version") or "")
        return {
            "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "machines": len(machines),
            "reachable": reachable,
            "server_version": version,
        }

    async def job_status(self) -> dict:
        items = []
        for key, name in _RUN_NAME.items():
            row = await self.session.scalar(
                select(JobRunOrm).where(JobRunOrm.name == name).order_by(JobRunOrm.started_at.desc()).limit(1)
            )
            if row is None:
                items.append({"key": key, "last_started_at": None, "duration_ms": None, "ok": None, "detail": ""})
            else:
                items.append({
                    "key": key,
                    "last_started_at": row.started_at,
                    "duration_ms": (row.finished_at or row.started_at) - row.started_at,
                    "ok": row.status == "ok",
                    "detail": row.detail,
                })
        return {"items": items}

    async def clock(self, speed: float, key: str | None) -> dict:
        self._require_key(key)
        await self._require_sim()
        if speed <= 0:
            raise ApiError(422, "VALIDATION_ERROR", "仿真倍率必须大于 0")
        await self._push_clock(speed)
        stored = await self._stored()
        stored["sim"]["speed"] = speed
        row = await self.session.get(PlatformSettingsOrm, 1)
        row.body = stored
        apply_live(stored)
        audit_id = await self.audit.write(self.user.user_id, "sim.clock", {"speed": speed})
        return {"speed": speed, "audit_id": audit_id}

    async def scenarios(self) -> dict:
        await self._require_sim()
        try:
            payload = await self.cluster.get("/scenarios")
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "读不到仿真场景") from exc
        names = _scenario_names(payload)
        return {"items": [{"name": name} for name in names]}

    async def apply_scenario(self, name: str, machine_id: str, key: str | None) -> dict:
        self._require_key(key)
        await self._require_sim()
        try:
            payload = await self.cluster.post(f"/scenarios/{name}/apply", {"machine_id": machine_id} if machine_id else None)
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "场景没有套上") from exc
        audit_id = await self.audit.write(self.user.user_id, "sim.scenario", {"name": name, "machine_id": machine_id})
        return {"audit_id": audit_id, "result": payload if isinstance(payload, dict) else {}}

    async def fault_catalog(self) -> dict:
        await self._require_sim()
        try:
            payload = await self.cluster.get("/faults/catalog")
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "读不到故障目录") from exc
        items = []
        for row in _items(payload, "items", "faults"):
            items.append({
                "kind": str(row.get("kind") or row.get("type") or ""),
                "layer": str(row.get("layer") or ""),
                "alarms": bool(row.get("alarms", True)),
            })
        return {"items": items}

    async def inject_fault(self, machine_id: str, kind: str, slot_index: int | None, key: str | None) -> dict:
        self._require_key(key)
        await self._require_sim()
        body = {"kind": kind, "type": kind}
        if slot_index is not None:
            body["slot_index"] = slot_index
        try:
            payload = await self.cluster.post(f"/machines/{machine_id}/faults", body)
        except httpx.HTTPError as exc:
            raise ApiError(502, "CLUSTER_ERROR", "故障没有注入") from exc
        audit_id = await self.audit.write(self.user.user_id, "sim.fault", {"machine_id": machine_id, "kind": kind})
        return {"audit_id": audit_id, "result": payload if isinstance(payload, dict) else {}}

    async def ground_truth(self, run_id: str) -> dict:
        if not live.ready or live.source != "sim" or not live.use_ground_truth:
            raise ApiError(404, "NOT_FOUND", "当前不能读取 ground truth")
        try:
            payload = await self.cluster.get(f"/runs/{run_id}/ground-truth")
        except httpx.HTTPError as exc:
            raise ApiError(404, "NOT_FOUND", "这次测试没有 ground truth") from exc
        return payload if isinstance(payload, dict) else {"run_id": run_id, "ground_truth": payload}

    async def _stored(self) -> dict:
        row = await self.session.get(PlatformSettingsOrm, 1)
        if row is None:
            row = PlatformSettingsOrm(id=1, body=default_settings(), updated_at=now_ms())
            self.session.add(row)
            await self.session.flush()
        return dict(row.body)

    async def _require_sim(self) -> None:
        if (await self._stored()).get("source") != "sim":
            raise ApiError(409, "CONFLICT", "当前数据源不是仿真平台")

    async def _push_clock(self, speed: float) -> None:
        try:
            await self.cluster.put("/fleet/clock", {"speed": speed, "time_scale": speed})
        except httpx.HTTPError:
            return

    def _require_key(self, key: str | None) -> None:
        if not self.user or not key:
            raise ApiError(400, "BAD_REQUEST", "缺少 Idempotency-Key")


def default_settings() -> dict:
    return {
        "source": "sim",
        "cluster": {
            "base_url": "http://10.20.1.10:18000/api",
            "token": env.cluster_token,
            "timeout_s": env.cluster_timeout_s,
            "retries": 2,
            "on_503": "skip",
        },
        "sim": {"base_url": env.cluster_base_url, "speed": 1, "use_ground_truth": False},
        "jobs": [
            {"key": "fleet", "name": "机群状态", "api": "GET /api/fleet", "interval_s": env.fleet_interval_s, "enabled": True, "note": "状态、通信、已装载方案"},
            {"key": "slots", "name": "槽位实时", "api": "GET /api/machines/{id}/slots", "interval_s": env.slots_interval_s, "enabled": True, "note": "步骤、功率、真空、温度"},
            {"key": "machine", "name": "机台详情", "api": "GET /api/machines/{id}", "interval_s": 10, "enabled": True, "note": "配置、报警、房间温度"},
            {"key": "runs", "name": "测试记录", "api": "GET /api/runs", "interval_s": env.runs_interval_s, "enabled": True, "note": "按 run_id 入库"},
            {"key": "samples", "name": "过程曲线", "api": "GET /api/runs/{id}/samples", "interval_s": 5, "enabled": True, "note": "打开曲线时增量拉取"},
            {"key": "plans", "name": "测试方案", "api": "GET /api/plans", "interval_s": 60, "enabled": True, "note": "方案目录"},
            {"key": "batches", "name": "批次与型号", "api": "GET /api/products/batches", "interval_s": env.catalog_interval_s, "enabled": True, "note": "含型号"},
            {"key": "calib", "name": "补偿与漂移", "api": "GET /api/machines/{id}/compensation", "interval_s": 60, "enabled": True, "note": "打开设备配置时读取"},
            {"key": "agg", "name": "5 分钟汇总", "api": "本地 agg_5m", "interval_s": env.agg_interval_s, "enabled": True, "note": "良率与热阻均值"},
        ],
        "storage": {
            "dsn": _dsn(env.database_url),
            "samples_days": 400,
            "runs_days": 1095,
            "agg_5m": True,
            "object_store": "",
        },
        "ai": {
            "base_url": env.anthropic_base_url,
            "api_key": env.anthropic_api_key,
            "monthly_budget_m": 120,
            "alert_pct": 80,
            "models": {
                "agent.analysis": "deepseek-v3",
                "agent.plan": "qwen3-max",
                "agent.ops": "qwen3-max",
                "report": "deepseek-v3",
                "anomaly": "deepseek-v3",
                "calib": "qwen3-max",
            },
        },
        "rules": {
            "drift_c": env.drift_c,
            "we_rules": ["WE-1", "WE-2", "WE-4"],
            "sentinel_as_data_anomaly": env.sentinel_as_data_anomaly,
            "degraded_alarm": env.degraded_alarm,
            "ack_timeout_min": 15,
        },
    }


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _scenario_names(payload: object) -> list[str]:
    if isinstance(payload, dict):
        raw = payload.get("names") or payload.get("scenarios") or payload.get("items") or []
    elif isinstance(payload, list):
        raw = payload
    else:
        raw = []
    names = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names or ["slow_drift", "sudden_bias", "vacuum_leak", "packet_loss"]

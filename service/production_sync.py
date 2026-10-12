import logging
from statistics import mean, pstdev

from core.clock import now_ms
from models.orm.production import BatchRecordOrm, ProductModelOrm, ProductionOrm
from models.orm.stats import RunOrm
from repo.production_repo import ProductionRepo
from service.cluster_sync import ClusterClient, _items

log = logging.getLogger(__name__)


class CatalogSync:
    def __init__(self, repo: ProductionRepo, client: ClusterClient | None = None) -> None:
        self.repo = repo
        self.client = client or ClusterClient()

    async def sync_models(self) -> int:
        payload = await self.client.get("/product-models", timeout=8)
        rows = []
        for raw in _items(payload, "models", "items"):
            name = raw.get("model")
            if not name:
                continue
            rows.append(ProductModelOrm(
                model=str(name),
                resistance_mean=float(raw.get("resistance_mean") or 0),
                resistance_sd=float(raw.get("resistance_sd") or 0),
                power_w=float(raw.get("power_w") or 0),
            ))
        if rows:
            await self.repo.replace_models(rows)
        return len(rows)

    async def sync_batches(self) -> int:
        payload = await self.client.get("/products/batches", timeout=8)
        remaining = await self._remaining()
        saved = 0
        for raw in _items(payload, "batches", "items"):
            batch_id = str(raw.get("batch_id") or "")
            if not batch_id:
                continue
            current = await self.repo.batch(batch_id)
            row = current or BatchRecordOrm(batch_id=batch_id)
            row.model = str(raw.get("model") or row.model or "")
            row.count = int(raw.get("count") or row.count or 0)
            row.defect_ratio = float(raw.get("defect_ratio") or 0)
            row.batch_factor = float(raw.get("batch_factor") or 1)
            if "remaining" in raw:
                row.remaining = int(raw.get("remaining") or 0)
            elif batch_id in remaining:
                row.remaining = remaining[batch_id]
            await self._fill_stats(row)
            await self.repo.save_batch(row)
            saved += 1
        return saved

    async def sync_production(self) -> bool:
        payload = None
        reached = False
        for path in ("/fleet/production", "/production"):
            try:
                payload = await self.client.get(path, timeout=8)
                reached = True
                break
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status == 404:
                    continue
                log.info("production sync %s skipped: %r", path, exc)
        if not reached:
            current = await self.repo.production()
            return current is not None
        if not isinstance(payload, dict) or not payload.get("batch_id"):
            await self.repo.save_production(ProductionOrm(id=1, active=False))
            return False
        await self.repo.save_production(ProductionOrm(
            id=1,
            active=True,
            batch_id=str(payload.get("batch_id") or ""),
            queue_remaining=int(payload.get("queue_remaining") or 0),
            plan_id=str(payload.get("plan_id") or ""),
            plan_version=int(payload.get("plan_version") or 0),
        ))
        return True

    async def _remaining(self) -> dict[str, int]:
        try:
            payload = await self.client.get("/products", timeout=8)
        except Exception as exc:
            log.info("products unavailable: %r", exc)
            return {}
        counts: dict[str, int] = {}
        for raw in _items(payload, "products", "items"):
            if str(raw.get("state") or raw.get("status") or "") != "NEW":
                continue
            batch_id = str(raw.get("batch_id") or "")
            if batch_id:
                counts[batch_id] = counts.get(batch_id, 0) + 1
        return counts

    async def _fill_stats(self, row: BatchRecordOrm) -> None:
        runs = await self.repo.runs_of(row.batch_id)
        row.tested = len(runs)
        row.passed = sum(1 for run in runs if run.passed is True)
        row.failed = sum(1 for run in runs if run.passed is False)
        row.aborted = sum(1 for run in runs if run.status in {"ABORTED", "FAULT"} or run.passed is None and run.status != "RUNNING")
        machines = sorted({run.machine_id for run in runs if run.machine_id})
        if machines:
            row.machine_ids = machines
        if runs and not row.plan_id:
            row.plan_id = runs[0].plan_id
            row.plan_version = runs[0].plan_version
        times = [run.ended_at for run in runs if run.ended_at]
        if times and not row.started_at:
            row.started_at = min(times)
        production = await self.repo.production()
        if production is not None and production.batch_id == row.batch_id:
            row.state = "running"
            row.ended_at = None
            row.plan_id = production.plan_id or row.plan_id
            row.plan_version = production.plan_version or row.plan_version
            row.eta_s = _eta(row.remaining, runs)
        elif row.tested:
            row.state = "done"
            row.ended_at = max(times) if times else now_ms()
            row.eta_s = None
        rcs = [run.rc for run in runs if run.rc is not None]
        row.rc_mean = round(mean(rcs), 4) if rcs else 0
        row.rc_sd = round(pstdev(rcs), 4) if len(rcs) > 1 else 0
        row.top_fail = _top_fail(runs)


def _top_fail(runs: list[RunOrm]) -> str:
    counts: dict[str, int] = {}
    for run in runs:
        for item in run.fail_items or []:
            counts[str(item)] = counts.get(str(item), 0) + 1
    if not counts:
        return ""
    return max(counts, key=counts.get)


def _eta(remaining: int, runs: list[RunOrm]) -> int | None:
    if remaining <= 0 or not runs:
        return None
    machines = len({run.machine_id for run in runs if run.machine_id}) or 1
    return int(remaining * 180 / machines)

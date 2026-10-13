"""批次报告只做结果汇总，不生成结论以外的图表数据。"""

from statistics import mean, pstdev


def build_report(batches: list[dict], runs: list[dict], limits_by_plan: dict[tuple[str, int], list[dict]]) -> dict:
    finished = [run for run in runs if run.get("status") != "RUNNING"]
    by_batch: dict[str, list[dict]] = {}
    for run in finished:
        by_batch.setdefault(str(run.get("batch_id") or ""), []).append(run)

    included = []
    for batch in batches:
        rows = by_batch.get(batch["batch_id"], [])
        if not rows:
            continue
        included.append(_batch_view(batch, rows))

    used = [run for batch in included for run in by_batch[batch["batch_id"]]]
    summary = _summary(included, used, limits_by_plan)
    return {
        "batches": included,
        "summary": summary,
        "machine_yield": _machine_yield(used),
        "rc_histogram": _histogram({batch["batch_id"]: [run["rc"] for run in by_batch[batch["batch_id"]] if run.get("rc") is not None] for batch in included}),
        "fail_pareto": _pareto(used),
        "delta_profile": _profile(included, by_batch, limits_by_plan),
        "compare": [
            {"batch_id": batch["batch_id"], "yield_rate": batch["yield_rate"], "rc_mean": batch["rc_mean"]}
            for batch in included
        ],
    }


def _batch_view(batch: dict, rows: list[dict]) -> dict:
    passed = sum(1 for run in rows if run.get("passed") is True)
    failed = sum(1 for run in rows if run.get("passed") is False)
    aborted = sum(1 for run in rows if run.get("passed") is None)
    rcs = [float(run["rc"]) for run in rows if run.get("rc") is not None]
    return {
        **batch,
        "tested": len(rows),
        "passed": passed,
        "failed": failed,
        "aborted": aborted,
        "yield_rate": _yield(passed, len(rows)),
        "rc_mean": round(mean(rcs), 3) if rcs else 0,
        "rc_sd": round(pstdev(rcs), 3) if len(rcs) > 1 else 0,
        "top_fail": _pareto(rows)[0]["item"] if _pareto(rows) else "",
    }


def _summary(batches: list[dict], runs: list[dict], limits_by_plan: dict[tuple[str, int], list[dict]]) -> dict:
    tested = sum(batch["tested"] for batch in batches)
    passed = sum(batch["passed"] for batch in batches)
    failed = sum(batch["failed"] for batch in batches)
    aborted = sum(batch["aborted"] for batch in batches)
    rcs = [float(run["rc"]) for run in runs if run.get("rc") is not None]
    dts = [float(run["dt01"]) for run in runs if run.get("dt01") is not None]
    usl = _usl(batches, limits_by_plan)
    return {
        "tested": tested,
        "passed": passed,
        "failed": failed,
        "aborted": aborted,
        "yield_rate": _yield(passed, tested),
        "rc_mean": round(mean(rcs), 3) if rcs else 0,
        "rc_sd": round(pstdev(rcs), 3) if len(rcs) > 1 else 0,
        "cpk_t01": _cpk(dts, usl),
        "usl_t01": usl,
        "machine_count": len({run.get("machine_id") for run in runs if run.get("machine_id")}),
    }


def _machine_yield(runs: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for run in runs:
        grouped.setdefault(str(run.get("machine_id") or ""), []).append(run)
    rows = [
        {"machine_id": machine_id, "n": len(items), "passed": sum(1 for run in items if run.get("passed") is True)}
        for machine_id, items in grouped.items() if machine_id
    ]
    return sorted(rows, key=lambda row: (row["passed"] / row["n"] if row["n"] else 1, row["machine_id"]))


def _histogram(values_by_batch: dict[str, list[float]], bins: int = 12) -> dict:
    flat = [value for values in values_by_batch.values() for value in values]
    if not flat:
        return {"edges": [], "counts": {batch_id: [] for batch_id in values_by_batch}}
    lo, hi = min(flat), max(flat)
    if lo == hi:
        lo -= 0.05
        hi += 0.05
    width = (hi - lo) / bins
    edges = [round(lo + index * width, 4) for index in range(bins + 1)]
    counts = {}
    for batch_id, values in values_by_batch.items():
        bucket = [0] * bins
        for value in values:
            index = min(bins - 1, max(0, int((value - lo) / width)))
            bucket[index] += 1
        counts[batch_id] = bucket
    return {"edges": edges, "counts": counts}


def _pareto(runs: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for run in runs:
        if run.get("passed") is not False:
            continue
        items = [str(item) for item in (run.get("fail_items") or []) if item]
        for item in items or ["未记录判定项"]:
            counts[item] = counts.get(item, 0) + 1
    return [{"item": item, "count": count} for item, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]


def _profile(batches: list[dict], by_batch: dict[str, list[dict]], limits_by_plan: dict[tuple[str, int], list[dict]]) -> dict:
    items = _delta_items(batches, by_batch, limits_by_plan)
    mean_by_batch = {}
    for batch in batches:
        rows = by_batch[batch["batch_id"]]
        mean_by_batch[batch["batch_id"]] = [_mean_delta(rows, item) for item in items]
    profile = {
        "items": items,
        "mean": mean_by_batch,
        "limit": [_limit(batches, limits_by_plan, item) for item in items],
    }
    if len(batches) == 1 and items:
        profile["p95"] = [_p95(by_batch[batches[0]["batch_id"]], item) for item in items]
    return profile


def _delta_items(batches: list[dict], by_batch: dict[str, list[dict]], limits_by_plan: dict[tuple[str, int], list[dict]]) -> list[str]:
    names: set[str] = set()
    for batch in batches:
        for limit in limits_by_plan.get((batch.get("plan_id"), batch.get("plan_version")), []):
            item = str(limit.get("item") or "")
            if item.startswith("Temp_T1-T") and not limit.get("skipped"):
                names.add(item.removeprefix("Temp_"))
        for run in by_batch.get(batch["batch_id"], []):
            for key in (run.get("deltas") or {}):
                if str(key).startswith("Temp_T1-T"):
                    names.add(str(key).removeprefix("Temp_"))
    return sorted(names, key=_delta_order)


def _mean_delta(runs: list[dict], item: str) -> float | None:
    values = _delta_values(runs, item)
    if not values:
        return None
    return round(mean(values), 3)


def _p95(runs: list[dict], item: str) -> float | None:
    values = sorted(_delta_values(runs, item))
    if not values:
        return None
    return round(values[min(len(values) - 1, int(len(values) * 0.95))], 3)


def _delta_values(runs: list[dict], item: str) -> list[float]:
    key = item if item.startswith("Temp_") else f"Temp_{item}"
    values = []
    for run in runs:
        raw = (run.get("deltas") or {}).get(key)
        if raw is None:
            raw = (run.get("deltas") or {}).get(item)
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    return values


def _limit(batches: list[dict], limits_by_plan: dict[tuple[str, int], list[dict]], item: str) -> float | None:
    highs = []
    for batch in batches:
        for limit in limits_by_plan.get((batch.get("plan_id"), batch.get("plan_version")), []):
            if limit.get("item") in {item, f"Temp_{item}"} and not limit.get("skipped") and limit.get("high") is not None:
                highs.append(float(limit["high"]))
    return min(highs) if highs else None


def _usl(batches: list[dict], limits_by_plan: dict[tuple[str, int], list[dict]]) -> float | None:
    highs = []
    for batch in batches:
        for limit in limits_by_plan.get((batch.get("plan_id"), batch.get("plan_version")), []):
            if limit.get("item") == "Temp_T0-T1" and not limit.get("skipped") and limit.get("high") is not None:
                highs.append(float(limit["high"]))
    return min(highs) if highs else None


def _cpk(values: list[float], usl: float | None) -> float | None:
    if usl is None or len(values) < 2:
        return None
    sigma = pstdev(values)
    if sigma == 0:
        return None
    return round((usl - mean(values)) / (3 * sigma), 2)


def _yield(passed: int, tested: int) -> float:
    if not tested:
        return 0
    return round(passed / tested * 100, 2)


def _delta_order(item: str) -> tuple[int, str]:
    tail = item.rsplit("-T", 1)[-1]
    return (int(tail), item) if tail.isdigit() else (10_000, item)

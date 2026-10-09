from models.entity.overview import AggEntity, RunEntity

BUCKET_MS = 300_000


def aggregate_runs(runs: list[RunEntity], start_ms: int, end_ms: int) -> list[AggEntity]:
    start = start_ms // BUCKET_MS * BUCKET_MS
    end = end_ms // BUCKET_MS * BUCKET_MS
    buckets: dict[int, list[RunEntity]] = {}
    cursor = start
    while cursor <= end:
        buckets[cursor] = []
        cursor += BUCKET_MS
    for run in runs:
        if run.status == "RUNNING":
            continue
        bucket = run.ended_at // BUCKET_MS * BUCKET_MS
        if bucket in buckets:
            buckets[bucket].append(run)
    out: list[AggEntity] = []
    for bucket in sorted(buckets):
        rows = buckets[bucket]
        passed = sum(1 for r in rows if r.status == "COMPLETED" and r.passed)
        failed = sum(1 for r in rows if r.status == "COMPLETED" and r.passed is False)
        aborted = sum(1 for r in rows if r.status in {"ABORTED", "FAULT"})
        rcs = [r.rc for r in rows if r.rc is not None]
        dts = [r.dt01 for r in rows if r.dt01 is not None]
        out.append(AggEntity(
            bucket=bucket,
            tests=passed + failed + aborted,
            passed=passed,
            failed=failed,
            aborted=aborted,
            rc_mean=round(sum(rcs) / len(rcs), 3) if rcs else 0,
            dt01_mean=round(sum(dts) / len(dts), 3) if dts else 0,
        ))
    return out


def yield_rate(passed: int, tests: int) -> float:
    if tests <= 0:
        return 0
    return round(passed / tests * 100, 2)

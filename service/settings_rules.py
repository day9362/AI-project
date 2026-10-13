import re

JOB_KEYS = ("fleet", "slots", "machine", "runs", "samples", "plans", "batches", "calib", "agg")
_FLOOR = {"fleet": 1, "slots": 1, "samples": 1}


def interval_floor(key: str) -> int:
    return _FLOOR.get(key, 5)


def interval_issues(jobs: list[dict]) -> list[dict]:
    seen = [job.get("key") for job in jobs]
    issues = []
    if set(seen) != set(JOB_KEYS) or len(seen) != len(JOB_KEYS):
        issues.append({"field": "jobs", "message": "同步任务必须是 fleet、slots、machine、runs、samples、plans、batches、calib、agg"})
        return issues
    for job in jobs:
        if not job.get("enabled"):
            continue
        floor = interval_floor(str(job["key"]))
        if int(job.get("interval_s") or 0) < floor:
            issues.append({"field": f"jobs.{job['key']}.interval_s", "message": f"{job['key']} 间隔不能低于 {floor} 秒"})
    return issues


def mask_secret(value: str) -> str:
    text = value or ""
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return f"{text[:3]}****{text[-4:]}"


def mask_dsn(dsn: str) -> str:
    return re.sub(r"(://[^:/@]*:)([^@]+)(@)", lambda match: match.group(1) + mask_secret(match.group(2)) + match.group(3), dsn, count=1)


def same_secret(incoming: str, stored: str) -> bool:
    return incoming == stored or incoming == mask_secret(stored)


def same_dsn(incoming: str, stored: str) -> bool:
    return incoming == stored or incoming == mask_dsn(stored)


def present(body: dict) -> dict:
    shown = {
        "source": body["source"],
        "cluster": {**body["cluster"], "token": mask_secret(body["cluster"].get("token") or "")},
        "sim": dict(body["sim"]),
        "jobs": list(body["jobs"]),
        "storage": {**body["storage"], "dsn": mask_dsn(body["storage"].get("dsn") or "")},
        "ai": {**body["ai"], "api_key": mask_secret(body["ai"].get("api_key") or "")},
        "rules": dict(body["rules"]),
    }
    return shown


def merge_secrets(incoming: dict, stored: dict) -> dict:
    merged = {
        "source": incoming["source"],
        "cluster": dict(incoming["cluster"]),
        "sim": dict(incoming["sim"]),
        "jobs": list(incoming["jobs"]),
        "storage": dict(incoming["storage"]),
        "ai": dict(incoming["ai"]),
        "rules": dict(incoming["rules"]),
    }
    if same_secret(merged["cluster"].get("token") or "", stored["cluster"].get("token") or ""):
        merged["cluster"]["token"] = stored["cluster"].get("token") or ""
    if same_secret(merged["ai"].get("api_key") or "", stored["ai"].get("api_key") or ""):
        merged["ai"]["api_key"] = stored["ai"].get("api_key") or ""
    if same_dsn(merged["storage"].get("dsn") or "", stored["storage"].get("dsn") or ""):
        merged["storage"]["dsn"] = stored["storage"].get("dsn") or ""
    return merged

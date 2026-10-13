"""设备操作只决定能不能发、发完本地要改什么，不自己编状态。"""


def ensure_online(comm_status: str) -> str | None:
    if comm_status == "DISCONNECTED":
        return "MACHINE_DISCONNECTED"
    return None


def sampling_run_ids(slots: list[dict], running_ids: list[str]) -> list[str]:
    found = [run_id for run_id in running_ids if run_id]
    for slot in slots:
        if slot.get("phase") == "SAMPLING" and slot.get("run_id"):
            found.append(str(slot["run_id"]))
    return list(dict.fromkeys(found))


def plan_spans(events: list[dict], current: tuple[str, int] | None, now: int) -> list[dict]:
    spans: list[dict] = []
    for event in events:
        if not event.get("accepted", True):
            continue
        key = (event["plan_id"], int(event["version"]))
        if spans and (spans[-1]["plan_id"], spans[-1]["version"]) == key:
            continue
        if spans:
            spans[-1]["to"] = event["created_at"]
        spans.append({
            "plan_id": event["plan_id"],
            "name": event.get("name") or event["plan_id"],
            "version": int(event["version"]),
            "from": event["created_at"],
            "to": None,
        })
    if spans and current and current != (spans[-1]["plan_id"], spans[-1]["version"]) and spans[-1]["to"] is None:
        spans[-1]["to"] = now
    if current and (not spans or (spans[-1]["plan_id"], spans[-1]["version"]) != current):
        spans.append({
            "plan_id": current[0], "name": current[0], "version": current[1], "from": now, "to": None,
        })
    return spans


def compensation_channels(body: object) -> list[dict]:
    if isinstance(body, list):
        return [_channel(row) for row in body if _channel(row)]
    if not isinstance(body, dict):
        return []
    for key in ("compensation", "channels", "items"):
        rows = body.get(key)
        if isinstance(rows, list):
            return [item for row in rows if (item := _channel(row))]
    if body and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in body.values()):
        return [{"channel": str(key), "value": float(value)} for key, value in body.items()]
    return []


def compensation_suggestion(items: list[dict], measured_at: int) -> dict:
    suggested = []
    for item in items:
        value = float(item["value"])
        if abs(value) < 0.01:
            continue
        suggested.append({
            "channel": item["channel"],
            "value": round(-value, 3),
            "reason": f"标准样品复测偏差 {value:+.3f} ℃",
        })
    return {"items": suggested, "basis_at": measured_at if suggested else 0}


def drift_rows(body: object) -> list[dict]:
    rows = body if isinstance(body, list) else []
    if isinstance(body, dict):
        rows = body.get("drifts") or body.get("items") or []
    found = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_current = row.get("current")
        raw_value = row.get("value")
        value = float(raw_value) if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool) else 0.0
        current = float(raw_current) if isinstance(raw_current, (int, float)) and not isinstance(raw_current, bool) else value
        found.append({
            "drift_id": str(row.get("drift_id") or row.get("id") or ""),
            "channel": str(row.get("channel") or ""),
            "kind": str(row.get("kind") or row.get("type") or ""),
            "value": value,
            "current": current,
        })
    return found


def cluster_compensation(mode: str, items: list[dict]) -> dict:
    return {
        "mode": mode,
        "compensation": items,
        "channels": items,
        "values": {item["channel"]: item["value"] for item in items},
    }


def _channel(row: object) -> dict | None:
    if not isinstance(row, dict) or not row.get("channel"):
        return None
    value = row.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return {"channel": str(row["channel"]), "value": float(value)}

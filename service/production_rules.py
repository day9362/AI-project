from models.dto.production import IssueOut, ProductionIn

BUSY = {"PREHEATING", "WAITING_LOAD", "CLAMPING", "SAMPLING", "RECOVERING"}


def precheck(
    body: ProductionIn,
    *,
    plan_power: float | None,
    limits: list[dict],
    model_power: float | None,
    remaining: int | None,
    machines: list[dict],
    sim_mode: bool,
) -> list[IssueOut]:
    issues: list[IssueOut] = []
    if body.batch_id and body.serial_numbers:
        issues.append(IssueOut(level="danger", field="batch_id", message="批次号和序列号列表只能留一个"))
    if not body.batch_id and not body.serial_numbers:
        issues.append(IssueOut(level="danger", field="batch_id", message="要指定批次号或序列号列表"))
    if not body.machine_ids:
        issues.append(IssueOut(level="danger", field="machine_ids", message="至少选择一台机"))
    if plan_power is None:
        issues.append(IssueOut(level="danger", field="plan_id", message="方案不存在"))
    elif model_power is not None and abs(plan_power - model_power) >= 0.05:
        issues.append(IssueOut(
            level="danger",
            field="power_w",
            message=f"方案功率 {plan_power:g} W 与型号参考功率 {model_power:g} W 不一致",
        ))
    if not any(item.get("item") == "power_w" and not item.get("skipped") for item in limits):
        issues.append(IssueOut(level="danger", field="power_w", message="方案没有 power_w 判定项"))
    if body.batch_id and (remaining is None or remaining <= 0):
        issues.append(IssueOut(level="danger", field="batch_id", message="这个批次没有剩余未测的片子"))
    known = {row["machine_id"]: row for row in machines}
    for machine_id in body.machine_ids:
        row = known.get(machine_id)
        if row is None:
            issues.append(IssueOut(level="danger", field="machine_ids", message=f"{machine_id} 不在当前机群里"))
            continue
        if row.get("comm_status") == "DISCONNECTED":
            issues.append(IssueOut(level="danger", field="machine_ids", message=f"{machine_id} 通信已断开"))
        if row.get("status") in {"FAULT", "MAINTENANCE"}:
            issues.append(IssueOut(level="danger", field="machine_ids", message=f"{machine_id} 处于 {row['status']}，不能下发"))
        busy = any(slot.get("phase") in BUSY for slot in row.get("slots") or [])
        other = row.get("plan_id") and (row.get("plan_id") != body.plan_id or row.get("plan_version") != body.plan_version)
        if busy and other:
            issues.append(IssueOut(level="warn", field="machine_ids", message=f"{machine_id} 正在测量其它方案，开始后会被跳过"))
        if sim_mode and float(row.get("speed") or 0) < 1:
            issues.append(IssueOut(level="warn", field="machine_ids", message=f"{machine_id} 仿真倍率过低，进度会很慢"))
    if not any(item.level == "danger" for item in issues):
        issues.insert(0, IssueOut(level="ok", message="可以下发"))
    return issues

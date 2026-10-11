from models.dto.plan import IssueOut, PlanBody

LIMIT_ITEMS = [
    "Temp_Ta",
    "Temp_T0-T1",
    *[f"Temp_T1-T{i}" for i in range(2, 15)],
    *[f"F{i}" for i in range(1, 15)],
    "power_w",
]
ORIENTATIONS = {0, 90, 180, 270}
MODELS = [
    {"model": "tb158", "power_w": 2.5},
    {"model": "tb172", "power_w": 2.5},
    {"model": "tb179", "power_w": 2.5},
    {"model": "HVP1307G17-1", "power_w": 3.5},
]


def capability_bounds(machines: list[dict]) -> dict[str, float]:
    bounds = {
        "duration_low_s": 1,
        "duration_high_s": 600,
        "power_low_w": 0.1,
        "power_high_w": 10,
        "force_low_g": 20,
        "force_high_g": 300,
        "start_low_c": 20,
        "start_high_c": 80,
        "sample_low_s": 1,
        "sample_high_s": 10,
        "overtemp_low_c": 40,
        "overtemp_high_c": 120,
        "ambient_low_c": 10,
        "ambient_high_c": 40,
    }
    caps = [row.get("capability") or {} for row in machines if isinstance(row.get("capability"), dict)]
    caps = [cap for cap in caps if cap]
    if not caps:
        return bounds
    for low, high in (
        ("duration_low_s", "duration_high_s"),
        ("power_low_w", "power_high_w"),
        ("force_low_g", "force_high_g"),
    ):
        lows = [float(cap[low]) for cap in caps if cap.get(low) is not None]
        highs = [float(cap[high]) for cap in caps if cap.get(high) is not None]
        if lows:
            bounds[low] = max(lows)
        if highs:
            bounds[high] = min(highs)
    return bounds


def validate_plan(body: PlanBody, bounds: dict[str, float]) -> list[IssueOut]:
    issues: list[IssueOut] = []

    def danger(field: str, message: str) -> None:
        issues.append(IssueOut(level="danger", field=field, message=message))

    def check_range(field: str, value: float, low_key: str, high_key: str, unit: str, label: str) -> None:
        low, high = bounds[low_key], bounds[high_key]
        if value < low or value > high:
            danger(field, f"{label} {value:g} {unit} 不在机台能力范围 {low:g}–{high:g} {unit}")

    check_range("start_temp_c", body.start_temp_c, "start_low_c", "start_high_c", "℃", "起始温度")
    check_range("duration_s", body.duration_s, "duration_low_s", "duration_high_s", "s", "测量时长")
    check_range("sample_period_s", body.sample_period_s, "sample_low_s", "sample_high_s", "s", "采样周期")
    check_range("power_w", body.power_w, "power_low_w", "power_high_w", "W", "加热功率")
    check_range("force_g", body.force_g, "force_low_g", "force_high_g", "g", "压紧力")
    check_range("overtemp_c", body.overtemp_c, "overtemp_low_c", "overtemp_high_c", "℃", "超温保护")
    check_range("ambient_low_c", body.ambient_low_c, "ambient_low_c", "ambient_high_c", "℃", "环境温度下限")
    check_range("ambient_high_c", body.ambient_high_c, "ambient_low_c", "ambient_high_c", "℃", "环境温度上限")
    if body.orientation not in ORIENTATIONS:
        danger("orientation", "方向只能是 0、90、180、270")
    if body.ambient_low_c >= body.ambient_high_c:
        danger("ambient_low_c", "环境温度下限必须小于上限")
    if body.overtemp_c <= body.start_temp_c + 10:
        issues.append(IssueOut(level="warn", field="overtemp_c", message="超温保护距离起始温度不足 10 ℃，可能误触发"))

    seen: set[str] = set()
    dupes: set[str] = set()
    for rule in body.limits:
        if rule.item not in LIMIT_ITEMS:
            danger("limits", f"未知判定项 {rule.item}")
        if rule.item in seen:
            dupes.add(rule.item)
        seen.add(rule.item)
        if not rule.skipped and rule.low is not None and rule.high is not None and rule.low >= rule.high:
            danger(rule.item, f"{rule.item} 下限必须小于上限")
    if dupes:
        danger("limits", f"判定项重复：{', '.join(sorted(dupes))}")

    power = next((rule for rule in body.limits if rule.item == "power_w" and not rule.skipped), None)
    if power is None:
        issues.append(IssueOut(level="warn", field="power_w", message="缺少 power_w 判定项，功率异常的片子不会被判不合格"))
    elif power.low is not None and power.high is not None and not (power.low <= body.power_w <= power.high):
        danger("power_w", f"加热功率 {body.power_w:g} W 不在 power_w 判定范围内")

    matched = [row["model"] for row in MODELS if abs(row["power_w"] - body.power_w) < 0.05]
    if matched:
        issues.append(IssueOut(level="ok", field="power_w", message=f"功率与 {' / '.join(matched)} 的参考功率一致"))
    else:
        issues.append(IssueOut(level="warn", field="power_w", message="功率不匹配任何已登记型号的参考功率"))
    if not any(item.level == "danger" for item in issues):
        issues.insert(0, IssueOut(level="ok", message="全部字段都在机台能力范围内"))
    return issues

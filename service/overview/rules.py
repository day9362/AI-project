from models.entity.overview import AlarmEntity, AttributionEntity

SENTINELS = {99999, 9999, -1, -2}


def alarm_category(source: str, code: str) -> str:
    if source == "通信" or code.startswith("COMM") or code == "PACKET_LOSS":
        return "communication"
    if source == "数据" or code.startswith("SENSOR"):
        return "data"
    if source == "判定":
        return "product"
    return "equipment"


def is_sentinel(value: float) -> bool:
    return value in SENTINELS or value >= 9999


def attribute(alarm: AlarmEntity, created_at: int) -> AttributionEntity:
    category = alarm_category(alarm.source, alarm.code)
    suggestions = {
        "equipment": "先确认夹具与传感器，再用标准样品复测，补偿只作为文字建议",
        "product": "对照同批次其它机台；若只有该批次不合格，按来料缺陷处理",
        "communication": "检查该机台链路，恢复在线前不要下发新指令",
        "data": "哨兵值按数据异常保留，不要当成真实温度",
    }
    return AttributionEntity(
        alarm_id=alarm.id,
        status="done",
        category=category,
        confidence=0.8,
        summary=f"{alarm.machine_id} {alarm.code}：{alarm.message}",
        evidence=[alarm.message, f"来源 {alarm.source}，级别 {alarm.level}"],
        suggestion=suggestions[category],
        model="rule",
        created_at=created_at,
    )

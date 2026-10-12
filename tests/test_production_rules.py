from models.dto.production import ProductionIn
from service.production_rules import precheck


def _body(**extra) -> ProductionIn:
    data = {
        "machine_ids": ["M01"],
        "plan_id": "PLAN-1",
        "plan_version": 1,
        "batch_id": "B-1",
        "auto_recover": True,
    }
    data.update(extra)
    return ProductionIn.model_validate(data)


def _machine(**extra) -> dict:
    row = {
        "machine_id": "M01", "status": "READY", "comm_status": "ONLINE",
        "plan_id": "PLAN-1", "plan_version": 1, "speed": 1, "slots": [{"phase": "IDLE"}],
    }
    row.update(extra)
    return row


def test_power_mismatch_is_danger():
    issues = precheck(
        _body(), plan_power=2.5, limits=[{"item": "power_w", "skipped": False}],
        model_power=3.5, remaining=10, machines=[_machine()], sim_mode=False,
    )
    assert any(item.level == "danger" and item.field == "power_w" for item in issues)


def test_no_remaining_and_fault_are_danger():
    issues = precheck(
        _body(), plan_power=2.5, limits=[{"item": "power_w", "skipped": False}],
        model_power=2.5, remaining=0, machines=[_machine(status="FAULT")], sim_mode=False,
    )
    assert any("没有剩余" in item.message for item in issues)
    assert any("FAULT" in item.message for item in issues)


def test_busy_other_plan_is_warn():
    issues = precheck(
        _body(), plan_power=2.5, limits=[{"item": "power_w", "skipped": False}],
        model_power=2.5, remaining=4,
        machines=[_machine(plan_id="PLAN-OLD", slots=[{"phase": "SAMPLING"}])],
        sim_mode=False,
    )
    assert any(item.level == "warn" and "会被跳过" in item.message for item in issues)
    assert not any(item.level == "danger" for item in issues)

from models.dto.plan import PlanBody
from service.plan_rules import capability_bounds, validate_plan


def _body(**overrides) -> PlanBody:
    data = {
        "name": "HVP 3.5W",
        "start_temp_c": 25,
        "duration_s": 180,
        "sample_period_s": 1,
        "power_w": 3.5,
        "force_g": 120,
        "orientation": 0,
        "overtemp_c": 80,
        "ambient_low_c": 18,
        "ambient_high_c": 28,
        "limits": [{"item": "power_w", "low": 3.2, "high": 3.8, "unit": "W", "skipped": False}],
    }
    data.update(overrides)
    return PlanBody.model_validate(data)


def test_matching_power_is_ok():
    issues = validate_plan(_body(), capability_bounds([]))
    assert issues[0].level == "ok"
    assert any(item.level == "ok" and "HVP1307G17-1" in item.message for item in issues)
    assert not any(item.level == "danger" for item in issues)


def test_power_outside_limit_is_danger():
    issues = validate_plan(_body(power_w=2.5), capability_bounds([]))
    assert any(item.level == "danger" and item.field == "power_w" for item in issues)


def test_overtemp_close_to_start_is_warn():
    issues = validate_plan(_body(overtemp_c=30), capability_bounds([]))
    assert any(item.level == "warn" and item.field == "overtemp_c" for item in issues)


def test_duplicate_limit_and_ambient_order():
    issues = validate_plan(
        _body(
            ambient_low_c=30,
            ambient_high_c=20,
            limits=[
                {"item": "Temp_T0-T1", "low": 1, "high": 0, "unit": "℃", "skipped": False},
                {"item": "Temp_T0-T1", "low": 0, "high": 3, "unit": "℃", "skipped": False},
            ],
        ),
        capability_bounds([]),
    )
    fields = {item.field for item in issues if item.level == "danger"}
    assert "ambient_low_c" in fields
    assert "Temp_T0-T1" in fields
    assert "limits" in fields


def test_capability_uses_the_tightest_machine():
    bounds = capability_bounds(
        [
            {"capability": {"power_low_w": 0.5, "power_high_w": 5, "duration_low_s": 10, "duration_high_s": 300}},
            {"capability": {"power_low_w": 1, "power_high_w": 4, "duration_low_s": 30, "duration_high_s": 200}},
        ]
    )
    assert bounds["power_low_w"] == 1
    assert bounds["power_high_w"] == 4
    assert bounds["duration_low_s"] == 30
    assert bounds["duration_high_s"] == 200

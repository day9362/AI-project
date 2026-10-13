from models.dto.report import ReportOut
from service.report_rules import build_report


def _batch(batch_id: str, plan_id: str = "P1") -> dict:
    return {
        "batch_id": batch_id, "model": "tb172", "count": 10, "plan_id": plan_id, "plan_version": 1,
        "plan_name": "观察", "machine_ids": ["M01"], "started_at": 1, "ended_at": None, "state": "done", "eta_s": None,
    }


def _run(batch_id: str, passed: bool | None, rc: float | None = 5.0, item: str = "", machine: str = "M01") -> dict:
    return {
        "batch_id": batch_id, "machine_id": machine, "status": "COMPLETED" if passed is not None else "ABORTED",
        "passed": passed, "fail_items": [item] if item else [], "rc": rc, "dt01": 2.0 if passed else 3.2,
        "deltas": {"Temp_T1-T2": 1.1, "Temp_T1-T14": 3.0},
    }


LIMITS = {("P1", 1): [
    {"item": "Temp_T0-T1", "high": 2.8, "skipped": False},
    {"item": "Temp_T1-T2", "high": 4.0, "skipped": False},
    {"item": "Temp_T1-T14", "high": None, "skipped": True},
]}


def test_zero_runs_are_left_out_of_the_calculation():
    report = build_report([_batch("B-empty"), _batch("B-ok")], [_run("B-ok", True), _run("B-ok", False, item="power_w")], LIMITS)
    assert [row["batch_id"] for row in report["batches"]] == ["B-ok"]
    assert report["summary"]["tested"] == 2
    assert report["summary"]["yield_rate"] == 50
    assert report["fail_pareto"] == [{"item": "power_w", "count": 1}]


def test_single_batch_has_p95_and_cpk():
    runs = [_run("B-ok", True, rc=4.8), _run("B-ok", True, rc=5.2), _run("B-ok", False, rc=5.4, item="Temp_T0-T1")]
    report = build_report([_batch("B-ok")], runs, LIMITS)
    assert report["delta_profile"]["p95"]
    assert report["delta_profile"]["limit"][0] == 4.0
    assert report["delta_profile"]["limit"][1] is None
    assert report["summary"]["cpk_t01"] is not None
    assert report["summary"]["usl_t01"] == 2.8
    assert len(report["rc_histogram"]["edges"]) == 13


def test_merged_batches_omit_p95():
    runs = [_run("B-a", True, machine="M01"), _run("B-b", False, item="Temp_T1-T2", machine="M02")]
    report = build_report([_batch("B-a"), _batch("B-b")], runs, LIMITS)
    assert "p95" not in report["delta_profile"]
    assert "p95" not in ReportOut.model_validate(report).model_dump()["delta_profile"]
    assert {row["batch_id"] for row in report["compare"]} == {"B-a", "B-b"}
    assert report["machine_yield"][0]["machine_id"] == "M02"

from service.device_rules import compensation_channels, compensation_suggestion, drift_rows, ensure_online, plan_spans, sampling_run_ids


def test_disconnected_is_not_forwarded():
    assert ensure_online("DISCONNECTED") == "MACHINE_DISCONNECTED"
    assert ensure_online("ONLINE") is None


def test_sampling_runs_are_the_ones_aborted():
    slots = [{"phase": "SAMPLING", "run_id": "R-1"}, {"phase": "IDLE", "run_id": "R-0"}]
    assert sampling_run_ids(slots, ["R-2", "R-1"]) == ["R-2", "R-1"]


def test_plan_history_keeps_the_loaded_plan_open():
    spans = plan_spans([
        {"plan_id": "P1", "version": 1, "created_at": 10, "accepted": True, "name": "甲"},
        {"plan_id": "P1", "version": 1, "created_at": 20, "accepted": False, "name": "甲"},
        {"plan_id": "P2", "version": 4, "created_at": 30, "accepted": True, "name": "乙"},
    ], ("P2", 4), now=100)
    assert spans[0]["to"] == 30
    assert spans[1]["to"] is None
    assert spans[1]["name"] == "乙"


def test_suggestion_negates_the_measured_bias():
    result = compensation_suggestion([{"channel": "T1", "value": 0.182}, {"channel": "T2", "value": 0.001}], 100)
    assert result["basis_at"] == 100
    assert result["items"] == [{"channel": "T1", "value": -0.182, "reason": "标准样品复测偏差 +0.182 ℃"}]


def test_drift_rows_read_cluster_records():
    rows = drift_rows({"drifts": [{"id": "d1", "channel": "T1", "type": "FIXED", "value": 0.2, "current": 0.18}]})
    assert rows == [{"drift_id": "d1", "channel": "T1", "kind": "FIXED", "value": 0.2, "current": 0.18}]


def test_compensation_body_accepts_cluster_shapes():
    assert compensation_channels({"channels": [{"channel": "T1", "value": -0.2}]}) == [{"channel": "T1", "value": -0.2}]
    assert compensation_channels({"T1": -0.2, "Ta": 0.1}) == [{"channel": "T1", "value": -0.2}, {"channel": "Ta", "value": 0.1}]
    assert compensation_channels({}) == []

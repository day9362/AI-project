from models.entity.overview import AlarmEntity, RunEntity
from repo.alarm_repo import decode_cursor, encode_cursor
from service.overview.aggregate import aggregate_runs, yield_rate
from service.overview.rules import alarm_category, attribute, is_sentinel
from service.passwords import hash_password, verify_password


def test_password_roundtrip():
    stored = hash_password("changeme")
    assert verify_password("changeme", stored)
    assert not verify_password("wrong", stored)


def test_alarm_category_matches_overview_buckets():
    assert alarm_category("通信", "COMM_DISCONNECT") == "communication"
    assert alarm_category("数据", "SENSOR_99999") == "data"
    assert alarm_category("判定", "Temp_T0-T1") == "product"
    assert alarm_category("漂移", "EQUIPMENT_ANOMALY") == "equipment"
    assert is_sentinel(99999)
    assert is_sentinel(-1)
    assert not is_sentinel(24.2)


def test_attribution_does_not_invent_a_write_action():
    alarm = AlarmEntity("AL-1", 1, "major", "M07", "漂移", "EQUIPMENT_ANOMALY", "T1 漂移", False)
    result = attribute(alarm, 10)
    assert result.status == "done"
    assert result.category == "equipment"
    assert "补偿" in result.suggestion


def test_cursor_roundtrip():
    token = encode_cursor(1759834000000, "AL-10418")
    assert decode_cursor(token) == (1759834000000, "AL-10418")


def test_aggregate_fills_empty_buckets_and_skips_running():
    runs = [
        RunEntity("r1", "M01", 1, "s", "p", 1, "COMPLETED", True, [], True, 4.8, 2.1, "b", 300_000),
        RunEntity("r2", "M01", 1, "s", "p", 1, "COMPLETED", False, ["Temp_T0-T1"], True, 5.1, 3.2, "b", 320_000),
        RunEntity("r3", "M01", 1, "s", "p", 1, "RUNNING", None, [], True, None, None, "b", 310_000),
        RunEntity("r4", "M01", 1, "s", "p", 1, "ABORTED", None, [], False, None, None, "b", 600_000),
    ]
    rows = aggregate_runs(runs, 0, 600_000)
    assert [row.bucket for row in rows] == [0, 300_000, 600_000]
    assert rows[1].tests == 2 and rows[1].passed == 1 and rows[1].failed == 1
    assert rows[2].aborted == 1 and rows[2].tests == 1
    assert yield_rate(1, 2) == 50.0

from core.clock import now_ms
from core.config import settings
from models.entity.overview import AlarmEntity, BatchBrief, MachineEntity, PlanEntity, RunEntity, SlotEntity
from models.entity.user import UserEntity
from repo.alarm_repo import AlarmRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from repo.user_repo import UserRepo
from service.overview.stats_service import StatsService
from service.passwords import hash_password

CAPABILITY = {
    "temp_channels": ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "T13", "T14", "Ta", "T_air", "T_motor_up", "T_motor_down"],
    "force_channels": [f"F{i}" for i in range(1, 15)],
    "duration_low_s": 1,
    "duration_high_s": 600,
    "power_low_w": 0.1,
    "power_high_w": 10,
    "force_low_g": 20,
    "force_high_g": 300,
}
PHASES = ["RESETTING", "PREHEATING", "WAITING_LOAD", "CLAMPING", "SAMPLING", "RECOVERING"]
STATUS = [
    ("READY", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("FAULT", "ONLINE", "", "PLC_FAULT · PLC 无响应"),
    ("READY", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("MAINTENANCE", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("READY", "ONLINE", "", ""),
    ("READY", "DEGRADED", "丢包", ""),
    ("READY", "DISCONNECTED", "", ""),
]


async def seed_if_empty(session) -> None:
    users = UserRepo(session)
    if await users.by_username("limingyuan") is None:
        password = hash_password(settings.default_password)
        await users.add(UserEntity("usr_limingyuan", "limingyuan", "李明远", "test", password))
        await users.add(UserEntity("usr_admin", "admin", "管理员", "admin", password))

    machines = MachineRepo(session)
    if await machines.count():
        return

    now = now_ms()
    stats = StatsRepo(session)
    await stats.add_plan(PlanEntity("PLAN-592bbc46", 2, "45度测3分钟", 180, 2.5, 45, 23, 27, False))
    await stats.add_plan(PlanEntity("PLAN-3f2c71d0", 3, "HVP 3.5W 标准测试", 180, 3.5, 45, 23, 27, False))
    await stats.add_plan(PlanEntity("DRAFT-0001", 0, "高压紧力对比（草稿）", 180, 2.5, 45, 23, 27, True))
    await stats.add_batch(BatchBrief("B-tb172-seed", 600, 372, "running", "PLAN-592bbc46", 2), "tb172")
    await stats.add_batch(BatchBrief("B-tb158-seed", 400, 400, "done", "PLAN-592bbc46", 2), "tb158")

    for i, (status, comm, note, alarm) in enumerate(STATUS, start=1):
        mid = f"M{i:02d}"
        hvp = i in {9, 10}
        running = status == "READY" and comm != "DISCONNECTED"
        plan_id = None if status == "MAINTENANCE" else ("PLAN-3f2c71d0" if hvp else "PLAN-592bbc46")
        version = None if plan_id is None else (3 if hvp else 2)
        slots: list[SlotEntity] = []
        for k in range(10):
            phase = "IDLE"
            if running:
                phase = PHASES[k % len(PHASES)]
            if i == 3 and k == 6:
                phase = "ERROR"
            if i == 5 and k < 2:
                phase = "ERROR"
            ta = round(24 + i * 0.08, 2)
            sampling = phase == "SAMPLING"
            run_id = f"R-{mid}-{k + 1}-seed" if sampling else None
            slots.append(SlotEntity(
                index=k + 1,
                phase=phase,
                serial_number=None if phase in {"IDLE", "RESETTING", "PREHEATING"} else f"B-tb172-seed-{k + 1:04d}",
                tests_done=1800 + i * 20 + k,
                last_error="VACUUM_LEAK · 真空未到位（-44.8 kPa）" if phase == "ERROR" and i == 3 else ("PLC 无响应" if phase == "ERROR" else ""),
                power_w=2.5 if sampling else 0,
                vacuum_kpa=-85 if phase in {"WAITING_LOAD", "CLAMPING", "SAMPLING"} else -2,
                t0=43.2 if sampling else 45,
                t1=41.1 if sampling else ta + 0.4,
                ta=ta,
                progress=55 if sampling else 0,
                run_id=run_id,
            ))
            if run_id:
                await stats.upsert_run(RunEntity(
                    run_id=run_id, machine_id=mid, slot_index=k + 1, serial_number=f"B-tb172-seed-{k + 1:04d}",
                    plan_id=plan_id or "", plan_version=version or 0, status="RUNNING", passed=None,
                    fail_items=[], keep_result=True, rc=None, dt01=None, batch_id="B-tb172-seed", ended_at=now,
                ))
                await machines.add_samples(run_id, _curve(2.5 if not hvp else 3.5, ta))
        await machines.save_machine(MachineEntity(
            machine_id=mid, serial=f"X9610_{i}#", fixture=f"513000{i:02d}", holder=f"V01_00{10 + i * 3:02d}",
            thermal_boards=f"TM_BOX_V3_56F{i}001;TM_BOX_V3_56F{i}5001",
            plc="INOVANCE" if i % 2 else "OMRON", firmware="VC_BASE_BOX_V3", slot_count=10,
            status=status, comm_status=comm, comm_note=note, speed=1, room_temp_c=round(23.6 + i * 0.11, 2),
            alarm=alarm, plan_id=plan_id, plan_version=version, capability=CAPABILITY, last_sync_at=now, slots=slots,
        ))
        await machines.replace_slots(mid, slots)

    await machines.add_bias("M07", "T1", 0.182, now - 3600_000)
    await machines.add_bias("M07", "Ta", 0.052, now - 3600_000)

    for i in range(240):
        n = (i % 11) + 1
        mid = f"M{n:02d}"
        passed = i % 37 != 0
        await stats.upsert_run(RunEntity(
            run_id=f"R-{mid}-hist-{i:04d}",
            machine_id=mid,
            slot_index=(i % 10) + 1,
            serial_number=f"B-tb172-seed-{i:04d}",
            plan_id="PLAN-3f2c71d0" if n in {9, 10} else "PLAN-592bbc46",
            plan_version=3 if n in {9, 10} else 2,
            status="COMPLETED",
            passed=passed,
            fail_items=[] if passed else ["Temp_T0-T1"],
            keep_result=True,
            rc=round(5.18 if n in {9, 10} else 4.77 + (0.09 if n == 7 else 0), 3),
            dt01=round(2.07 if passed else 3.05, 3),
            batch_id="B-tb172-seed",
            ended_at=now - i * 4 * 60_000,
        ))

    alarms = AlarmRepo(session)
    for item in _seed_alarms(now):
        await alarms.add(item)
    await StatsService(stats, machines, alarms).rebuild_recent(16)


def _curve(power: float, ta: float) -> list[tuple[float, float, float, float, float]]:
    points = []
    for t_s in range(0, 60, 10):
        k = 1 - pow(2.718, -t_s / 28)
        t1 = ta + 4.77 * power * k
        t0 = t1 + 2.07 * (0.4 + 0.6 * k)
        points.append((float(t_s), round(t0, 2), round(t1, 2), ta, power))
    return points


def _seed_alarms(now: int) -> list[AlarmEntity]:
    rows = [
        ("AL-10421", 3, "critical", "M05", None, "机台", "PLC_FAULT", "PLC 无响应，机台进入 FAULT，槽位 1、2 进入 ERROR", False),
        ("AL-10420", 7, "critical", "M12", None, "通信", "COMM_DISCONNECT", "通信断开（DISCONNECTED），状态查询与指令下发均返回 503", False),
        ("AL-10419", 9, "major", "M03", 7, "槽位", "VACUUM_LEAK", "真空未到位：-44.8 kPa（吸附阈值 -60 kPa），槽位进入 ERROR", False),
        ("AL-10418", 15, "major", "M07", None, "漂移", "EQUIPMENT_ANOMALY", "T1 通道估计漂移 +0.18 ℃，超过 0.15 ℃ 设备异常阈值", False),
        ("AL-10417", 22, "minor", "M11", None, "通信", "PACKET_LOSS", "通信降级（DEGRADED · 丢包），近 5 分钟采样缺行 3.2%", True),
        ("AL-10416", 31, "minor", "M02", 4, "数据", "SENSOR_99999", "T9 读数 99999（接触不良哨兵值），本次判定为不合格", True),
        ("AL-10415", 48, "major", "M04", None, "判定", "Temp_T0-T1", "连续 3 片 Temp_T0-T1 超上限 2.8 ℃", True),
        ("AL-10414", 70, "minor", "M06", None, "机台", "AMBIENT_EXCURSION", "房间温度 27.3 ℃ 超出方案范围 23–27 ℃", True),
    ]
    out = []
    for alarm_id, minutes, level, machine_id, slot, source, code, message, acked in rows:
        out.append(AlarmEntity(
            id=alarm_id, time=now - minutes * 60_000, level=level, machine_id=machine_id, slot_index=slot,
            source=source, code=code, message=message, acked=acked,
            acked_by="李明远" if acked else None, acked_at=now - minutes * 60_000 + 60_000 if acked else None,
        ))
    return out

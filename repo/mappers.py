from models.entity.overview import (
    AggEntity,
    AlarmEntity,
    AttributionEntity,
    BatchBrief,
    MachineEntity,
    PlanEntity,
    RunEntity,
    SlotEntity,
    YieldRecent,
)
from models.entity.user import UserEntity
from models.orm.alarm import AlarmAttributionOrm, AlarmOrm
from models.orm.machine import MachineOrm, SlotOrm
from models.orm.stats import Agg5mOrm, BatchStatOrm, PlanOrm, RunOrm
from models.orm.user import UserOrm


def user_entity(row: UserOrm) -> UserEntity:
    return UserEntity(row.user_id, row.username, row.name, row.role, row.password_hash)


def slot_entity(row: SlotOrm) -> SlotEntity:
    return SlotEntity(
        index=row.index,
        phase=row.phase,
        serial_number=row.serial_number,
        tests_done=row.tests_done,
        last_error=row.last_error,
        power_w=row.power_w,
        vacuum_kpa=row.vacuum_kpa,
        t0=row.t0,
        t1=row.t1,
        ta=row.ta,
        progress=row.progress,
        run_id=row.run_id,
    )


def machine_entity(row: MachineOrm, slots: list[SlotOrm], yield_recent: YieldRecent | None = None) -> MachineEntity:
    return MachineEntity(
        machine_id=row.machine_id,
        serial=row.serial,
        fixture=row.fixture,
        holder=row.holder,
        thermal_boards=row.thermal_boards,
        plc=row.plc,
        firmware=row.firmware,
        slot_count=row.slot_count,
        status=row.status,
        comm_status=row.comm_status,
        comm_note=row.comm_note,
        speed=row.speed,
        room_temp_c=row.room_temp_c,
        alarm=row.alarm,
        plan_id=row.plan_id,
        plan_version=row.plan_version,
        capability=row.capability or {},
        slots=[slot_entity(s) for s in slots],
        last_sync_at=row.last_sync_at,
        yield_recent=yield_recent or YieldRecent(0, 0),
    )


def run_entity(row: RunOrm) -> RunEntity:
    return RunEntity(
        run_id=row.run_id,
        machine_id=row.machine_id,
        slot_index=row.slot_index,
        serial_number=row.serial_number,
        plan_id=row.plan_id,
        plan_version=row.plan_version,
        status=row.status,
        passed=row.passed,
        fail_items=list(row.fail_items or []),
        keep_result=row.keep_result,
        rc=row.rc,
        dt01=row.dt01,
        batch_id=row.batch_id,
        ended_at=row.ended_at,
    )


def agg_entity(row: Agg5mOrm) -> AggEntity:
    return AggEntity(row.bucket, row.tests, row.passed, row.failed, row.aborted, row.rc_mean, row.dt01_mean)


def alarm_entity(row: AlarmOrm) -> AlarmEntity:
    return AlarmEntity(
        id=row.id,
        time=row.time,
        level=row.level,
        machine_id=row.machine_id,
        source=row.source,
        code=row.code,
        message=row.message,
        acked=row.acked,
        slot_index=row.slot_index,
        acked_by=row.acked_by,
        acked_at=row.acked_at,
    )


def attribution_entity(row: AlarmAttributionOrm) -> AttributionEntity:
    return AttributionEntity(
        alarm_id=row.alarm_id,
        status=row.status,
        category=row.category,
        confidence=row.confidence,
        summary=row.summary,
        evidence=list(row.evidence or []),
        suggestion=row.suggestion,
        model=row.model,
        created_at=row.created_at,
    )


def plan_entity(row: PlanOrm) -> PlanEntity:
    return PlanEntity(
        row.plan_id, row.version, row.name, row.duration_s, row.power_w,
        row.start_temp_c, row.ambient_low_c, row.ambient_high_c, row.draft,
    )


def batch_brief(row: BatchStatOrm) -> BatchBrief:
    return BatchBrief(row.batch_id, row.count, row.tested, row.state, row.plan_id, row.plan_version)

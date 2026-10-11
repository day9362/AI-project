import base64

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entity.overview import AlarmEntity, AttributionEntity
from models.orm.alarm import AlarmAttributionOrm, AlarmOrm
from repo.mappers import alarm_entity, attribution_entity


def encode_cursor(time_ms: int, alarm_id: str) -> str:
    raw = f"{time_ms}|{alarm_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, str]:
    pad = "=" * (-len(cursor) % 4)
    time_ms, alarm_id = base64.urlsafe_b64decode(cursor + pad).decode().split("|", 1)
    return int(time_ms), alarm_id


class AlarmRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def page(
        self,
        *,
        acked: bool | None,
        machine_id: str | None,
        level: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[AlarmEntity], str | None]:
        stmt = select(AlarmOrm).order_by(AlarmOrm.time.desc(), AlarmOrm.id.desc()).limit(limit + 1)
        if acked is not None:
            stmt = stmt.where(AlarmOrm.acked == acked)
        if machine_id:
            stmt = stmt.where(AlarmOrm.machine_id == machine_id)
        if level:
            stmt = stmt.where(AlarmOrm.level == level)
        if cursor:
            time_ms, alarm_id = decode_cursor(cursor)
            stmt = stmt.where(
                (AlarmOrm.time < time_ms) | ((AlarmOrm.time == time_ms) & (AlarmOrm.id < alarm_id))
            )
        rows = list(await self.session.scalars(stmt))
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = encode_cursor(last.time, last.id)
            rows = rows[:limit]
        return [alarm_entity(row) for row in rows], next_cursor

    async def get(self, alarm_id: str) -> AlarmEntity | None:
        row = await self.session.get(AlarmOrm, alarm_id)
        return alarm_entity(row) if row else None

    async def open_alarms(self) -> list[AlarmEntity]:
        rows = await self.session.scalars(select(AlarmOrm).where(AlarmOrm.acked.is_(False)))
        return [alarm_entity(row) for row in rows]

    async def between(self, start_ms: int, end_ms: int) -> list[AlarmEntity]:
        rows = await self.session.scalars(
            select(AlarmOrm).where(AlarmOrm.time >= start_ms, AlarmOrm.time < end_ms).order_by(AlarmOrm.time)
        )
        return [alarm_entity(row) for row in rows]

    async def add(self, alarm: AlarmEntity) -> None:
        self.session.add(AlarmOrm(
            id=alarm.id, time=alarm.time, level=alarm.level, machine_id=alarm.machine_id,
            slot_index=alarm.slot_index, source=alarm.source, code=alarm.code, message=alarm.message,
            acked=alarm.acked, acked_by=alarm.acked_by, acked_at=alarm.acked_at,
        ))

    async def remove(self, alarm_id: str) -> None:
        await self.session.execute(delete(AlarmOrm).where(AlarmOrm.id == alarm_id))

    async def save_ack(self, alarm: AlarmEntity) -> None:
        row = await self.session.get(AlarmOrm, alarm.id)
        if row is None:
            return
        row.acked = alarm.acked
        row.acked_by = alarm.acked_by
        row.acked_at = alarm.acked_at

    async def next_seq(self) -> int:
        row = await self.session.scalar(select(AlarmOrm.id).order_by(AlarmOrm.id.desc()).limit(1))
        if not row or not str(row).startswith("AL-"):
            return 10422
        try:
            return int(str(row).split("-", 1)[1]) + 1
        except ValueError:
            return 10422

    async def attribution(self, alarm_id: str) -> AttributionEntity | None:
        row = await self.session.get(AlarmAttributionOrm, alarm_id)
        return attribution_entity(row) if row else None

    async def save_attribution(self, item: AttributionEntity) -> None:
        row = await self.session.get(AlarmAttributionOrm, item.alarm_id)
        values = dict(
            status=item.status, category=item.category, confidence=item.confidence, summary=item.summary,
            evidence=item.evidence, suggestion=item.suggestion, model=item.model, created_at=item.created_at,
        )
        if row is None:
            self.session.add(AlarmAttributionOrm(alarm_id=item.alarm_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)

    async def attributions_for(self, alarm_ids: list[str]) -> dict[str, AttributionEntity]:
        if not alarm_ids:
            return {}
        rows = await self.session.scalars(select(AlarmAttributionOrm).where(AlarmAttributionOrm.alarm_id.in_(alarm_ids)))
        return {row.alarm_id: attribution_entity(row) for row in rows}

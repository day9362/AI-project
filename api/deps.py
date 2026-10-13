from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionLocal
from core.errors import ApiError
from models.entity.user import UserEntity
from repo.alarm_repo import AlarmRepo
from repo.audit_repo import AuditRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from repo.user_repo import UserRepo
from service.auth_service import AuthService, resolve_session
from service.overview.alarm_service import AlarmService
from service.overview.machine_service import MachineService
from service.overview.stats_service import StatsService
from service.plan_service import PlanService
from service.device_service import DeviceService
from service.production_service import ProductionService
from service.report_service import ReportService
from service.settings_service import SettingsService


async def db_session():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "未登录")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "未登录")
    return token


async def current_user(token: Annotated[str, Depends(bearer_token)]) -> UserEntity:
    user = await resolve_session(token)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "登录已失效")
    return user


def auth_service(session: Annotated[AsyncSession, Depends(db_session)]) -> AuthService:
    return AuthService(UserRepo(session), AuditRepo(session))


def machine_service(session: Annotated[AsyncSession, Depends(db_session)]) -> MachineService:
    return MachineService(MachineRepo(session), StatsRepo(session))


def stats_service(session: Annotated[AsyncSession, Depends(db_session)]) -> StatsService:
    return StatsService(StatsRepo(session), MachineRepo(session), AlarmRepo(session))


def alarm_service(session: Annotated[AsyncSession, Depends(db_session)]) -> AlarmService:
    return AlarmService(AlarmRepo(session), MachineRepo(session), StatsRepo(session), AuditRepo(session))


def production_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    user: Annotated[UserEntity, Depends(current_user)],
) -> ProductionService:
    return ProductionService(session, user)


def device_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    user: Annotated[UserEntity, Depends(current_user)],
) -> DeviceService:
    return DeviceService(session, user)


def report_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: Annotated[UserEntity, Depends(current_user)],
) -> ReportService:
    return ReportService(session)


def settings_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    user: Annotated[UserEntity, Depends(current_user)],
) -> SettingsService:
    return SettingsService(session, user)


def plan_service(
    session: Annotated[AsyncSession, Depends(db_session)],
    user: Annotated[UserEntity, Depends(current_user)],
) -> PlanService:
    return PlanService(session, user)

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionLocal
from core.errors import ApiError
from models.entity.user import UserEntity
from repo.alarm_repo import AlarmRepo
from repo.job_repo import JobRepo
from repo.machine_repo import MachineRepo
from repo.stats_repo import StatsRepo
from repo.user_repo import UserRepo
from service.auth_service import AuthService
from service.overview.alarm_service import AlarmService
from service.overview.machine_service import MachineService
from service.overview.stats_service import StatsService


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


async def current_user(token: Annotated[str, Depends(bearer_token)], session: Annotated[AsyncSession, Depends(db_session)]) -> UserEntity:
    user = await AuthService(UserRepo(session)).resolve(token)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "登录已失效")
    return user


def machine_service(session: Annotated[AsyncSession, Depends(db_session)]) -> MachineService:
    return MachineService(MachineRepo(session), StatsRepo(session))


def stats_service(session: Annotated[AsyncSession, Depends(db_session)]) -> StatsService:
    return StatsService(StatsRepo(session), MachineRepo(session), AlarmRepo(session))


def alarm_service(session: Annotated[AsyncSession, Depends(db_session)]) -> AlarmService:
    return AlarmService(AlarmRepo(session), MachineRepo(session), StatsRepo(session), JobRepo(session))


def auth_service(session: Annotated[AsyncSession, Depends(db_session)]) -> AuthService:
    return AuthService(UserRepo(session))

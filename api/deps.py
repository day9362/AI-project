from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionLocal
from core.errors import ApiError
from models.entity.user import UserEntity
from repo.audit_repo import AuditRepo
from repo.user_repo import UserRepo
from service.auth_service import AuthService, resolve_session


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

import secrets
import time

import jwt

from core.config import settings
from core.errors import ApiError
from core.redis import redis
from models.dto.auth import LoginOut, UserOut
from models.entity.user import UserEntity
from repo.audit_repo import AuditRepo
from repo.user_repo import UserRepo
from service.passwords import verify_password

_SESSION = "auth:session:{jti}"
_USER = "auth:user:{user_id}"


class AuthService:
    def __init__(self, users: UserRepo, audits: AuditRepo):
        self.users = users
        self.audits = audits

    async def login(self, username: str, password: str) -> LoginOut:
        user = await self.users.by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise ApiError(401, "UNAUTHORIZED", "用户名或密码错误")
        previous = await redis.get(_USER.format(user_id=user.user_id))
        if previous:
            await redis.delete(_SESSION.format(jti=previous))
        jti = secrets.token_urlsafe(16)
        token = _issue(user, jti)
        ttl = settings.session_ttl_seconds
        await redis.set(_SESSION.format(jti=jti), user.user_id, ex=ttl)
        await redis.set(_USER.format(user_id=user.user_id), jti, ex=ttl)
        await self.audits.write(user.name, "auth.login", {"username": username})
        return LoginOut(token=token, user=UserOut(user_id=user.user_id, name=user.name, role=user.role))

    async def logout(self, token: str) -> None:
        user, jti = await _open(token)
        if user is None or jti is None:
            raise ApiError(401, "UNAUTHORIZED", "登录已失效")
        await redis.delete(_SESSION.format(jti=jti))
        current = await redis.get(_USER.format(user_id=user.user_id))
        if current == jti:
            await redis.delete(_USER.format(user_id=user.user_id))
        await self.audits.write(user.name, "auth.logout", {"username": user.username})


def _issue(user: UserEntity, jti: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "jti": jti,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token if isinstance(token, str) else token.decode()


async def resolve_session(token: str) -> UserEntity | None:
    user, _ = await _open(token)
    return user


async def _open(token: str) -> tuple[UserEntity | None, str | None]:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None, None
    user_id = data.get("sub")
    jti = data.get("jti")
    name = data.get("name")
    role = data.get("role")
    if not user_id or not jti or not name or not role:
        return None, None
    if await redis.get(_USER.format(user_id=user_id)) != jti:
        return None, None
    if await redis.get(_SESSION.format(jti=jti)) != user_id:
        return None, None
    return UserEntity(user_id, data.get("username") or "", name, role), jti

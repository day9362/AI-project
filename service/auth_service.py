import json
import secrets

from core.config import settings
from core.errors import ApiError
from core.redis import redis
from models.dto.auth import LoginOut, UserOut
from models.entity.user import UserEntity
from repo.user_repo import UserRepo
from service.passwords import verify_password

_SESSION = "auth:session:{token}"
_USER = "auth:user:{user_id}"


class AuthService:
    def __init__(self, users: UserRepo):
        self.users = users

    async def login(self, username: str, password: str) -> LoginOut:
        user = await self.users.by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise ApiError(401, "UNAUTHORIZED", "用户名或密码错误")
        previous = await redis.get(_USER.format(user_id=user.user_id))
        if previous:
            await redis.delete(_SESSION.format(token=previous))
        token = secrets.token_urlsafe(32)
        payload = json.dumps({"user_id": user.user_id, "name": user.name, "role": user.role, "username": user.username})
        await redis.set(_SESSION.format(token=token), payload, ex=settings.session_ttl_seconds)
        await redis.set(_USER.format(user_id=user.user_id), token, ex=settings.session_ttl_seconds)
        return LoginOut(token=token, user=UserOut(user_id=user.user_id, name=user.name, role=user.role))

    async def logout(self, token: str) -> None:
        raw = await redis.get(_SESSION.format(token=token))
        await redis.delete(_SESSION.format(token=token))
        if raw:
            user_id = json.loads(raw)["user_id"]
            current = await redis.get(_USER.format(user_id=user_id))
            if current == token:
                await redis.delete(_USER.format(user_id=user_id))

    async def resolve(self, token: str) -> UserEntity | None:
        return await resolve_session(token)


async def resolve_session(token: str) -> UserEntity | None:
    raw = await redis.get(_SESSION.format(token=token))
    if not raw:
        return None
    data = json.loads(raw)
    return UserEntity(data["user_id"], data.get("username", ""), data["name"], data["role"])

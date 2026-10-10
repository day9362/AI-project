from core.config import settings
from models.entity.user import UserEntity
from repo.user_repo import UserRepo
from service.passwords import hash_password


async def seed_if_empty(session) -> None:
    users = UserRepo(session)
    if await users.by_username("limingyuan") is not None:
        return
    password = hash_password(settings.default_password)
    await users.add(UserEntity("usr_limingyuan", "limingyuan", "李明远", "test", password))
    await users.add(UserEntity("usr_admin", "admin", "管理员", "admin", password))

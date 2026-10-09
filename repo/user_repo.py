from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.entity.user import UserEntity
from models.orm.user import UserOrm
from repo.mappers import user_entity


class UserRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_username(self, username: str) -> UserEntity | None:
        row = await self.session.scalar(select(UserOrm).where(UserOrm.username == username))
        return user_entity(row) if row else None

    async def add(self, user: UserEntity) -> None:
        self.session.add(UserOrm(
            user_id=user.user_id,
            username=user.username,
            name=user.name,
            password_hash=user.password_hash,
            role=user.role,
        ))

from fastapi import APIRouter
from sqlalchemy import text

from api.auth import router as auth_router
from core.db import engine
from core.redis import redis

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)


@api_router.get("/health")
async def health() -> dict:
    await redis.ping()
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"ok": True}

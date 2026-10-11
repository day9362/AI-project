from fastapi import APIRouter
from sqlalchemy import text

from api.auth import router as auth_router
from api.overview.alarms import router as alarms_router
from api.overview.machines import router as machines_router
from api.overview.stats import router as stats_router
from api.overview.ws import router as ws_router
from core.db import engine
from core.redis import redis

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(machines_router)
api_router.include_router(stats_router)
api_router.include_router(alarms_router)
api_router.include_router(ws_router)


@api_router.get("/health")
async def health() -> dict:
    await redis.ping()
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"ok": True}

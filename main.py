import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models.orm  # noqa: F401  注册 ORM，供 create_all 使用
from api.errors import install_handlers
from api.router import api_router
from core.db import SessionLocal, engine
from core.redis import redis
from models.orm.base import Base
from service.seed import seed_if_empty
from tasks.scheduler import start_scheduler, stop_scheduler
from tasks.triggers import trigger_bus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis.ping()
    async with SessionLocal() as session:
        await seed_if_empty(session)
        await session.commit()
    await trigger_bus.start()
    start_scheduler()
    yield
    stop_scheduler()
    await trigger_bus.stop()
    await redis.aclose()
    await engine.dispose()


app = FastAPI(title="VC-TestOS", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_handlers(app)
app.include_router(api_router)

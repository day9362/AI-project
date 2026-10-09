from fastapi import APIRouter

# 测试方案接口按 docs/backend-api.md 第 5 节后续接入。
router = APIRouter(prefix="/plans", tags=["test_plan"])

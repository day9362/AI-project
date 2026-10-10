from redis.asyncio import Redis

from core.config import settings

# 本机 Redis 5.0 不支持 RESP3 的 HELLO，固定用协议 2。
redis = Redis.from_url(settings.redis_url, decode_responses=True, protocol=2)

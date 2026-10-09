import logging

from fastapi import WebSocket

from core.clock import now_ms

log = logging.getLogger(__name__)


class RealtimeHub:
    """运行总览的 WebSocket 订阅。只推变化，不补历史。"""

    def __init__(self) -> None:
        self._topics: dict[WebSocket, set[str]] = {}

    async def register(self, ws: WebSocket) -> None:
        self._topics[ws] = set()

    def subscribe(self, ws: WebSocket, topics: list[str]) -> None:
        self._topics[ws] = set(topics)

    async def unregister(self, ws: WebSocket) -> None:
        self._topics.pop(ws, None)

    async def publish(self, topic: str, data) -> None:
        payload = {"topic": topic, "ts": now_ms(), "data": data}
        dead: list[WebSocket] = []
        for ws, topics in self._topics.items():
            if topic not in topics:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._topics.pop(ws, None)


hub = RealtimeHub()

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from service.auth_service import resolve_session
from service.realtime import hub

log = logging.getLogger(__name__)
router = APIRouter(tags=["overview"])


@router.websocket("/ws")
async def overview_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    token = _token(websocket)
    if not token or await resolve_session(token) is None:
        await websocket.close(code=4401)
        return
    await hub.register(websocket)
    ping = asyncio.create_task(_ping(websocket))
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("op") == "subscribe":
                topics = message.get("topics") or []
                hub.subscribe(websocket, [str(item) for item in topics])
    except WebSocketDisconnect:
        pass
    finally:
        ping.cancel()
        await hub.unregister(websocket)


def _token(websocket: WebSocket) -> str:
    header = websocket.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return websocket.query_params.get("token", "")


async def _ping(websocket: WebSocket) -> None:
    try:
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"topic": "ping"})
    except Exception:
        log.debug("ws ping stopped")

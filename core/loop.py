"""Windows 上 psycopg 异步模式不能跑在 ProactorEventLoop 里。

Uvicorn 0.36 起在 Windows 默认返回 ProactorEventLoop，且忽略
set_event_loop_policy。启动时指定：

    python -m uvicorn main:app --port 8000 --loop core.loop:selector_loop
"""

import asyncio
import selectors


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())

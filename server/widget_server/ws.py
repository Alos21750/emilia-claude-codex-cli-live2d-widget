import asyncio
from typing import Any

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock = asyncio.Lock()

    async def register_ws_client(self, ws: WebSocket) -> None:
        async with self._clients_lock:
            self._clients.add(ws)

    async def unregister_ws_client(self, ws: WebSocket) -> None:
        async with self._clients_lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def count(self) -> int:
        async with self._clients_lock:
            return len(self._clients)

    async def close_all(self) -> None:
        async with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
        for ws in clients:
            try:
                await ws.close()
            except Exception:
                pass

    async def broadcast(self, event: dict[str, Any]) -> None:
        async with self._clients_lock:
            clients = list(self._clients)
        if not clients:
            return

        stale: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._clients_lock:
                for ws in stale:
                    if ws in self._clients:
                        self._clients.remove(ws)

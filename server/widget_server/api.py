import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .monitor import SessionBridgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session-bridge", tags=["session-bridge"])

bridge_service = SessionBridgeService()


@router.get("/health")
async def bridge_health() -> dict[str, Any]:
    return await bridge_service.get_health()


@router.get("/snapshot")
async def bridge_snapshot() -> dict[str, Any]:
    return await bridge_service.get_snapshot()


@router.get("/history")
async def bridge_history(limit: int = 20) -> dict[str, Any]:
    return await bridge_service.get_history(limit)


@router.get("/claude-usage")
async def bridge_claude_usage() -> dict[str, Any]:
    """Return Claude Code usage / rate-limit data from Anthropic API."""
    from .claude_usage import fetch_claude_usage, format_usage_summary

    raw = await fetch_claude_usage()
    if raw is None:
        raise HTTPException(status_code=502, detail="Unable to fetch Claude usage (no token or API error)")
    return format_usage_summary(raw)


@router.websocket("/ws")
async def bridge_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await bridge_service.register_ws_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Session bridge websocket failed")
    finally:
        await bridge_service.unregister_ws_client(websocket)


async def start_session_bridge() -> None:
    await bridge_service.start()


async def stop_session_bridge() -> None:
    await bridge_service.stop()

import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .monitor import SessionBridgeService

logger = logging.getLogger(__name__)

router = APIRouter()
session_router = APIRouter(prefix="/api/session-bridge", tags=["session-bridge"])
widget_router = APIRouter(prefix="/api/widget", tags=["widget"])

bridge_service = SessionBridgeService()

MODEL_DISPLAY_NAMES = {
    "hiyori": "Hiyori (Live2D sample)",
    "ac_base_emilia01": "Emilia (default)",
    "ac_base_emilia02": "Emilia 02",
    "ac_base_emilia_dress01": "Emilia (Dress)",
    "ac_base_emilia_hood01": "Emilia (Hood)",
    "ac_base_emilia_mizugi01": "Emilia (Swimsuit)",
    "ac_base_emilia_nemaki01": "Emilia (Sleepwear 1)",
    "ac_base_emilia_nemaki02": "Emilia (Sleepwear 2)",
    "ac_base_emilia_nemaki03": "Emilia (Sleepwear 3)",
    "ac_base_emilia_wedding01": "Emilia (Wedding)",
    "ac_base_emilia_xmas01": "Emilia (Christmas)",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _models_root() -> Path:
    return _repo_root() / "frontend" / "public" / "assets" / "models"


def _public_root() -> Path:
    return _repo_root() / "frontend" / "public"


def _fallback_display_name(key: str) -> str:
    words = [part for part in re.split(r"[_\-\s]+", key) if part]
    if not words:
        return key
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _display_name(key: str) -> str:
    return MODEL_DISPLAY_NAMES.get(key, _fallback_display_name(key))


@session_router.get("/health")
async def bridge_health() -> dict[str, Any]:
    return await bridge_service.get_health()


@session_router.get("/snapshot")
async def bridge_snapshot() -> dict[str, Any]:
    return await bridge_service.get_snapshot()


@session_router.get("/history")
async def bridge_history(limit: int = 20) -> dict[str, Any]:
    return await bridge_service.get_history(limit)


@session_router.get("/claude-usage")
async def bridge_claude_usage() -> dict[str, Any]:
    """Return Claude Code usage / rate-limit data from Anthropic API."""
    from .claude_usage import fetch_claude_usage, format_usage_summary

    raw = await fetch_claude_usage()
    if raw is None:
        raise HTTPException(status_code=502, detail="Unable to fetch Claude usage (no token or API error)")
    return format_usage_summary(raw)


@session_router.websocket("/ws")
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


@widget_router.get("/models")
async def widget_models() -> list[dict[str, str]]:
    models_root = _models_root()
    public_root = _public_root()
    if not models_root.exists():
        return []

    discovered: dict[str, dict[str, str]] = {}
    for model_file in sorted(models_root.rglob("*.model3.json")):
        if not model_file.is_file():
            continue
        key = model_file.parent.name
        if key in discovered:
            continue
        model_path = model_file.relative_to(public_root).as_posix()
        discovered[key] = {
            "key": key,
            "modelPath": model_path,
            "displayName": _display_name(key),
        }

    def sort_key(item: dict[str, str]) -> tuple[int, str]:
        return (0 if item["key"].lower() == "hiyori" else 1, item["displayName"].lower())

    return sorted(discovered.values(), key=sort_key)


async def start_session_bridge() -> None:
    await bridge_service.start()


async def stop_session_bridge() -> None:
    await bridge_service.stop()


router.include_router(session_router)
router.include_router(widget_router)

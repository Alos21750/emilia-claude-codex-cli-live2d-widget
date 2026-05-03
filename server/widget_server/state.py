import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SESSION_STATES = {"IDLE", "THINKING", "TOOLING", "RESPONDING", "WAITING"}
STATE_PRIORITY = {"IDLE": 0, "RESPONDING": 1, "THINKING": 2, "TOOLING": 3, "WAITING": 4}
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
WHITESPACE_PATTERN = re.compile(r"\s+")
PERMISSION_MODE_DEFAULT = "default"
PERMISSION_MODE_AUTO = "auto"
PERMISSION_MODE_PLAN = "plan"
PERMISSION_MODE_FULL = "full"

AGENT_BRAND_CODEX = "codex"
AGENT_BRAND_CLAUDE = "claude"
SUPPORTED_AGENT_BRANDS = {AGENT_BRAND_CODEX, AGENT_BRAND_CLAUDE}

_CLAUDE_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "sonnet": 1_000_000,
    "opus": 1_000_000,
    "haiku": 200_000,
    "claude-opus-4-7": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-opus-4-6": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
}

_AUTO_INJECTED_USER_PROMPTS = {
    "initialize a new codex session. reply with: session_ready",
    "initialize a new session. reply with: session_ready",
    "please produce a detailed implementation plan before any code edits.",
    "tool loaded.",
    "tool loaded",
}
_AUTO_INJECTED_ASSISTANT_MESSAGES = {
    "session_ready",
    "tool loaded.",
    "tool loaded",
}
_AUTO_INJECTED_MESSAGE_PREFIXES = (
    "# agents.md instructions for ",
    "warning: apply_patch was requested via",
)
SESSION_BRIDGE_PROMPT_SCHEMA = "session_bridge_user_input_v1"


def _claude_model_context_window(model: str) -> int:
    """Return known context window size for a Claude model, or 200000 as default."""
    normalized = (model or "").strip().lower()
    if not normalized:
        return 0
    if normalized in _CLAUDE_MODEL_CONTEXT_WINDOWS:
        return _CLAUDE_MODEL_CONTEXT_WINDOWS[normalized]
    for key, window in _CLAUDE_MODEL_CONTEXT_WINDOWS.items():
        if key in normalized or normalized in key:
            return window
    if normalized in ("haiku",) or "haiku" in normalized:
        return 200_000
    if "claude" in normalized or normalized in ("sonnet", "opus"):
        return 1_000_000
    return 0


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_ts(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    try:
        normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
        datetime.fromisoformat(normalized)
        return candidate
    except ValueError:
        return ""


def _ts_to_epoch(value: str) -> float:
    candidate = (value or "").strip()
    if not candidate:
        return 0.0
    try:
        normalized = candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return 0.0


def _extract_message_content(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            candidate = item.get("text")
            if not isinstance(candidate, str) or not candidate.strip():
                candidate = item.get("content")
            if isinstance(candidate, str) and candidate.strip():
                chunks.append(candidate.strip())
        return " ".join(chunks).strip()
    message = payload.get("message")
    if isinstance(message, str):
        return message.strip()
    return ""


def _normalize_message_for_compare(text: str) -> str:
    normalized = WHITESPACE_PATTERN.sub(" ", str(text or "")).strip().lower()
    return normalized


def _normalize_persona_value(value: Any) -> str:
    return str(value or "").strip()


def _normalize_persona_payload(value: Any) -> Optional[dict[str, str]]:
    if not isinstance(value, dict):
        return None
    persona_id = _normalize_persona_value(value.get("id"))
    persona_name = _normalize_persona_value(value.get("name"))
    persona_content = str(value.get("content") or "")
    if not persona_id and not persona_name and not persona_content.strip():
        return None
    return {
        "id": persona_id,
        "name": persona_name,
        "content": persona_content,
    }


def _parse_session_bridge_prompt(content: Any) -> Optional[dict[str, Any]]:
    if not isinstance(content, str):
        return None
    candidate = content.strip()
    if not candidate.startswith("{"):
        return None
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("schema") or "").strip() != SESSION_BRIDGE_PROMPT_SCHEMA:
        return None
    user_input = payload.get("user_input")
    if not isinstance(user_input, str):
        return None
    personality = _normalize_persona_payload(payload.get("personality"))
    return {
        "user_input": user_input,
        "personality": personality,
        "plan_mode": bool(payload.get("plan_mode")),
    }


def _extract_visible_user_input(content: Any) -> str:
    parsed = _parse_session_bridge_prompt(content)
    if parsed is not None:
        return str(parsed.get("user_input") or "").strip()
    return str(content or "").strip()


def _extract_prompt_persona(content: Any) -> Optional[dict[str, str]]:
    parsed = _parse_session_bridge_prompt(content)
    if parsed is None:
        return None
    personality = parsed.get("personality")
    return personality if isinstance(personality, dict) else None


def _is_auto_injected_message(role: str, content: str) -> bool:
    normalized_role = str(role or "").strip().lower()
    normalized_content = _normalize_message_for_compare(content)
    if not normalized_content:
        return False
    for prefix in _AUTO_INJECTED_MESSAGE_PREFIXES:
        if normalized_content.startswith(prefix):
            return True
    if normalized_role == "user":
        return normalized_content in _AUTO_INJECTED_USER_PROMPTS
    if normalized_role == "assistant":
        return normalized_content in _AUTO_INJECTED_ASSISTANT_MESSAGES
    return False


def _basename_from_cwd(cwd: str) -> str:
    value = (cwd or "").strip()
    if not value:
        return ""
    return Path(value).name or value


def _normalize_permission_mode(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "full",
        "complete",
        "full-access",
        "danger",
        "danger-full-access",
        "dangerously-bypass-approvals-and-sandbox",
    }:
        return PERMISSION_MODE_FULL
    if normalized in {"auto", "auto-mode"}:
        return PERMISSION_MODE_AUTO
    if normalized in {"plan", "plan-mode"}:
        return PERMISSION_MODE_PLAN
    return PERMISSION_MODE_DEFAULT


def _resolve_permission_mode(
    permission_mode: Optional[str],
    approval_policy: Optional[str] = None,
    sandbox_mode: Optional[str] = None,
) -> str:
    if permission_mode is not None and str(permission_mode).strip():
        return _normalize_permission_mode(permission_mode)
    sandbox_value = str(sandbox_mode or "").strip().lower()
    if sandbox_value == "danger-full-access":
        return PERMISSION_MODE_FULL
    return PERMISSION_MODE_DEFAULT


@dataclass
class _FileCursor:
    path: Path
    offset: int
    inode: int
    session_id: Optional[str] = None
    align_line_on_next_read: bool = False


@dataclass
class _SessionRecord:
    session_id: str
    display_name: str
    state: str = "IDLE"
    last_seen_at: str = field(default_factory=_iso_now)
    last_seen_epoch: float = field(default_factory=time.time)
    last_state_change_mono: float = field(default_factory=time.monotonic)
    pending_state: Optional[str] = None
    pending_due_mono: float = 0.0
    idle_due_epoch: Optional[float] = None
    active: bool = True
    originator: str = "Codex Desktop"
    agent_brand: str = AGENT_BRAND_CODEX
    cwd: str = ""
    cwd_basename: str = ""
    branch: str = ""
    model: str = ""
    effort: str = ""
    permission_mode: str = PERMISSION_MODE_DEFAULT
    approval_policy: str = ""
    sandbox_mode: str = ""
    plan_mode: Optional[bool] = None
    plan_mode_fallback: bool = False
    total_tokens: int = 0
    model_context_window: int = 0
    primary_rate_remaining_percent: Optional[float] = None
    secondary_rate_remaining_percent: Optional[float] = None
    persona_id: str = ""
    persona_name: str = ""
    persona_content: str = ""
    last_event_type: str = ""
    has_real_user_input: bool = False

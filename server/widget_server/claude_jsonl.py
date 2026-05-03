import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .state import (
    WHITESPACE_PATTERN,
    _FileCursor,
    _basename_from_cwd,
    _claude_model_context_window,
    _extract_prompt_persona,
    _extract_visible_user_input,
    _is_auto_injected_message,
    _normalize_ts,
    _ts_to_epoch,
)

if TYPE_CHECKING:
    from .monitor import SessionBridgeService

logger = logging.getLogger(__name__)


def _event_payload_or_item(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload:
        return payload
    if str(event.get("type") or "") == "item.completed" and isinstance(event.get("item"), dict):
        return event.get("item") or {}
    return {}


def _event_timestamp_or_none(event: dict[str, Any]) -> tuple[str, float] | None:
    timestamp = _normalize_ts(event.get("timestamp"))
    if not timestamp:
        return None
    event_epoch = _ts_to_epoch(timestamp)
    if event_epoch <= 0:
        return None
    return timestamp, event_epoch


def _classify_claude_assistant_message(message: dict[str, Any]) -> tuple[str, str]:
    """Map Claude assistant message blocks to a session state and event type."""
    content = message.get("content")
    has_tool_use = False
    has_waiting_tool = False
    has_thinking = False
    has_text = False

    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "tool_use":
                has_tool_use = True
                tool_name = str(item.get("name") or "").strip().lower()
                if tool_name in {"askuserquestion", "request_user_input"}:
                    has_waiting_tool = True
                continue
            if item_type == "thinking":
                thinking_text = str(item.get("thinking") or item.get("text") or "").strip()
                if thinking_text:
                    has_thinking = True
                continue
            if item_type == "text":
                text_value = str(item.get("text") or "").strip()
                if text_value:
                    has_text = True
                continue

    if has_tool_use:
        if has_waiting_tool:
            return "WAITING", "request_user_input"
        return "TOOLING", "agent_tool_call_begin"

    stop_reason = str(message.get("stop_reason") or "").strip().lower()
    if has_text:
        if stop_reason in {"end_turn", "stop_sequence"}:
            return "IDLE", "assistant_message"
        return "RESPONDING", "assistant_message"

    if has_thinking:
        if stop_reason in {"end_turn", "stop_sequence"}:
            return "IDLE", "assistant_message"
        return "THINKING", "agent_reasoning"

    if stop_reason in {"end_turn", "stop_sequence"}:
        return "IDLE", "assistant_message"

    return "RESPONDING", "assistant_message"


class ClaudeJsonlParser:
    def __init__(self, service: "SessionBridgeService") -> None:
        self.service = service

    async def consume_file(self, path: Path) -> None:
        """Read incremental lines from a Claude session JSONL file."""
        key = str(path)
        stat = path.stat()
        cursor = self.service._claude_files.get(key)
        if cursor is None:
            session_id_from_name = None
            matched = self.service._session_id_pattern.search(path.stem)
            if matched:
                session_id_from_name = matched.group(0)
            cursor = _FileCursor(
                path=path,
                offset=0,
                inode=stat.st_ino,
                session_id=session_id_from_name,
            )
            self.service._claude_files[key] = cursor
        elif cursor.inode != stat.st_ino or stat.st_size < cursor.offset:
            cursor.offset = 0
            cursor.inode = stat.st_ino

        with path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(cursor.offset)
            for line in f:
                await self.ingest_line(line, cursor)
            cursor.offset = f.tell()

    async def ingest_line(self, line: str, cursor: _FileCursor) -> None:
        """Parse a single line from a Claude Code session JSONL file."""
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            return

        session_id = str(
            event.get("sessionId") or event.get("session_id") or cursor.session_id or ""
        ).strip()
        if not session_id or not self.service._session_id_pattern.fullmatch(session_id):
            return
        cursor.session_id = session_id

        parsed_ts = _event_timestamp_or_none(event)
        if parsed_ts is None:
            logger.debug("Ignoring Claude disk event without valid timestamp session=%s event=%s", session_id, event.get("type"))
            return
        timestamp, event_epoch = parsed_ts
        now_epoch = time.time()
        cwd = str(event.get("cwd") or "").strip()
        event_type = str(event.get("type") or "").lower()
        emitted_event: Optional[dict[str, Any]] = None

        async with self.service._sessions_lock:
            session = self.service._sessions.get(session_id)
            if session is None:
                session = self.service._new_session(session_id, timestamp)
                session.agent_brand = "claude"
                self.service._sessions[session_id] = session
                logger.info("Claude session online (disk): %s", session_id)

            if cwd:
                session.cwd = cwd
                session.cwd_basename = _basename_from_cwd(cwd)
            session.last_seen_at = timestamp
            session.last_seen_epoch = event_epoch
            session.active = (now_epoch - event_epoch) < self.service.inactive_ttl_sec
            session.agent_brand = "claude"
            session.originator = "Claude Code"

            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            if event_type == "user":
                content = message.get("content", "")
                if isinstance(content, list):
                    texts = [
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    content = " ".join(t for t in texts if t)
                if isinstance(content, str) and content.strip():
                    persona = _extract_prompt_persona(content)
                    if persona:
                        session.persona_id = str(persona.get("id") or "")
                        session.persona_name = str(persona.get("name") or "")
                        session.persona_content = str(persona.get("content") or "")
                    cleaned = WHITESPACE_PATTERN.sub(" ", _extract_visible_user_input(content)).strip()
                    if not _is_auto_injected_message("user", cleaned):
                        session.has_real_user_input = True
                        if len(cleaned) > 42:
                            cleaned = cleaned[:39].rstrip() + "..."
                        session.display_name = cleaned
                session.last_event_type = "user_message"
                session.state = "THINKING"
                emitted_event = self.service._build_state_event(session)

            elif event_type == "assistant":
                model = str(message.get("model") or "").strip()
                if model:
                    session.model = model
                    if session.model_context_window == 0:
                        session.model_context_window = _claude_model_context_window(model)
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                if isinstance(usage, dict):
                    inp = usage.get("input_tokens") or 0
                    out = usage.get("output_tokens") or 0
                    cache_read = usage.get("cache_read_input_tokens") or 0
                    cache_create = usage.get("cache_creation_input_tokens") or 0
                    try:
                        total = int(inp) + int(out) + int(cache_read) + int(cache_create)
                        if total > 0:
                            session.total_tokens = total
                    except (ValueError, TypeError):
                        pass
                assistant_state, assistant_event_type = _classify_claude_assistant_message(message)
                session.state = assistant_state
                session.last_event_type = assistant_event_type
                emitted_event = self.service._build_state_event(session)

            elif event_type == "tool_use":
                tool_name = str(event.get("name") or event.get("tool_name") or "").strip().lower()
                wait_for_user = tool_name in {"askuserquestion", "request_user_input"}
                session.last_event_type = "request_user_input" if wait_for_user else "agent_tool_call_begin"
                session.state = "WAITING" if wait_for_user else "TOOLING"
                emitted_event = self.service._build_state_event(session)

            elif event_type == "tool_result":
                session.last_event_type = "agent_tool_call_finish"
                session.state = "THINKING"
                emitted_event = self.service._build_state_event(session)

            elif event_type == "result":
                session.last_event_type = "task_complete"
                session.state = "IDLE"
                usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
                if isinstance(usage, dict):
                    inp = usage.get("input_tokens") or usage.get("input") or 0
                    out = usage.get("output_tokens") or usage.get("output") or 0
                    cache_read = usage.get("cache_read_input_tokens") or usage.get("cache_read") or 0
                    cache_create = usage.get("cache_creation_input_tokens") or usage.get("cache_creation") or 0
                    try:
                        total = int(inp) + int(out) + int(cache_read) + int(cache_create)
                        if total > 0:
                            session.total_tokens = total
                    except (ValueError, TypeError):
                        pass
                top_total = event.get("total_tokens")
                if top_total is not None:
                    coerced = self._coerce_non_negative_int(top_total)
                    if coerced is not None and coerced > 0:
                        session.total_tokens = coerced
                for key in ("model_context_window", "context_window", "max_tokens"):
                    val = event.get(key)
                    if val is not None:
                        coerced = self._coerce_non_negative_int(val)
                        if coerced is not None and coerced > 0:
                            session.model_context_window = coerced
                            break
                emitted_event = self.service._build_state_event(session)

            elif event_type == "rate_limit_event":
                rate_info = event.get("rate_limit_info") if isinstance(event.get("rate_limit_info"), dict) else {}
                if isinstance(rate_info, dict):
                    utilization = rate_info.get("utilization")
                    if utilization is not None:
                        try:
                            remaining = max(0.0, 100.0 - float(utilization))
                            session.primary_rate_remaining_percent = round(remaining, 2)
                        except (ValueError, TypeError):
                            pass
                emitted_event = self.service._build_state_event(session)

            elif event_type == "event_msg":
                payload = _event_payload_or_item(event)
                if str(payload.get("type") or "") == "token_count":
                    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
                    if isinstance(info, dict):
                        last_usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
                        total_tokens = self._coerce_non_negative_int(
                            last_usage.get("total_tokens") if isinstance(last_usage, dict) else None
                        )
                        model_context_window = self._coerce_non_negative_int(info.get("model_context_window"))
                        rate_limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
                        primary_remaining = self._remaining_percent_from_rate_limit(
                            rate_limits.get("primary") if isinstance(rate_limits, dict) else None
                        )
                        secondary_remaining = self._remaining_percent_from_rate_limit(
                            rate_limits.get("secondary") if isinstance(rate_limits, dict) else None
                        )
                        if total_tokens is not None:
                            session.total_tokens = total_tokens
                        if model_context_window is not None:
                            session.model_context_window = model_context_window
                        if primary_remaining is not None:
                            session.primary_rate_remaining_percent = primary_remaining
                        if secondary_remaining is not None:
                            session.secondary_rate_remaining_percent = secondary_remaining
                        session.last_event_type = "token_count"
                        emitted_event = self.service._build_state_event(session)

            elif event_type == "summary":
                summary_text = _extract_visible_user_input(event.get("summary"))
                if summary_text:
                    if not _is_auto_injected_message("user", summary_text) and not _is_auto_injected_message("assistant", summary_text):
                        session.has_real_user_input = True
                        if len(summary_text) > 42:
                            summary_text = summary_text[:39].rstrip() + "..."
                        session.display_name = summary_text
                emitted_event = self.service._build_state_event(session)

            elif event_type in {"last-prompt", "last_prompt"}:
                last_prompt_raw = str(event.get("lastPrompt") or event.get("last_prompt") or "").strip()
                persona = _extract_prompt_persona(last_prompt_raw)
                if persona:
                    session.persona_id = str(persona.get("id") or "")
                    session.persona_name = str(persona.get("name") or "")
                    session.persona_content = str(persona.get("content") or "")
                last_prompt = _extract_visible_user_input(last_prompt_raw)
                if last_prompt:
                    if not _is_auto_injected_message("user", last_prompt):
                        session.has_real_user_input = True
                        if len(last_prompt) > 42:
                            last_prompt = last_prompt[:39].rstrip() + "..."
                        session.display_name = last_prompt
                emitted_event = self.service._build_state_event(session)

            elif event_type == "queue-operation":
                operation = str(event.get("operation") or "").strip().lower()
                queued_content_raw = str(event.get("content") or "").strip()
                persona = _extract_prompt_persona(queued_content_raw)
                if persona:
                    session.persona_id = str(persona.get("id") or "")
                    session.persona_name = str(persona.get("name") or "")
                    session.persona_content = str(persona.get("content") or "")
                queued_content = _extract_visible_user_input(queued_content_raw)
                if operation == "enqueue" and queued_content and not _is_auto_injected_message("user", queued_content):
                    session.has_real_user_input = True
                    if len(queued_content) > 42:
                        queued_content = queued_content[:39].rstrip() + "..."
                    session.display_name = queued_content
                    session.last_event_type = "user_message"
                    session.state = "THINKING"
                    emitted_event = self.service._build_state_event(session)

        if emitted_event:
            await self.service._broadcast(emitted_event)

    @staticmethod
    def _coerce_non_negative_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            if isinstance(value, float) and value != value:
                return None
            return max(0, int(value))
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return max(0, int(float(text)))
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_percent(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            if isinstance(value, float) and value != value:
                return None
            return max(0.0, min(100.0, float(value)))
        if isinstance(value, str):
            text = value.strip().replace("%", "")
            if not text:
                return None
            try:
                return max(0.0, min(100.0, float(text)))
            except ValueError:
                return None
        return None

    @classmethod
    def _remaining_percent_from_rate_limit(cls, item: Any) -> Optional[float]:
        if not isinstance(item, dict):
            return None
        used = cls._coerce_percent(item.get("used_percent"))
        if used is None:
            return None
        return max(0.0, min(100.0, 100.0 - used))


__all__ = ["ClaudeJsonlParser"]

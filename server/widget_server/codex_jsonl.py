import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .state import (
    PERMISSION_MODE_DEFAULT,
    SESSION_STATES,
    STATE_PRIORITY,
    WHITESPACE_PATTERN,
    _FileCursor,
    _SessionRecord,
    _basename_from_cwd,
    _extract_message_content,
    _extract_prompt_persona,
    _extract_visible_user_input,
    _is_auto_injected_message,
    _resolve_permission_mode,
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


class CodexJsonlParser:
    def __init__(self, service: "SessionBridgeService") -> None:
        self.service = service

    def collect_history_from_line(
        self,
        line: str,
        cursor: _FileCursor,
        sessions: dict[str, dict[str, Any]],
    ) -> None:
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return

        top_type = event.get("type", "")
        payload = _event_payload_or_item(event)
        parsed_ts = _event_timestamp_or_none(event)
        if parsed_ts is None:
            return
        ts, ts_epoch = parsed_ts
        session_id = self._extract_session_id(event, payload, cursor)
        if not session_id:
            return
        cursor.session_id = session_id

        record = sessions.get(session_id)
        if record is None:
            record = {
                "session_id": session_id,
                "display_name": f"session-{session_id[:8]}",
                "state": "IDLE",
                "last_seen_at": ts,
                "last_seen_epoch": ts_epoch,
                "originator": "Codex Desktop",
                "cwd": "",
                "cwd_basename": "",
                "last_event_type": "",
                "has_real_user_input": False,
                "branch": "",
                "context": {
                    "model": "",
                    "effort": "",
                    "persona_id": "",
                    "persona_name": "",
                    "persona_content": "",
                    "permission_mode": PERMISSION_MODE_DEFAULT,
                    "approval_policy": "",
                    "sandbox_mode": "",
                    "plan_mode": None,
                    "plan_mode_fallback": False,
                    "total_tokens": 0,
                    "model_context_window": 0,
                    "primary_rate_remaining_percent": None,
                    "secondary_rate_remaining_percent": None,
                },
            }
            sessions[session_id] = record

        if ts_epoch < (record["last_seen_epoch"] - 1e-6):
            return

        record["last_seen_at"] = ts
        record["last_seen_epoch"] = ts_epoch
        record["last_event_type"] = str(payload.get("type") or top_type)

        if top_type == "session_meta":
            display_name = payload.get("display_name") or payload.get("name")
            if isinstance(display_name, str) and display_name.strip():
                record["display_name"] = display_name.strip()
            record["originator"] = str(payload.get("originator") or record.get("originator") or "Codex Desktop")
            record["cwd"] = str(payload.get("cwd") or record.get("cwd") or "")
            record["cwd_basename"] = _basename_from_cwd(record["cwd"])
            git_info = payload.get("git") if isinstance(payload.get("git"), dict) else {}
            if isinstance(git_info, dict):
                branch = str(git_info.get("branch") or "").strip()
                if branch:
                    record["branch"] = branch

        if top_type == "turn_context":
            context = record.get("context") if isinstance(record.get("context"), dict) else {}
            context["model"] = str(payload.get("model") or context.get("model") or "")
            context["effort"] = str(payload.get("effort") or context.get("effort") or "")
            context["approval_policy"] = str(payload.get("approval_policy") or context.get("approval_policy") or "")
            sandbox = payload.get("sandbox_policy") if isinstance(payload.get("sandbox_policy"), dict) else {}
            if isinstance(sandbox, dict):
                context["sandbox_mode"] = str(sandbox.get("type") or context.get("sandbox_mode") or "")
            context["permission_mode"] = _resolve_permission_mode(
                None,
                approval_policy=context.get("approval_policy"),
                sandbox_mode=context.get("sandbox_mode"),
            )
            collaboration = payload.get("collaboration_mode") if isinstance(payload.get("collaboration_mode"), dict) else {}
            plan_mode = None
            if isinstance(collaboration, dict):
                mode = str(collaboration.get("mode") or "").strip().lower()
                if mode:
                    plan_mode = mode == "plan"
            if plan_mode is not None:
                context["plan_mode"] = plan_mode
            context["plan_mode_fallback"] = bool(context.get("plan_mode_fallback", False))
            record["context"] = context
            cwd_from_turn = str(payload.get("cwd") or "").strip()
            if cwd_from_turn:
                record["cwd"] = cwd_from_turn
                record["cwd_basename"] = _basename_from_cwd(cwd_from_turn)

        if top_type == "event_msg" and str(payload.get("type") or "") == "token_count":
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            if isinstance(info, dict):
                context = record.get("context") if isinstance(record.get("context"), dict) else {}
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
                    context["total_tokens"] = total_tokens
                if model_context_window is not None:
                    context["model_context_window"] = model_context_window
                if primary_remaining is not None:
                    context["primary_rate_remaining_percent"] = primary_remaining
                if secondary_remaining is not None:
                    context["secondary_rate_remaining_percent"] = secondary_remaining
                record["context"] = context

        title = self._extract_title(top_type, payload)
        if title:
            record["display_name"] = title
        context = record.get("context") if isinstance(record.get("context"), dict) else {}
        if top_type == "event_msg" and str(payload.get("type") or "") == "user_message":
            raw_user_message = str(payload.get("message") or "")
            user_message = _extract_visible_user_input(raw_user_message)
            persona = _extract_prompt_persona(raw_user_message)
            if persona:
                context["persona_id"] = str(persona.get("id") or "")
                context["persona_name"] = str(persona.get("name") or "")
                context["persona_content"] = str(persona.get("content") or "")
            if user_message and not _is_auto_injected_message("user", user_message):
                record["has_real_user_input"] = True
        elif top_type == "response_item" and str(payload.get("type") or "") == "message" and str(payload.get("role") or "") == "user":
            raw_user_content = _extract_message_content(payload)
            user_content = _extract_visible_user_input(raw_user_content)
            persona = _extract_prompt_persona(raw_user_content)
            if persona:
                context["persona_id"] = str(persona.get("id") or "")
                context["persona_name"] = str(persona.get("name") or "")
                context["persona_content"] = str(persona.get("content") or "")
            if user_content and not _is_auto_injected_message("user", user_content):
                record["has_real_user_input"] = True
        record["context"] = context

        state, is_task_complete, wait_for_user = self._map_to_state(top_type, payload)
        if wait_for_user:
            record["state"] = "WAITING"
        elif is_task_complete:
            record["state"] = "IDLE"
        elif state in SESSION_STATES:
            record["state"] = state

    async def consume_file(self, path: Path) -> None:
        key = str(path)
        stat = path.stat()
        cursor = self.service._files.get(key)
        if cursor is None:
            start_offset = max(stat.st_size - self.service.initial_read_bytes, 0)
            session_id_from_name = None
            matched = self.service._session_id_pattern.search(path.name)
            if matched:
                session_id_from_name = matched.group(0)
            cursor = _FileCursor(
                path=path,
                offset=start_offset,
                inode=stat.st_ino,
                session_id=session_id_from_name,
                align_line_on_next_read=(start_offset > 0),
            )
            self.service._files[key] = cursor
        elif cursor.inode != stat.st_ino or stat.st_size < cursor.offset:
            cursor.offset = 0
            cursor.inode = stat.st_ino
            cursor.align_line_on_next_read = False

        with path.open("r", encoding="utf-8", errors="ignore") as f:
            f.seek(cursor.offset)
            if cursor.align_line_on_next_read:
                f.readline()
                cursor.align_line_on_next_read = False
            for line in f:
                await self.consume_line(line, cursor)
            cursor.offset = f.tell()

    async def consume_line(self, line: str, cursor: _FileCursor) -> None:
        text = line.strip()
        if not text:
            return
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            self.service.events_dropped_total += 1
            logger.warning("Session bridge dropped malformed json line in %s", cursor.path)
            return
        self.service.events_ingested_total += 1
        self.service.latest_event_epoch = time.time()
        await self._ingest_event(event, cursor)

    async def _ingest_event(self, event: dict[str, Any], cursor: _FileCursor) -> None:
        top_type = event.get("type", "")
        payload = _event_payload_or_item(event)
        parsed_ts = _event_timestamp_or_none(event)
        if parsed_ts is None:
            logger.debug("Ignoring Codex event without valid timestamp event=%s", top_type)
            return
        timestamp, event_epoch = parsed_ts
        now_epoch = time.time()

        if top_type == "session_meta":
            session_id = self._extract_session_id(event, payload, cursor)
            if not session_id:
                logger.warning("session_meta without session id: %s", event)
                return
            cursor.session_id = session_id
            async with self.service._sessions_lock:
                session = self.service._sessions.get(session_id)
                if session is None:
                    session = self.service._new_session(session_id, timestamp)
                    self.service._sessions[session_id] = session
                    logger.info("session online: %s", session_id)
                elif event_epoch < (session.last_seen_epoch - 1e-6):
                    return
                session.originator = str(payload.get("originator") or session.originator)
                session.cwd = str(payload.get("cwd") or session.cwd)
                session.cwd_basename = _basename_from_cwd(session.cwd)
                git_info = payload.get("git") if isinstance(payload.get("git"), dict) else {}
                if isinstance(git_info, dict):
                    branch = str(git_info.get("branch") or "").strip()
                    if branch:
                        session.branch = branch
                session.last_event_type = "session_meta"
                session.last_seen_at = timestamp
                session.last_seen_epoch = event_epoch
                session.active = (now_epoch - session.last_seen_epoch) < self.service.inactive_ttl_sec
                display_name = payload.get("display_name") or payload.get("name")
                if isinstance(display_name, str) and display_name.strip():
                    session.display_name = display_name.strip()
            return

        session_id = cursor.session_id or self._extract_session_id(event, payload, cursor)
        if not session_id:
            logger.warning("Session bridge dropped event without session id. type=%s", top_type)
            self.service.events_dropped_total += 1
            return
        cursor.session_id = session_id

        state, is_task_complete, wait_for_user = self._map_to_state(top_type, payload)
        event_type = str(payload.get("type") or top_type)
        emitted_event: Optional[dict[str, Any]] = None

        async with self.service._sessions_lock:
            session = self.service._sessions.get(session_id)
            if session is None:
                session = self.service._new_session(session_id, timestamp)
                self.service._sessions[session_id] = session
                logger.info("session online: %s", session_id)
            elif event_epoch < (session.last_seen_epoch - 1e-6):
                return

            session.last_seen_at = timestamp
            session.last_seen_epoch = event_epoch
            session.active = (now_epoch - session.last_seen_epoch) < self.service.inactive_ttl_sec
            session.last_event_type = event_type
            if session.cwd:
                session.cwd_basename = _basename_from_cwd(session.cwd)
            title = self._extract_title(top_type, payload)
            if title:
                session.display_name = title
            if top_type == "event_msg" and event_type == "user_message":
                raw_user_message = str(payload.get("message") or "")
                user_message = _extract_visible_user_input(raw_user_message)
                persona = _extract_prompt_persona(raw_user_message)
                if persona:
                    session.persona_id = str(persona.get("id") or "")
                    session.persona_name = str(persona.get("name") or "")
                    session.persona_content = str(persona.get("content") or "")
                if user_message and not _is_auto_injected_message("user", user_message):
                    session.has_real_user_input = True
            elif top_type == "response_item" and event_type == "message" and str(payload.get("role") or "") == "user":
                raw_user_content = _extract_message_content(payload)
                user_content = _extract_visible_user_input(raw_user_content)
                persona = _extract_prompt_persona(raw_user_content)
                if persona:
                    session.persona_id = str(persona.get("id") or "")
                    session.persona_name = str(persona.get("name") or "")
                    session.persona_content = str(persona.get("content") or "")
                if user_content and not _is_auto_injected_message("user", user_content):
                    session.has_real_user_input = True

            if top_type == "turn_context":
                session.model = str(payload.get("model") or session.model or "")
                session.effort = str(payload.get("effort") or session.effort or "")
                session.approval_policy = str(payload.get("approval_policy") or session.approval_policy or "")
                sandbox = payload.get("sandbox_policy") if isinstance(payload.get("sandbox_policy"), dict) else {}
                if isinstance(sandbox, dict):
                    session.sandbox_mode = str(sandbox.get("type") or session.sandbox_mode or "")
                session.permission_mode = _resolve_permission_mode(
                    None,
                    approval_policy=session.approval_policy,
                    sandbox_mode=session.sandbox_mode,
                )
                cwd_from_turn = str(payload.get("cwd") or "").strip()
                if cwd_from_turn:
                    session.cwd = cwd_from_turn
                    session.cwd_basename = _basename_from_cwd(cwd_from_turn)
                collaboration = payload.get("collaboration_mode") if isinstance(payload.get("collaboration_mode"), dict) else {}
                if isinstance(collaboration, dict):
                    mode = str(collaboration.get("mode") or "").strip().lower()
                    if mode:
                        session.plan_mode = mode == "plan"
                        session.plan_mode_fallback = False
                emitted_event = self.service._build_state_event(session)
                state = None

            if top_type == "event_msg" and event_type == "token_count":
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
                    emitted_event = self.service._build_state_event(session)
                    state = None

            if is_task_complete:
                if session.pending_state == "RESPONDING" and session.state != "RESPONDING":
                    session.state = "RESPONDING"
                    session.last_state_change_mono = time.monotonic()
                    session.pending_state = None
                    session.pending_due_mono = 0.0
                    emitted_event = self.service._build_state_event(session)
                    session.idle_due_epoch = session.last_seen_epoch + self.service.idle_after_task_complete_sec
                elif session.state in {"THINKING", "TOOLING"}:
                    session.state = "IDLE"
                    session.last_state_change_mono = time.monotonic()
                    session.pending_state = None
                    session.pending_due_mono = 0.0
                    session.idle_due_epoch = None
                    emitted_event = self.service._build_state_event(session)
                else:
                    session.idle_due_epoch = session.last_seen_epoch + self.service.idle_after_task_complete_sec
            elif state in {"THINKING", "TOOLING", "RESPONDING", "WAITING"} or wait_for_user:
                session.idle_due_epoch = None

            if state in SESSION_STATES:
                previous_state = session.state
                if self._schedule_state_transition(session, state):
                    if previous_state != session.state:
                        logger.info("session state: %s %s -> %s", session_id, previous_state, session.state)
                    emitted_event = self.service._build_state_event(session)

            if wait_for_user and session.state != "WAITING":
                previous_state = session.state
                session.pending_state = None
                session.state = "WAITING"
                session.last_state_change_mono = time.monotonic()
                logger.info("session state: %s %s -> WAITING", session_id, previous_state)
                emitted_event = self.service._build_state_event(session)

        if emitted_event:
            await self.service._broadcast(emitted_event)
        elif state is None and not is_task_complete:
            logger.debug(
                "Session bridge ignored unknown event: top_type=%s payload_type=%s",
                top_type,
                payload.get("type"),
            )

    def extract_session_id_from_path(self, path: Path) -> Optional[str]:
        match_by_name = self.service._session_id_pattern.search(path.name)
        if match_by_name:
            return match_by_name.group(0)
        match_by_full_path = self.service._session_id_pattern.search(str(path))
        if match_by_full_path:
            return match_by_full_path.group(0)
        return None

    def _extract_visible_user_message(self, top_type: str, payload: dict[str, Any]) -> str:
        text = ""
        payload_type = str(payload.get("type") or "")
        if top_type == "event_msg" and payload_type == "user_message":
            text = str(payload.get("message") or "")
        elif top_type == "response_item" and payload_type == "message" and str(payload.get("role") or "") == "user":
            content = payload.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                chunks: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    candidate = item.get("text")
                    if not isinstance(candidate, str) or not candidate.strip():
                        candidate = item.get("content")
                    if isinstance(candidate, str) and candidate.strip():
                        chunks.append(candidate.strip())
                if chunks:
                    text = " ".join(chunks)
            if not text:
                text = str(payload.get("message") or "")
        return _extract_visible_user_input(text)

    def _extract_title(self, top_type: str, payload: dict[str, Any]) -> str:
        cleaned = WHITESPACE_PATTERN.sub(" ", self._extract_visible_user_message(top_type, payload)).strip()
        if not cleaned:
            return ""
        if _is_auto_injected_message("user", cleaned):
            return ""
        max_len = 42
        if len(cleaned) > max_len:
            return cleaned[: max_len - 3].rstrip() + "..."
        return cleaned

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

    def _map_to_state(self, top_type: str, payload: dict[str, Any]) -> tuple[Optional[str], bool, bool]:
        payload_type = str(payload.get("type") or "")

        if top_type == "event_msg":
            if payload_type == "agent_reasoning":
                return "THINKING", False, False
            if payload_type == "agent_message":
                return "RESPONDING", True, False
            if payload_type == "task_complete":
                return None, True, False

        if top_type == "response_item":
            if payload_type == "reasoning":
                return "THINKING", False, False
            if payload_type in {"function_call", "custom_tool_call"}:
                name = str(payload.get("name") or "")
                args_text = json.dumps(payload.get("arguments", ""), ensure_ascii=False)
                wait_for_user = name == "request_user_input" or "request_user_input" in args_text
                return ("WAITING" if wait_for_user else "TOOLING"), False, wait_for_user
            if payload_type == "message" and str(payload.get("role") or "") == "assistant":
                return "RESPONDING", True, False

        if top_type == "item.completed":
            item_type = str(payload.get("type") or "")
            if item_type in {"agent_message", "assistant_message"}:
                return "RESPONDING", True, False
            if item_type == "message" and str(payload.get("role") or "").lower() == "assistant":
                return "RESPONDING", True, False

        if top_type == "custom_tool_call":
            name = str(payload.get("name") or "")
            wait_for_user = name == "request_user_input"
            return ("WAITING" if wait_for_user else "TOOLING"), False, wait_for_user

        return None, False, False

    def _extract_session_id(
        self,
        event: dict[str, Any],
        payload: dict[str, Any],
        cursor: _FileCursor,
    ) -> Optional[str]:
        candidates: list[Any] = [
            event.get("session_id"),
            event.get("sessionId"),
            payload.get("session_id"),
            payload.get("sessionId"),
        ]
        session_payload = payload.get("session")
        if isinstance(session_payload, dict):
            candidates.extend([session_payload.get("id"), session_payload.get("session_id")])

        if cursor.session_id:
            candidates.append(cursor.session_id)

        file_match = self.service._session_id_pattern.search(cursor.path.name)
        if file_match:
            candidates.append(file_match.group(0))
        path_match = self.service._session_id_pattern.search(str(cursor.path))
        if path_match:
            candidates.append(path_match.group(0))

        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            normalized = candidate.strip()
            if normalized and self.service._session_id_pattern.fullmatch(normalized):
                return normalized
        return None

    def _schedule_state_transition(self, session: _SessionRecord, new_state: str) -> bool:
        if session.state == new_state:
            session.pending_state = None
            session.pending_due_mono = 0.0
            return False

        now_mono = time.monotonic()
        if now_mono - session.last_state_change_mono >= self.service.min_state_duration_sec:
            session.state = new_state
            session.last_state_change_mono = now_mono
            session.pending_state = None
            session.pending_due_mono = 0.0
            return True

        if session.pending_state is None:
            session.pending_state = new_state
        elif STATE_PRIORITY[new_state] > STATE_PRIORITY[session.pending_state]:
            session.pending_state = new_state

        session.pending_due_mono = session.last_state_change_mono + self.service.min_state_duration_sec
        return False


__all__ = ["CodexJsonlParser", "_event_payload_or_item", "_event_timestamp_or_none"]
